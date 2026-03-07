"""BIRD config generation and versioning service."""

import difflib
import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import BGPAdminState, ConnectionState, MemberState
from ixforge.exceptions import NotFoundError, ValidationError
from ixforge.models.bgp_session import BGPSession
from ixforge.models.config import ConfigVersion
from ixforge.models.connection import Connection
from ixforge.models.member import Member
from ixforge.models.route_server import RouteServer
from ixforge.services.templates.loader import get_template_env, get_template_snapshots

logger = structlog.get_logger()


@dataclass(frozen=True)
class PeerContext:
    """Template context for a single BGP peer."""

    protocol_name: str
    member_name: str
    peer_ip: str
    peer_asn: int
    max_prefixes: int | None


@dataclass(frozen=True)
class RouteServerContext:
    """Template context for the route server itself."""

    name: str
    hostname: str
    ip_v4: str | None
    ip_v6: str | None
    asn: int
    router_id: str


@dataclass(frozen=True)
class DiffResult:
    """Result of comparing two config versions"""

    diff: str
    from_hash: str
    to_hash: str


def _sanitize_protocol_name(name: str, peer_ip: str) -> str:
    """Build a valid BIRD protocol name from member name and peer IP.

    BIRD protocol names must be alphanumeric plus underscores. Replace dots
    and colons in IP addresses with underscores and strip other invalid chars.
    """
    raw = f"{name}_{peer_ip}"
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", raw)
    return sanitized[:64]


async def _build_peers(
    session: AsyncSession,
    route_server_id: uuid.UUID,
    af: int,
) -> list[PeerContext]:
    """Gather active BGP sessions for the given address family and build peer contexts."""
    stmt = (
        select(BGPSession, Connection, Member)
        .join(Connection, BGPSession.connection_id == Connection.id)
        .join(Member, Connection.member_id == Member.id)
        .where(
            BGPSession.route_server_id == route_server_id,
            BGPSession.af == af,
            BGPSession.admin_state == BGPAdminState.up,
            Connection.state == ConnectionState.active,
            Member.state == MemberState.active,
        )
        .order_by(BGPSession.peer_asn, BGPSession.peer_ip)
    )
    result = await session.execute(stmt)
    rows = result.all()

    peers: list[PeerContext] = []
    for bgp_session, _connection, member in rows:
        protocol_name = _sanitize_protocol_name(member.short_name, bgp_session.peer_ip)
        peers.append(
            PeerContext(
                protocol_name=protocol_name,
                member_name=member.name,
                peer_ip=bgp_session.peer_ip,
                peer_asn=bgp_session.peer_asn,
                max_prefixes=bgp_session.max_prefixes,
            )
        )
    return peers


async def _build_rs_context(session: AsyncSession, rs: RouteServer) -> RouteServerContext:
    """Build the route server template context from the model."""
    import ipaddress

    if not rs.ip_v4 and not rs.ip_v6:
        raise ValidationError(
            f"Route server '{rs.name}' must have at least one IP (v4 or v6) to generate config"
        )

    if rs.ip_v4:
        router_id = rs.ip_v4
    elif rs.ip_v6:
        # Derivar router ID de los ultimos 4 bytes de la IPv6
        v6 = ipaddress.ip_address(rs.ip_v6)
        v6_bytes = v6.packed[-4:]
        derived = ipaddress.IPv4Address(v6_bytes)

        if (
            derived
            in (
                ipaddress.IPv4Address("0.0.0.0"),
                ipaddress.IPv4Address("255.255.255.255"),
            )
            or derived.is_multicast
            or derived.is_private
            or derived.is_loopback
            or derived.is_reserved
        ):
            raise ValidationError(
                f"Cannot derive valid BIRD router ID from IPv6 {rs.ip_v6} "
                f"(got {derived}). Assign an IPv4 address to this route server"
            )
        router_id = str(derived)

        # Validate uniqueness of derived router_id across route servers in the same IXP
        stmt = select(RouteServer.id, RouteServer.name, RouteServer.ip_v4).where(
            RouteServer.ixp_id == rs.ixp_id,
            RouteServer.id != rs.id,
            RouteServer.is_active.is_(True),
        )
        result = await session.execute(stmt)
        for _other_id, other_name, other_ip_v4 in result.all():
            if other_ip_v4 == router_id:
                raise ValidationError(
                    f"Derived router_id {router_id} from IPv6 {rs.ip_v6} "
                    f"collides with IPv4 of route server '{other_name}'. "
                    f"Assign a unique IPv4 address to this route server"
                )

    return RouteServerContext(
        name=rs.name,
        hostname=rs.hostname,
        ip_v4=rs.ip_v4,
        ip_v6=rs.ip_v6,
        asn=rs.asn,
        router_id=router_id,
    )


async def generate_config(
    session: AsyncSession,
    route_server_id: uuid.UUID,
    ixp_id: uuid.UUID,
    generated_by_id: uuid.UUID | None = None,
) -> ConfigVersion:
    """Generate BIRD config for a route server and store a new version.

    Renders both IPv4 and IPv6 configurations, combines them, computes a
    SHA-256 hash, and stores the result as a ConfigVersion row.
    """
    rs = await session.get(RouteServer, route_server_id)
    if rs is None or rs.ixp_id != ixp_id:
        raise NotFoundError("RouteServer", str(route_server_id))

    rs_context = await _build_rs_context(session, rs)
    generated_at = datetime.now(UTC)
    generated_at_str = generated_at.isoformat()

    env = get_template_env()

    v4_peers = await _build_peers(session, route_server_id, af=4)
    v6_peers = await _build_peers(session, route_server_id, af=6)

    v4_config = ""
    if rs.ip_v4:
        v4_template = env.get_template("bird_v4.conf.j2")
        v4_config = v4_template.render(
            route_server=rs_context,
            peers=v4_peers,
            generated_at=generated_at_str,
            config_hash="",
        )

    v6_config = ""
    if rs.ip_v6:
        v6_template = env.get_template("bird_v6.conf.j2")
        v6_config = v6_template.render(
            route_server=rs_context,
            peers=v6_peers,
            generated_at=generated_at_str,
            config_hash="",
        )

    combined = _combine_configs(v4_config, v6_config)
    config_hash = hashlib.sha256(combined.encode()).hexdigest()

    template_snapshot = get_template_snapshots()

    config_version = ConfigVersion(
        route_server_id=route_server_id,
        content=combined,
        config_hash=config_hash,
        template_snapshot=template_snapshot,
        generated_at=generated_at,
        generated_by_id=generated_by_id,
    )
    session.add(config_version)
    await session.flush()

    return config_version


def _combine_configs(v4_config: str, v6_config: str) -> str:
    """Combine IPv4 and IPv6 configs into a single output with section markers."""
    sections: list[str] = []
    if v4_config:
        sections.append(f"# === IPv4 Configuration ===\n{v4_config}")
    if v6_config:
        sections.append(f"# === IPv6 Configuration ===\n{v6_config}")
    return "\n\n".join(sections)


async def get_diff(
    session: AsyncSession,
    version_a_id: uuid.UUID,
    version_b_id: uuid.UUID,
    route_server_id: uuid.UUID,
) -> DiffResult:
    """Return a unified diff between two config versions."""
    version_a = await session.get(ConfigVersion, version_a_id)
    if version_a is None or version_a.route_server_id != route_server_id:
        raise NotFoundError("ConfigVersion", str(version_a_id))

    version_b = await session.get(ConfigVersion, version_b_id)
    if version_b is None or version_b.route_server_id != route_server_id:
        raise NotFoundError("ConfigVersion", str(version_b_id))

    diff_lines = difflib.unified_diff(
        version_a.content.splitlines(keepends=True),
        version_b.content.splitlines(keepends=True),
        fromfile=f"config @ {version_a.generated_at.isoformat()}",
        tofile=f"config @ {version_b.generated_at.isoformat()}",
    )
    return DiffResult(
        diff="".join(diff_lines),
        from_hash=version_a.config_hash,
        to_hash=version_b.config_hash,
    )
