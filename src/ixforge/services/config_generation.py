"""BIRD config generation and versioning service."""

import difflib
import hashlib
import re
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import BGPAdminState, MemberState, TrunkState
from ixforge.exceptions import NotFoundError, ValidationError
from ixforge.models.bgp_session import BGPSession
from ixforge.models.config import ConfigVersion
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.models.route_server import RouteServer
from ixforge.models.trunk import Trunk, TrunkVLAN
from ixforge.services.rs_templates import get_all_templates
from ixforge.services.template_env import build_template_env

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
    ip_v4: str | None
    ip_v6: str | None
    asn: int
    router_id: str


@dataclass(frozen=True)
class DiffResult:
    """Result of comparing two config versions"""

    diff: str
    from_hash: str | None
    to_hash: str


# BIRD limita los simbolos a 64 caracteres. El patron euro-ix deriva cinco
# simbolos del mismo slug (t_, pb_, pp_, f_import_, f_export_) y el prefijo
# mas largo mide 9, asi que el slug no puede pasar de 55
PEER_SLUG_MAX_LEN = 55


def _sanitize_symbol(value: str) -> str:
    """Deja solo los caracteres que BIRD acepta en un simbolo"""
    return re.sub(r"[^a-zA-Z0-9_]", "_", value)


def _build_peer_slug(short_name: str, peer_ip: str, af: int) -> str:
    """Base alfanumerica de la que salen todos los simbolos BIRD de un peer

    La IP y la familia van al final y NO se truncan nunca: son lo unico que
    distingue dos sesiones del mismo miembro. Lo que se recorta es el nombre.
    Truncar el string completo, que es lo obvio, borra justo la parte que da
    unicidad: dos peers con nombre largo colapsan en el mismo simbolo y BIRD
    rechaza el config con "Symbol already defined"
    """
    tail = _sanitize_symbol(f"_{peer_ip}_v{af}")
    head = _sanitize_symbol(short_name)
    budget = max(PEER_SLUG_MAX_LEN - len(tail), 0)
    return (head[:budget] + tail)[:PEER_SLUG_MAX_LEN]


def _deduplicate_slugs(groups: list[list[Any]]) -> list[list[Any]]:
    """Unicidad de simbolos sobre TODO el config, no por familia

    BIRD tiene un unico namespace de simbolos por daemon. Antes v4 y v6 corrian
    en daemons separados y podian repetir nombres sin problema; ahora comparten
    archivo. Desambiguar dentro de build_peers, que se llama una vez por familia,
    deja pasar las colisiones cruzadas
    """
    seen: set[str] = set()
    out: list[list[Any]] = []
    for group in groups:
        new_group = []
        for ctx in group:
            slug = ctx.slug
            base = slug
            counter = 2
            while slug in seen:
                suffix = f"_{counter}"
                slug = base[: PEER_SLUG_MAX_LEN - len(suffix)] + suffix
                counter += 1
            seen.add(slug)
            new_group.append(ctx if slug == ctx.slug else replace(ctx, slug=slug))
        out.append(new_group)
    return out


async def build_peers(
    session: AsyncSession,
    route_server_id: uuid.UUID,
    af: int,
) -> list[PeerContext]:
    """Gather active BGP sessions for the given address family and build peer contexts."""
    # Use DISTINCT ON subquery to avoid duplicates when a trunk_vlan has multiple IPs of the same AF
    ip_subq = (
        select(
            IPAssignment.trunk_vlan_id,
            IPAssignment.address,
            IPPool.af,
        )
        .join(IPPool, IPAssignment.pool_id == IPPool.id)
        .distinct(IPAssignment.trunk_vlan_id, IPPool.af)
        .order_by(IPAssignment.trunk_vlan_id, IPPool.af, IPAssignment.address)
        .subquery()
    )

    stmt = (
        select(BGPSession, Member, ip_subq.c.address)
        .join(TrunkVLAN, BGPSession.trunk_vlan_id == TrunkVLAN.id)
        .join(Trunk, TrunkVLAN.trunk_id == Trunk.id)
        .join(Member, Trunk.member_id == Member.id)
        .join(
            ip_subq,
            (BGPSession.trunk_vlan_id == ip_subq.c.trunk_vlan_id)
            & (ip_subq.c.af == af),
        )
        .where(
            BGPSession.route_server_id == route_server_id,
            BGPSession.af == af,
            BGPSession.admin_state == BGPAdminState.up,
            Trunk.state == TrunkState.active,
            Member.state == MemberState.active,
        )
        .order_by(Member.asn, ip_subq.c.address)
    )
    result = await session.execute(stmt)
    rows = result.all()

    seen_names: set[str] = set()
    peers: list[PeerContext] = []
    for bgp_session, member, peer_ip in rows:
        peer_ip_str = str(peer_ip)
        protocol_name = _build_peer_slug(member.short_name, peer_ip_str, af)
        # La unicidad definitiva la da _deduplicate_slugs sobre todo el config
        base = protocol_name
        counter = 2
        while protocol_name in seen_names:
            suffix = f"_{counter}"
            protocol_name = base[: PEER_SLUG_MAX_LEN - len(suffix)] + suffix
            counter += 1
        seen_names.add(protocol_name)
        peers.append(
            PeerContext(
                protocol_name=protocol_name,
                member_name=member.name,
                peer_ip=peer_ip_str,
                peer_asn=member.asn,
                max_prefixes=bgp_session.max_prefixes,
            )
        )
    return peers


async def build_rs_context(session: AsyncSession, rs: RouteServer, ixp_asn: int) -> RouteServerContext:
    """Build the route server template context from the model."""
    import ipaddress

    if not rs.ip_v4 and not rs.ip_v6:
        raise ValidationError(
            f"Route server '{rs.name}' must have at least one IP (v4 or v6) to generate config"
        )

    if rs.ip_v4:
        router_id = rs.ip_v4
    elif rs.ip_v6:
        # Derive router ID from the last 4 bytes of the IPv6 address
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
        ip_v4=rs.ip_v4,
        ip_v6=rs.ip_v6,
        asn=ixp_asn,
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

    ixp = await session.get(IXP, ixp_id)
    if ixp is None:
        raise NotFoundError("IXP", str(ixp_id))

    rs_context = await build_rs_context(session, rs, ixp.asn)
    generated_at = datetime.now(UTC)
    generated_at_str = generated_at.isoformat()

    env = await build_template_env(session, ixp_id)

    v4_peers = await build_peers(session, route_server_id, af=4)
    v6_peers = await build_peers(session, route_server_id, af=6)

    v4_config = ""
    if rs.ip_v4:
        v4_template = env.get_template("bird_v4.conf.j2")
        v4_config = v4_template.render(
            route_server=rs_context,
            peers=v4_peers,
            generated_at=generated_at_str,
            config_hash="",
            include_globals=True,
        )

    v6_config = ""
    if rs.ip_v6:
        v6_template = env.get_template("bird_v6.conf.j2")
        # Un solo daemon BIRD carga ambas familias: los globals (log, router id,
        # device, funciones) deben aparecer una sola vez en el config combinado
        v6_config = v6_template.render(
            route_server=rs_context,
            peers=v6_peers,
            generated_at=generated_at_str,
            config_hash="",
            include_globals=not bool(rs.ip_v4),
        )

    combined = _combine_configs(v4_config, v6_config)
    config_hash = hashlib.sha256(combined.encode()).hexdigest()

    template_snapshot = await get_all_templates(session, ixp_id)

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
    version_a_id: uuid.UUID | None,
    version_b_id: uuid.UUID,
    route_server_id: uuid.UUID,
) -> DiffResult:
    """Return a unified diff between two config versions.

    Si ``version_a_id`` es None, se diffea contra la version inmediatamente
    anterior a ``version_b`` del mismo route server (o contra vacio si no hay
    anterior). Asi el boton 'Ver Diff' del portal, que solo pasa ``to``, funciona
    """
    version_b = await session.get(ConfigVersion, version_b_id)
    if version_b is None or version_b.route_server_id != route_server_id:
        raise NotFoundError("ConfigVersion", str(version_b_id))

    if version_a_id is not None:
        version_a = await session.get(ConfigVersion, version_a_id)
        if version_a is None or version_a.route_server_id != route_server_id:
            raise NotFoundError("ConfigVersion", str(version_a_id))
    else:
        stmt = (
            select(ConfigVersion)
            .where(
                ConfigVersion.route_server_id == route_server_id,
                ConfigVersion.generated_at < version_b.generated_at,
            )
            .order_by(ConfigVersion.generated_at.desc())
            .limit(1)
        )
        version_a = (await session.execute(stmt)).scalar_one_or_none()

    from_content = version_a.content if version_a is not None else ""
    from_label = (
        f"config @ {version_a.generated_at.isoformat()}" if version_a is not None else "empty"
    )
    diff_lines = difflib.unified_diff(
        from_content.splitlines(keepends=True),
        version_b.content.splitlines(keepends=True),
        fromfile=from_label,
        tofile=f"config @ {version_b.generated_at.isoformat()}",
    )
    return DiffResult(
        diff="".join(diff_lines),
        from_hash=version_a.config_hash if version_a is not None else None,
        to_hash=version_b.config_hash,
    )
