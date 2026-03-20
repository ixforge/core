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
    from sqlalchemy import func, select

    from ixforge.database import get_session_factory
    from ixforge.models.ixp import IXP
    from ixforge.models.user import User, UserRole
    from ixforge.services.auth import hash_password

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Verify at least one IXP exists
        ixp_count = await session.scalar(select(func.count()).select_from(IXP))
        if not ixp_count:
            print("Error: no IXP configured. Run setup via the web UI first.")
            sys.exit(1)

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
    )


_COMMANDS = {
    "run": "Start the API server",
    "ui": "Start the admin portal (port 8001)",
    "worker": "Start background task workers",
    "upgrade": "Run database migrations (alembic upgrade head)",
    "createsuperuser": "Create an admin user",
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
