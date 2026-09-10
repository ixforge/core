"""Filtros de prefijos y ASN de origen por miembro y familia."""

import ipaddress
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import NotFoundError, ValidationError
from ixforge.models.bgp_session import BGPSession
from ixforge.models.member import Member
from ixforge.models.member_prefix_filter import MemberPrefixFilter
from ixforge.models.trunk import Trunk, TrunkVLAN
from ixforge.schemas.member_prefix_filter import MemberPrefixFilterWrite


def _validate_af(af: int) -> int:
    if af not in (4, 6):
        raise ValidationError(f"familia invalida: {af}, se espera 4 o 6")
    return af


def _validate_prefix_family(prefixes: list[str] | None, af: int) -> None:
    """Un prefijo de la familia equivocada es un error del operador

    Dejarlo pasar generaria un allnet que BIRD rechaza o, peor, que no matchea
    nunca y filtra todo lo del miembro
    """
    if prefixes is None:
        return
    for prefix in prefixes:
        try:
            network = ipaddress.ip_network(prefix, strict=False)
        except ValueError as exc:
            raise ValidationError(f"prefijo invalido: {prefix}") from exc
        if network.version != af:
            raise ValidationError(
                f"el prefijo {prefix} es IPv{network.version} y el filtro es IPv{af}"
            )


async def _assert_member(
    session: AsyncSession, ixp_id: uuid.UUID, member_id: uuid.UUID
) -> Member:
    member = await session.get(Member, member_id)
    if member is None or member.ixp_id != ixp_id:
        raise NotFoundError("Member", str(member_id))
    return member


async def _defer_for_every_route_server(
    session: AsyncSession, member_id: uuid.UUID, triggered_by: str
) -> None:
    """El filtro es del miembro, asi que afecta a todos los route servers donde peerea

    Se deduplica: un miembro con sesiones v4 y v6 contra el mismo RS produce
    una sola regeneracion
    """
    stmt = (
        select(BGPSession.route_server_id)
        .join(TrunkVLAN, BGPSession.trunk_vlan_id == TrunkVLAN.id)
        .join(Trunk, TrunkVLAN.trunk_id == Trunk.id)
        .where(Trunk.member_id == member_id)
        .distinct()
    )
    result = await session.execute(stmt)

    from ixforge.tasks.config import defer_rs_config_regeneration

    for (route_server_id,) in result.all():
        await defer_rs_config_regeneration(route_server_id, triggered_by)


async def get(
    session: AsyncSession, ixp_id: uuid.UUID, member_id: uuid.UUID, af: int
) -> MemberPrefixFilter:
    _validate_af(af)
    await _assert_member(session, ixp_id, member_id)
    stmt = select(MemberPrefixFilter).where(
        MemberPrefixFilter.member_id == member_id,
        MemberPrefixFilter.af == af,
    )
    pf = (await session.execute(stmt)).scalar_one_or_none()
    if pf is None:
        raise NotFoundError("MemberPrefixFilter", f"{member_id}/{af}")
    return pf


async def upsert(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    member_id: uuid.UUID,
    af: int,
    data: MemberPrefixFilterWrite,
) -> MemberPrefixFilter:
    """Crea o reemplaza la unica fila (member_id, af)"""
    _validate_af(af)
    await _assert_member(session, ixp_id, member_id)
    _validate_prefix_family(data.prefixes, af)

    stmt = select(MemberPrefixFilter).where(
        MemberPrefixFilter.member_id == member_id,
        MemberPrefixFilter.af == af,
    )
    pf = (await session.execute(stmt)).scalar_one_or_none()

    if pf is None:
        pf = MemberPrefixFilter(ixp_id=ixp_id, member_id=member_id, af=af)
        session.add(pf)

    pf.origin_asns = data.origin_asns
    pf.prefixes = data.prefixes
    pf.as_set = data.as_set
    pf.source = data.source
    pf.last_updated_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(pf)

    await _defer_for_every_route_server(session, member_id, "prefix_filter.updated")
    return pf


async def delete(
    session: AsyncSession, ixp_id: uuid.UUID, member_id: uuid.UUID, af: int
) -> None:
    pf = await get(session, ixp_id, member_id, af)
    await session.delete(pf)
    await session.flush()

    await _defer_for_every_route_server(session, member_id, "prefix_filter.deleted")
