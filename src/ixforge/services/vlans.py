"""VLAN service: CRUD operations."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import ConflictError, NotFoundError
from ixforge.models.ip import IPPool
from ixforge.models.route_server_vlan import RouteServerVLAN
from ixforge.models.trunk import TrunkVLAN
from ixforge.models.vlan import VLAN
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.vlan import VLANCreate, VLANRead, VLANUpdate
from ixforge.services import custom_fields
from ixforge.services.base import paginate


async def create(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    data: VLANCreate,
) -> VLAN:
    """Create a VLAN."""
    if data.extra_data is not None:
        await custom_fields.validate_extra_data(session, ixp_id, "vlan", data.extra_data)
    vlan = VLAN(
        ixp_id=ixp_id,
        name=data.name,
        vid=data.vid,
        type=data.type,
        description=data.description,
        extra_data=data.extra_data,
    )
    session.add(vlan)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(f"VLAN with VID {data.vid} already exists in this IXP") from exc
    return vlan


async def get(session: AsyncSession, ixp_id: uuid.UUID, vlan_id: uuid.UUID) -> VLAN:
    """Get a VLAN by id or raise NotFoundError."""
    vlan = await session.get(VLAN, vlan_id)
    if vlan is None or vlan.ixp_id != ixp_id:
        raise NotFoundError("VLAN", str(vlan_id))
    return vlan


async def list_vlans(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    params: CursorParams,
) -> CursorPage[VLANRead]:
    """List VLANs for an IXP with cursor-based pagination."""
    stmt = select(VLAN).where(VLAN.ixp_id == ixp_id)
    return await paginate(
        session,
        stmt,
        params,
        sort_column=VLAN.created_at,
        id_column=VLAN.id,
        schema=VLANRead,
    )


async def update(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    vlan_id: uuid.UUID,
    data: VLANUpdate,
) -> VLAN:
    """Update a VLAN."""
    vlan = await get(session, ixp_id, vlan_id)
    update_fields = data.model_dump(exclude_unset=True)
    if "extra_data" in update_fields and update_fields["extra_data"] is not None:
        await custom_fields.validate_extra_data(session, ixp_id, "vlan", update_fields["extra_data"])
    for field, value in update_fields.items():
        setattr(vlan, field, value)
    await session.flush()
    await session.refresh(vlan)
    return vlan


async def delete(session: AsyncSession, ixp_id: uuid.UUID, vlan_id: uuid.UUID) -> None:
    """Delete a VLAN."""
    vlan = await get(session, ixp_id, vlan_id)

    has_pool = await session.scalar(
        select(IPPool.id).where(IPPool.vlan_id == vlan_id).limit(1)
    )
    if has_pool is not None:
        raise ConflictError("Cannot delete VLAN: IP pools are still associated")

    has_tv = await session.scalar(
        select(TrunkVLAN.id).where(TrunkVLAN.vlan_id == vlan_id).limit(1)
    )
    if has_tv is not None:
        raise ConflictError("Cannot delete VLAN: trunks are still using it")

    has_rs_vlan = await session.scalar(
        select(RouteServerVLAN.id).where(RouteServerVLAN.vlan_id == vlan_id).limit(1)
    )
    if has_rs_vlan is not None:
        raise ConflictError("Cannot delete VLAN: route servers are still associated. Remove RS-VLAN associations first")

    await session.delete(vlan)
    await session.flush()
