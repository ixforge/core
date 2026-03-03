"""CLI entrypoint."""

from __future__ import annotations

import asyncio
import getpass
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def _run_server() -> None:
    """Start the API server."""
    import uvicorn

    from ixforge.config import get_settings

    settings = get_settings()
    uvicorn.run(
        "ixforge.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )


def _run_worker(queues: list[str] | None = None) -> None:
    """Start procrastinate background workers.

    Parameters
    ----------
    queues:
        Optional list of queue names to listen on.  When *None*, the worker
        processes jobs from all queues.
    """
    from ixforge.tasks import app

    kwargs: dict[str, object] = {}
    if queues:
        kwargs["queues"] = queues

    asyncio.run(app.run_worker_async(**kwargs))  # type: ignore[arg-type]


def _run_upgrade() -> None:
    """Run Alembic database migrations and apply procrastinate schema."""
    from alembic.config import Config as AlembicConfig

    from alembic import command as alembic_command

    # Apply procrastinate schema first (idempotent)
    _apply_procrastinate_schema()

    cfg = AlembicConfig("alembic.ini")
    alembic_command.upgrade(cfg, "head")
    print("Database migrations applied successfully.")


def _apply_procrastinate_schema() -> None:
    """Apply the procrastinate job queue schema (idempotent)."""
    try:
        from ixforge.tasks import app as procrastinate_app

        asyncio.run(procrastinate_app.schema_manager.apply_schema_async())
        print("Procrastinate schema applied successfully.")
    except Exception as exc:
        print(f"Warning: could not apply procrastinate schema: {exc}")
        print("The worker may not start correctly without the procrastinate tables.")


def _run_createsuperuser() -> None:
    """Create an admin user.

    Reads credentials from environment variables ``IXFORGE_ADMIN_EMAIL`` and
    ``IXFORGE_ADMIN_PASSWORD``, falling back to interactive stdin prompts.
    """
    email = os.environ.get("IXFORGE_ADMIN_EMAIL", "")
    password = os.environ.get("IXFORGE_ADMIN_PASSWORD", "")

    if not email:
        email = input("Email: ").strip()
    if not email:
        print("Error: email is required")
        sys.exit(1)

    if not password:
        password = getpass.getpass("Password: ")
    if not password:
        print("Error: password is required")
        sys.exit(1)

    full_name = os.environ.get("IXFORGE_ADMIN_FULL_NAME", "Admin")

    asyncio.run(_create_admin_user(email, password, full_name))


async def _create_admin_user(email: str, password: str, full_name: str) -> None:
    """Insert the admin user into the database."""
    from sqlalchemy import select

    from ixforge.database import get_session_factory
    from ixforge.models.user import User, UserRole
    from ixforge.services.auth import hash_password

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()
        if existing is not None:
            print(f"Error: user with email '{email}' already exists")
            sys.exit(1)

        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=UserRole.admin,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        print(f"Admin user '{email}' created successfully.")


def _get_pg_connection_parts() -> dict[str, str]:
    """Extract host, port, user, dbname from DATABASE_URL for pg_dump/pg_restore."""
    from ixforge.config import get_settings

    settings = get_settings()
    url = settings.database_url

    # Strip the asyncpg driver prefix so we can parse a plain postgresql:// URL
    url = url.replace("postgresql+asyncpg://", "postgresql://")

    from urllib.parse import urlparse

    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "ixforge",
        "dbname": parsed.path.lstrip("/") if parsed.path else "ixforge",
        "password": parsed.password or "",
    }


def _run_backup() -> None:
    """Create a compressed PostgreSQL backup using ``pg_dump``."""
    parts = _get_pg_connection_parts()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"ixforge_backup_{timestamp}.sql.gz"

    env = os.environ.copy()
    if parts["password"]:
        env["PGPASSWORD"] = parts["password"]

    cmd = [
        "pg_dump",
        "-h",
        parts["host"],
        "-p",
        parts["port"],
        "-U",
        parts["user"],
        "-d",
        parts["dbname"],
        "--no-owner",
        "--no-acl",
        "-Z",
        "9",
        "-f",
        filename,
    ]

    print(f"Creating backup: {filename}")
    result = subprocess.run(cmd, env=env, check=False)
    if result.returncode != 0:
        print("Error: pg_dump failed")
        sys.exit(1)
    print(f"Backup saved to {filename}")


def _run_restore(archive: str) -> None:
    """Restore a PostgreSQL database from a compressed backup archive."""
    path = Path(archive)
    if not path.exists():
        print(f"Error: archive not found: {archive}")
        sys.exit(1)

    parts = _get_pg_connection_parts()

    env = os.environ.copy()
    if parts["password"]:
        env["PGPASSWORD"] = parts["password"]

    psql_cmd = [
        "psql",
        "-h",
        parts["host"],
        "-p",
        parts["port"],
        "-U",
        parts["user"],
        "-d",
        parts["dbname"],
    ]

    print(f"Restoring from {archive}...")

    if archive.endswith(".gz"):
        # Pipe gunzip output into psql
        gunzip = subprocess.Popen(["gunzip", "-c", archive], stdout=subprocess.PIPE, env=env)
        psql = subprocess.run(psql_cmd, stdin=gunzip.stdout, env=env, check=False)
        if gunzip.stdout is not None:
            gunzip.stdout.close()
        gunzip.wait()
        if psql.returncode != 0 or gunzip.returncode != 0:
            print("Error: restore failed")
            sys.exit(1)
    else:
        result = subprocess.run([*psql_cmd, "-f", archive], env=env, check=False)
        if result.returncode != 0:
            print("Error: restore failed")
            sys.exit(1)

    print("Restore completed successfully.")


async def _seed_data() -> None:
    """Insert sample development data (idempotent)."""
    from sqlalchemy import select

    from ixforge.database import get_session_factory
    from ixforge.enums import (
        BGPAdminState,
        BGPOperState,
        ConnectionState,
        ConnectionType,
        MemberState,
        PeeringPolicy,
        PortType,
        VLANType,
    )
    from ixforge.models.bgp_session import BGPSession
    from ixforge.models.connection import Connection, ConnectionVLAN
    from ixforge.models.ip import IPAssignment, IPPool
    from ixforge.models.ixp import IXP
    from ixforge.models.member import Member
    from ixforge.models.port import Port
    from ixforge.models.route_server import RouteServer
    from ixforge.models.switch import Switch
    from ixforge.models.vlan import VLAN

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Check idempotency: skip if an IXP named "Demo IXP" already exists.
        result = await session.execute(select(IXP).where(IXP.short_name == "DEMO"))
        if result.scalar_one_or_none() is not None:
            print("Seed data already exists, skipping.")
            return

        # -- IXP --
        ixp = IXP(
            name="Demo IXP",
            short_name="DEMO",
            asn=65000,
            website="https://demo-ixp.example.net",
            country="US",
            city="San Francisco",
        )
        session.add(ixp)
        await session.flush()
        print(f"Created IXP: {ixp.name} (id={ixp.id})")

        # -- Members in various states --
        members_data = [
            ("Acme Networks", "ACME", 64512, MemberState.active, PeeringPolicy.open),
            ("Beta Corp", "BETA", 64513, MemberState.provisioning, PeeringPolicy.selective),
            ("Gamma Telecom", "GAMMA", 64514, MemberState.prospect, PeeringPolicy.open),
            ("Delta ISP", "DELTA", 64515, MemberState.suspended, PeeringPolicy.restrictive),
            ("Epsilon Cloud", "EPSILON", 64516, MemberState.active, PeeringPolicy.open),
        ]
        members: list[Member] = []
        for name, short, asn, state, policy in members_data:
            m = Member(
                ixp_id=ixp.id,
                name=name,
                short_name=short,
                asn=asn,
                state=state,
                peering_policy=policy,
                website=f"https://{short.lower()}.example.net",
            )
            session.add(m)
            members.append(m)
        await session.flush()
        print(f"Created {len(members)} members")

        # -- Switches --
        switches: list[Switch] = []
        for i in range(2):
            sw = Switch(
                ixp_id=ixp.id,
                name=f"switch-{i + 1:02d}",
                hostname=f"switch-{i + 1:02d}.demo-ixp.example.net",
                vendor="Arista",
                model="DCS-7280SR-48C6",
                management_ip=f"10.0.0.{i + 1}",
                is_active=True,
            )
            session.add(sw)
            switches.append(sw)
        await session.flush()
        print(f"Created {len(switches)} switches")

        # -- Ports (4 ports per switch) --
        ports: list[Port] = []
        for sw in switches:
            for p in range(4):
                port = Port(
                    ixp_id=ixp.id,
                    switch_id=sw.id,
                    name=f"Ethernet{p + 1}",
                    speed=10000,
                    type=PortType.member,
                    is_active=True,
                )
                session.add(port)
                ports.append(port)
        await session.flush()
        print(f"Created {len(ports)} ports")

        # -- VLANs --
        vlan_prod = VLAN(
            ixp_id=ixp.id,
            name="Production Peering",
            vid=100,
            type=VLANType.production,
            description="Main peering VLAN",
        )
        vlan_quar = VLAN(
            ixp_id=ixp.id,
            name="Quarantine",
            vid=999,
            type=VLANType.quarantine,
            description="Quarantine VLAN for new members",
        )
        session.add(vlan_prod)
        session.add(vlan_quar)
        await session.flush()
        print("Created 2 VLANs")

        # -- IP Pools --
        pool_v4 = IPPool(
            ixp_id=ixp.id,
            vlan_id=vlan_prod.id,
            network="192.0.2.0/24",
            af=4,
        )
        pool_v6 = IPPool(
            ixp_id=ixp.id,
            vlan_id=vlan_prod.id,
            network="2001:db8::/64",
            af=6,
        )
        session.add(pool_v4)
        session.add(pool_v6)
        await session.flush()
        print("Created 2 IP pools (IPv4 + IPv6)")

        # -- Connections for active members with ports, VLANs, IPs --
        active_members = [m for m in members if m.state == MemberState.active]
        connections: list[Connection] = []
        ip_offset = 1  # Start from .1 (skip network .0)
        for port_idx, m in enumerate(active_members):
            if port_idx >= len(ports):
                break
            conn = Connection(
                ixp_id=ixp.id,
                member_id=m.id,
                port_id=ports[port_idx].id,
                type=ConnectionType.physical,
                state=ConnectionState.active,
                speed=10000,
                mac_address=f"00:11:22:33:44:{port_idx:02x}",
            )
            session.add(conn)
            connections.append(conn)
        await session.flush()
        print(f"Created {len(connections)} connections")

        # Attach VLANs and IPs to connections
        for i, conn in enumerate(connections):
            cv = ConnectionVLAN(
                ixp_id=ixp.id,
                connection_id=conn.id,
                vlan_id=vlan_prod.id,
                tagged=False,
            )
            session.add(cv)

            ip4 = IPAssignment(
                ixp_id=ixp.id,
                pool_id=pool_v4.id,
                connection_id=conn.id,
                address=f"192.0.2.{ip_offset + i}",
            )
            session.add(ip4)

            ip6 = IPAssignment(
                ixp_id=ixp.id,
                pool_id=pool_v6.id,
                connection_id=conn.id,
                address=f"2001:db8::{ip_offset + i}",
            )
            session.add(ip6)
        await session.flush()

        # -- Route Servers --
        route_servers: list[RouteServer] = []
        for i in range(2):
            rs = RouteServer(
                ixp_id=ixp.id,
                name=f"rs{i + 1}",
                hostname=f"rs{i + 1}.demo-ixp.example.net",
                ip_v4=f"192.0.2.{250 + i}",
                ip_v6=f"2001:db8::{250 + i}",
                asn=65000,
                software="bird",
                is_active=True,
            )
            session.add(rs)
            route_servers.append(rs)
        await session.flush()
        print(f"Created {len(route_servers)} route servers")

        # -- BGP Sessions (one per active connection per route server) --
        bgp_count = 0
        for conn_obj in connections:
            member_obj = next(m for m in members if m.id == conn_obj.member_id)
            for rs in route_servers:
                bgp = BGPSession(
                    ixp_id=ixp.id,
                    route_server_id=rs.id,
                    connection_id=conn_obj.id,
                    peer_ip=f"192.0.2.{ip_offset + connections.index(conn_obj)}",
                    peer_asn=member_obj.asn,
                    admin_state=BGPAdminState.up,
                    oper_state=BGPOperState.up,
                    af=4,
                    max_prefixes=100,
                )
                session.add(bgp)
                bgp_count += 1
        await session.flush()
        print(f"Created {bgp_count} BGP sessions")

        await session.commit()
        print("Seed data created successfully.")


def _run_seed() -> None:
    """Seed the database with sample development data."""
    asyncio.run(_seed_data())


def _run_ui() -> None:
    """Start the UI portal server."""
    import uvicorn

    from ixforge.config import get_settings

    settings = get_settings()
    uvicorn.run(
        "ixforge.ui.app:create_ui_app",
        factory=True,
        host="0.0.0.0",
        port=settings.ui_port,
        reload=settings.debug,
    )


_COMMANDS = {
    "run": "Start the API server",
    "ui": "Start the admin portal (port 8001)",
    "worker": "Start background task workers",
    "upgrade": "Run database migrations (alembic upgrade head)",
    "createsuperuser": "Create an admin user",
    "seed": "Seed database with sample development data",
    "backup": "Create a compressed database backup",
    "restore": "Restore database from a backup archive",
}


def _print_usage() -> None:
    print("Usage: ixforge <command> [options]\n")
    print("Commands:")
    for cmd, desc in _COMMANDS.items():
        print(f"  {cmd:20s} {desc}")


def main() -> None:
    if len(sys.argv) < 2:
        _print_usage()
        sys.exit(1)

    command = sys.argv[1]

    if command == "run":
        _run_server()
    elif command == "ui":
        _run_ui()
    elif command == "worker":
        # Parse optional --queues flag: ixforge worker --queues config maintenance
        queues: list[str] | None = None
        if "--queues" in sys.argv:
            idx = sys.argv.index("--queues")
            queues = sys.argv[idx + 1 :]
            if not queues or any(q.startswith("-") for q in queues):
                print("Error: --queues requires at least one valid queue name")
                sys.exit(1)
        _run_worker(queues=queues)
    elif command == "upgrade":
        _run_upgrade()
    elif command == "createsuperuser":
        _run_createsuperuser()
    elif command == "seed":
        _run_seed()
    elif command == "backup":
        _run_backup()
    elif command == "restore":
        if len(sys.argv) < 3:
            print("Usage: ixforge restore <archive>")
            sys.exit(1)
        _run_restore(sys.argv[2])
    else:
        print(f"Unknown command: {command}\n")
        _print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
