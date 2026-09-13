"""Lectura de los prefijos que anuncia un miembro y de su historial.

Los escribe el agente por sesion BGP. Aca se leen por miembro, que es como los
pide el sitio: un miembro tiene una sesion por route server y por familia, y
todas anuncian lo mismo
"""

import uuid
from typing import Any

from sqlalchemy import Select, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.models.bgp_prefix import BGPPrefixEvent, BGPSessionPrefix
from ixforge.models.bgp_session import BGPSession
from ixforge.models.ip import IPAssignment
from ixforge.models.route_server import RouteServer
from ixforge.models.route_server_peer import RouteServerPeer
from ixforge.models.trunk import Trunk, TrunkVLAN


def _sesiones_del_miembro(ixp_id: uuid.UUID, member_id: uuid.UUID) -> Select[tuple[uuid.UUID]]:
    return (
        select(BGPSession.id)
        .join(TrunkVLAN, TrunkVLAN.id == BGPSession.trunk_vlan_id)
        .join(Trunk, Trunk.id == TrunkVLAN.trunk_id)
        .where(Trunk.member_id == member_id, BGPSession.ixp_id == ixp_id)
    )


def _peers_del_miembro(ixp_id: uuid.UUID, member_id: uuid.UUID) -> Select[tuple[uuid.UUID]]:
    """Los peers del route server que usan una IP asignada a este miembro

    El upstream del IXP no tiene sesion de miembro: su BGP lo maneja un peer.
    Se lo reconoce por la IP, que es la que tiene asignada en el IPAM
    """
    ips = (
        select(IPAssignment.address)
        .join(TrunkVLAN, TrunkVLAN.id == IPAssignment.trunk_vlan_id)
        .join(Trunk, Trunk.id == TrunkVLAN.trunk_id)
        .where(Trunk.member_id == member_id, IPAssignment.ixp_id == ixp_id)
    )
    return select(RouteServerPeer.id).where(
        RouteServerPeer.ixp_id == ixp_id,
        RouteServerPeer.peer_ip.in_(ips),
    )


def escapar_like(valor: str) -> str:
    """Neutraliza los comodines de LIKE en entrada de usuario

    Sin esto un % en el filtro trae todo y un _ hace de comodin de un caracter,
    que no es lo que alguien escribiendo un prefijo espera
    """
    return valor.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def prefijos(
    db: AsyncSession,
    ixp_id: uuid.UUID,
    member_id: uuid.UUID,
    prefix: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Los prefijos que el miembro esta anunciando ahora

    Se deduplica por prefijo: el mismo prefijo llega por las sesiones de los dos
    route servers y listarlo dos veces seria ruido
    """
    stmt = (
        select(BGPSessionPrefix)
        .where(
            or_(
                BGPSessionPrefix.bgp_session_id.in_(_sesiones_del_miembro(ixp_id, member_id)),
                BGPSessionPrefix.route_server_peer_id.in_(_peers_del_miembro(ixp_id, member_id)),
            )
        )
        .order_by(BGPSessionPrefix.prefix)
    )
    if prefix:
        stmt = stmt.where(BGPSessionPrefix.prefix.like(f"{escapar_like(prefix)}%", escape="\\"))

    vistos: dict[str, dict[str, Any]] = {}
    for fila in (await db.execute(stmt)).scalars():
        actual = vistos.get(fila.prefix)
        if actual is None:
            vistos[fila.prefix] = {
                "prefix": fila.prefix,
                "as_path": fila.as_path,
                "communities": fila.communities,
                "first_seen_at": fila.first_seen_at,
                "last_seen_at": fila.last_seen_at,
            }
            continue
        # Entre route servers se conserva lo mas reciente y el primer avistaje
        # mas viejo: es el mismo prefijo visto dos veces, no dos prefijos
        if fila.last_seen_at > actual["last_seen_at"]:
            actual["last_seen_at"] = fila.last_seen_at
            actual["as_path"] = fila.as_path
            actual["communities"] = fila.communities
        if fila.first_seen_at < actual["first_seen_at"]:
            actual["first_seen_at"] = fila.first_seen_at

    return list(vistos.values())[:limit]


async def eventos(
    db: AsyncSession,
    ixp_id: uuid.UUID,
    member_id: uuid.UUID,
    prefix: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """El historial de cambios, lo mas nuevo primero

    Cada fila dice de que route server vino. Los dos ven el mismo anuncio, asi
    que el hecho aparece dos veces; sin el nombre se lee como un duplicado sin
    sentido, y con el dice algo: si aparece en uno solo, ese es el dato
    """
    stmt = (
        select(BGPPrefixEvent, RouteServer.name)
        .outerjoin(BGPSession, BGPSession.id == BGPPrefixEvent.bgp_session_id)
        .outerjoin(
            RouteServerPeer, RouteServerPeer.id == BGPPrefixEvent.route_server_peer_id
        )
        .join(
            RouteServer,
            RouteServer.id
            == func.coalesce(BGPSession.route_server_id, RouteServerPeer.route_server_id),
        )
        .where(
            or_(
                BGPPrefixEvent.bgp_session_id.in_(_sesiones_del_miembro(ixp_id, member_id)),
                BGPPrefixEvent.route_server_peer_id.in_(_peers_del_miembro(ixp_id, member_id)),
            )
        )
        .order_by(desc(BGPPrefixEvent.occurred_at))
        .limit(limit)
    )
    if prefix:
        stmt = stmt.where(BGPPrefixEvent.prefix.like(f"{escapar_like(prefix)}%", escape="\\"))

    return [
        {
            "prefix": e.prefix,
            "event_type": e.event_type,
            "as_path": e.as_path,
            "previous_as_path": e.previous_as_path,
            "communities": e.communities,
            "previous_communities": e.previous_communities,
            "occurred_at": e.occurred_at,
            "route_server": nombre,
        }
        for e, nombre in (await db.execute(stmt)).all()
    ]
