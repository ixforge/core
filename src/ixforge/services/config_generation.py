"""BIRD config generation and versioning service."""

import difflib
import hashlib
import ipaddress
import re
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import BGPAdminState, MemberState, TrunkState
from ixforge.exceptions import NotFoundError, ValidationError
from ixforge.models.bgp_session import BGPSession
from ixforge.models.config import ConfigVersion
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.models.member_prefix_filter import MemberPrefixFilter
from ixforge.models.route_server import RouteServer
from ixforge.models.route_server_peer import RouteServerPeer
from ixforge.models.rpki_server import RPKIServer
from ixforge.models.trunk import Trunk, TrunkVLAN
from ixforge.services.communities import (
    BLOQUE_PUBLICO,
    RPKI_COMMUNITIES,
    member_type_community,
    peer_type_community,
)
from ixforge.services.rs_templates import get_all_templates
from ixforge.services.template_env import build_template_env

logger = structlog.get_logger()


@dataclass(frozen=True)
class PeerContext:
    """Template context for a single BGP peer.

    all_peer_ips, origin_asns y prefixes van como tuplas porque el dataclass es
    frozen: una lista mutable adentro de un contexto congelado invita a que
    alguien la modifique durante el render
    """

    slug: str
    member_name: str
    member_short_name: str
    member_type_community: int | None
    peer_ip: str
    all_peer_ips: tuple[str, ...]
    peer_asn: int
    origin_asns: tuple[int, ...]
    prefixes: tuple[str, ...] | None
    max_prefixes: int | None
    af: int


@dataclass(frozen=True)
class RSPeerContext:
    """Template context para una sesion que no pertenece a un miembro."""

    slug: str
    name: str
    description: str | None
    peer_ip: str
    peer_asn: int
    local_asn: int
    passive: bool
    peer_type: str
    peer_type_community: int | None
    mark_community: str | None
    max_prefixes: int | None
    af: int


@dataclass(frozen=True)
class RPKIServerContext:
    """Template context para un servidor RTR."""

    slug: str
    name: str
    host: str
    port: int
    transport: str
    refresh_time: int | None
    retry_time: int | None
    expire_time: int | None


@dataclass(frozen=True)
class RouteServerContext:
    """Template context for the route server itself."""

    name: str
    ip_v4: str | None
    ip_v6: str | None
    asn: int
    router_id: str
    passive_sessions: bool
    rpki_enabled: bool
    rpki_servers: tuple[RPKIServerContext, ...]
    # intervalos de (rsasn, *) que el export NO borra, porque son publicos: el
    # bloque de tipos mas las marcas que el operador haya configurado. Solo
    # entran las marcas del ASN del IXP, las otras ni caen en (rsasn, *)
    communities_conservadas: tuple[tuple[int, int], ...]


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


async def _member_vlan_ips(
    session: AsyncSession, af: int
) -> dict[tuple[uuid.UUID, uuid.UUID], list[str]]:
    """Todas las IPs de cada miembro en cada VLAN, para el chequeo de next hop

    Clave: (member_id, vlan_id). El chequeo euro-ix necesita el conjunto completo
    del miembro y no solo la IP de la sesion que se esta renderizando, o el
    propio segundo puerto del miembro queda marcado como next hop hijacking
    """
    stmt = (
        select(Trunk.member_id, TrunkVLAN.vlan_id, IPAssignment.address)
        .join(TrunkVLAN, IPAssignment.trunk_vlan_id == TrunkVLAN.id)
        .join(Trunk, TrunkVLAN.trunk_id == Trunk.id)
        .join(IPPool, IPAssignment.pool_id == IPPool.id)
        .where(IPPool.af == af, Trunk.state == TrunkState.active)
        .order_by(IPAssignment.address)
    )
    result = await session.execute(stmt)
    out: dict[tuple[uuid.UUID, uuid.UUID], list[str]] = {}
    for member_id, vlan_id, address in result.all():
        out.setdefault((member_id, vlan_id), []).append(str(address))
    return out


async def _prefix_filters(
    session: AsyncSession, member_ids: set[uuid.UUID], af: int
) -> dict[uuid.UUID, MemberPrefixFilter]:
    """Filtros de prefijos de esos miembros para esa familia, en una sola consulta"""
    if not member_ids:
        return {}
    stmt = select(MemberPrefixFilter).where(
        MemberPrefixFilter.member_id.in_(member_ids),
        MemberPrefixFilter.af == af,
    )
    result = await session.execute(stmt)
    return {pf.member_id: pf for pf in result.scalars()}


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
        select(BGPSession, Member, ip_subq.c.address, TrunkVLAN.vlan_id)
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

    member_ids = {member.id for _s, member, _ip, _vlan in rows}
    ips_by_member_vlan = await _member_vlan_ips(session, af)
    filters_by_member = await _prefix_filters(session, member_ids, af)

    peers: list[PeerContext] = []
    for bgp_session, member, peer_ip, vlan_id in rows:
        peer_ip_str = str(peer_ip)
        pf = filters_by_member.get(member.id)

        # Las dos listas se tratan distinto a proposito. origin_asns cae al ASN
        # del miembro tanto si no hay fila como si la lista esta vacia, que es el
        # lado restrictivo: un allas vacio marcaria todas sus rutas como
        # filtradas por origen. prefixes distingue NULL de lista vacia, porque
        # colapsarlos seria fail-open
        origin_asns = (
            tuple(pf.origin_asns) if pf is not None and pf.origin_asns else (member.asn,)
        )
        prefixes = (
            tuple(pf.prefixes) if pf is not None and pf.prefixes is not None else None
        )
        all_ips = ips_by_member_vlan.get((member.id, vlan_id), [peer_ip_str])

        peers.append(
            PeerContext(
                slug=_build_peer_slug(member.short_name, peer_ip_str, af),
                member_name=member.name,
                member_short_name=member.short_name,
                member_type_community=member_type_community(member.member_type),
                peer_ip=peer_ip_str,
                all_peer_ips=tuple(all_ips),
                peer_asn=member.asn,
                origin_asns=origin_asns,
                prefixes=prefixes,
                max_prefixes=bgp_session.max_prefixes,
                af=af,
            )
        )
    return peers


async def build_rs_peers(
    session: AsyncSession, route_server_id: uuid.UUID, af: int
) -> list[RSPeerContext]:
    """Peers de upstream, colectores y especiales de un route server

    La familia se deriva de peer_ip: el modelo no guarda af para no tener dos
    fuentes de verdad
    """
    ixp_asn_stmt = (
        select(IXP.asn)
        .join(RouteServer, RouteServer.ixp_id == IXP.id)
        .where(RouteServer.id == route_server_id)
    )
    ixp_asn = (await session.execute(ixp_asn_stmt)).scalar_one()

    stmt = (
        select(RouteServerPeer)
        .where(
            RouteServerPeer.route_server_id == route_server_id,
            RouteServerPeer.admin_state == BGPAdminState.up,
        )
        .order_by(RouteServerPeer.peer_asn, RouteServerPeer.peer_ip)
    )
    result = await session.execute(stmt)

    peers: list[RSPeerContext] = []
    for peer in result.scalars():
        peer_ip = str(peer.peer_ip)
        if ipaddress.ip_address(peer_ip).version != af:
            continue

        peers.append(
            RSPeerContext(
                slug=_build_peer_slug(peer.name, peer_ip, af),
                name=peer.name,
                description=peer.description,
                peer_ip=peer_ip,
                peer_asn=peer.peer_asn,
                local_asn=peer.local_asn if peer.local_asn is not None else ixp_asn,
                passive=peer.passive,
                peer_type=peer.peer_type.value,
                peer_type_community=peer_type_community(peer.peer_type),
                mark_community=peer.mark_community,
                max_prefixes=peer.max_prefixes,
                af=af,
            )
        )
    return peers


async def build_rs_context(session: AsyncSession, rs: RouteServer, ixp_asn: int) -> RouteServerContext:
    """Build the route server template context from the model."""
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

    rpki_stmt = (
        select(RPKIServer)
        .where(
            RPKIServer.ixp_id == rs.ixp_id,
            or_(
                RPKIServer.route_server_id.is_(None),
                RPKIServer.route_server_id == rs.id,
            ),
        )
        .order_by(RPKIServer.name)
    )
    rpki_result = await session.execute(rpki_stmt)
    rpki_servers = tuple(
        RPKIServerContext(
            slug=_sanitize_symbol(srv.name)[:PEER_SLUG_MAX_LEN],
            name=srv.name,
            host=srv.host,
            port=srv.port,
            transport=srv.transport.value,
            refresh_time=srv.refresh_time,
            retry_time=srv.retry_time,
            expire_time=srv.expire_time,
        )
        for srv in rpki_result.scalars()
    )

    marcas_stmt = select(RouteServerPeer.mark_community).where(
        RouteServerPeer.route_server_id == rs.id,
        RouteServerPeer.mark_community.is_not(None),
    )
    marcas_result = await session.execute(marcas_stmt)
    conservadas: set[tuple[int, int]] = {BLOQUE_PUBLICO}
    for marca in marcas_result.scalars():
        asn_marca, _, valor = str(marca).partition(":")
        # una marca de otro ASN no cae dentro de (rsasn, *), no hay que exceptuarla
        if asn_marca.isdigit() and int(asn_marca) == ixp_asn and valor.isdigit():
            conservadas.add((int(valor), int(valor)))

    return RouteServerContext(
        name=rs.name,
        ip_v4=rs.ip_v4,
        ip_v6=rs.ip_v6,
        asn=ixp_asn,
        router_id=router_id,
        passive_sessions=rs.passive_sessions,
        rpki_enabled=rs.rpki_enabled,
        rpki_servers=tuple(_deduplicate_slugs([list(rpki_servers)])[0]),
        communities_conservadas=tuple(sorted(conservadas)),
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

    # Un solo render con las dos familias adentro. Coordinar dos renders con una
    # variable include_globals que los templates tienen que respetar por
    # convencion es la misma clase de bug que produjo el protocol device
    # duplicado en produccion
    v4_peers, v6_peers, v4_rs_peers, v6_rs_peers = _deduplicate_slugs(
        [
            await build_peers(session, route_server_id, af=4),
            await build_peers(session, route_server_id, af=6),
            await build_rs_peers(session, route_server_id, af=4),
            await build_rs_peers(session, route_server_id, af=6),
        ]
    )

    template = env.get_template("bird.conf.j2")
    combined = template.render(
        route_server=rs_context,
        peers_v4=v4_peers,
        peers_v6=v6_peers,
        rs_peers_v4=v4_rs_peers,
        rs_peers_v6=v6_rs_peers,
        generated_at=generated_at_str,
        rpki_communities=RPKI_COMMUNITIES,
        config_hash="",
    )
    config_hash = hashlib.sha256(combined.encode()).hexdigest()

    # El hash se calcula sobre el render con el campo vacio y despues se rellena.
    # Sin esto la cabecera queda en blanco en todos los route servers y no hay
    # forma de mirar un bird.conf y saber de que version salio. El agent nunca
    # recalcula el hash sobre el contenido, se lo cree a la API, asi que
    # rellenarlo no rompe el reporte de config aplicada
    combined = combined.replace("# Config hash: ", f"# Config hash: {config_hash}", 1)

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
