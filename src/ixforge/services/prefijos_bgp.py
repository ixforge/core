"""Lectura de los prefijos que anuncia un miembro y de su historial.

Los escribe el agente por sesion BGP. Aca se leen por miembro, que es como los
pide el sitio: un miembro tiene una sesion por route server y por familia, y
todas anuncian lo mismo
"""

import uuid
from typing import Any

from sqlalchemy import Select, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.models.bgp_prefix import BGPPrefixEvent, BGPSessionPrefix
from ixforge.models.bgp_session import BGPSession
from ixforge.models.trunk import Trunk, TrunkVLAN


def _sesiones_del_miembro(ixp_id: uuid.UUID, member_id: uuid.UUID) -> Select[tuple[uuid.UUID]]:
    return (
        select(BGPSession.id)
        .join(TrunkVLAN, TrunkVLAN.id == BGPSession.trunk_vlan_id)
        .join(Trunk, Trunk.id == TrunkVLAN.trunk_id)
        .where(Trunk.member_id == member_id, BGPSession.ixp_id == ixp_id)
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
        .where(BGPSessionPrefix.bgp_session_id.in_(_sesiones_del_miembro(ixp_id, member_id)))
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
                "first_seen_at": fila.first_seen_at,
                "last_seen_at": fila.last_seen_at,
            }
            continue
        # Entre route servers se conserva lo mas reciente y el primer avistaje
        # mas viejo: es el mismo prefijo visto dos veces, no dos prefijos
        if fila.last_seen_at > actual["last_seen_at"]:
            actual["last_seen_at"] = fila.last_seen_at
            actual["as_path"] = fila.as_path
        if fila.first_seen_at < actual["first_seen_at"]:
            actual["first_seen_at"] = fila.first_seen_at

    return list(vistos.values())[:limit]


async def eventos(
    db: AsyncSession,
    ixp_id: uuid.UUID,
    member_id: uuid.UUID,
    prefix: str | None = None,
    limit: int = 100,
) -> list[BGPPrefixEvent]:
    """El historial de cambios, lo mas nuevo primero"""
    stmt = (
        select(BGPPrefixEvent)
        .where(BGPPrefixEvent.bgp_session_id.in_(_sesiones_del_miembro(ixp_id, member_id)))
        .order_by(desc(BGPPrefixEvent.occurred_at))
        .limit(limit)
    )
    if prefix:
        stmt = stmt.where(BGPPrefixEvent.prefix.like(f"{escapar_like(prefix)}%", escape="\\"))

    return list((await db.execute(stmt)).scalars())
