"""RouteServerVLAN service."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import ConflictError, NotFoundError
from ixforge.models.route_server import RouteServer
from ixforge.models.route_server_vlan import RouteServerVLAN
from ixforge.models.vlan import VLAN
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.route_server_vlan import RouteServerVLANRead
from ixforge.services.base import paginate


async def list_vlans(
    session: AsyncSession, ixp_id: uuid.UUID, rs_id: uuid.UUID, params: CursorParams
) -> CursorPage[RouteServerVLANRead]:
    stmt = select(RouteServerVLAN).where(
        RouteServerVLAN.route_server_id == rs_id,
        RouteServerVLAN.ixp_id == ixp_id,
    )
    return await paginate(session, stmt, params, RouteServerVLAN.created_at, RouteServerVLAN.id, RouteServerVLANRead)


async def add_vlan(
    session: AsyncSession, ixp_id: uuid.UUID, rs_id: uuid.UUID, vlan_id: uuid.UUID
) -> RouteServerVLAN:
    rs = await session.get(RouteServer, rs_id)
    if rs is None or rs.ixp_id != ixp_id:
        raise NotFoundError("RouteServer", str(rs_id))
    vlan = await session.get(VLAN, vlan_id)
    if vlan is None or vlan.ixp_id != ixp_id:
        raise NotFoundError("VLAN", str(vlan_id))
    assoc = RouteServerVLAN(ixp_id=ixp_id, route_server_id=rs_id, vlan_id=vlan_id)
    session.add(assoc)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("VLAN already associated with this route server") from exc
    return assoc


async def remove_vlan(
    session: AsyncSession, ixp_id: uuid.UUID, rs_id: uuid.UUID, vlan_id: uuid.UUID
) -> None:
    assoc = await session.scalar(
        select(RouteServerVLAN).where(
            RouteServerVLAN.ixp_id == ixp_id,
            RouteServerVLAN.route_server_id == rs_id,
            RouteServerVLAN.vlan_id == vlan_id,
        )
    )
    if assoc is None:
        raise NotFoundError("RouteServerVLAN", f"rs={rs_id} vlan={vlan_id}")
    await session.delete(assoc)
    await session.flush()
