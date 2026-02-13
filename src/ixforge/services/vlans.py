"""VLAN service: CRUD operations."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import NotFoundError
from ixforge.models.vlan import VLAN
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.vlan import VLANCreate, VLANRead, VLANUpdate
from ixforge.services.base import paginate


async def create(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    data: VLANCreate,
) -> VLAN:
    """Create a VLAN."""
    vlan = VLAN(
        ixp_id=ixp_id,
        name=data.name,
        vid=data.vid,
        type=data.type,
        description=data.description,
        extra_data=data.extra_data,
    )
    session.add(vlan)
    await session.flush()
    return vlan


async def get(session: AsyncSession, vlan_id: uuid.UUID) -> VLAN:
    """Get a VLAN by id or raise NotFoundError."""
    vlan = await session.get(VLAN, vlan_id)
    if vlan is None:
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
    vlan_id: uuid.UUID,
    data: VLANUpdate,
) -> VLAN:
    """Update a VLAN."""
    vlan = await get(session, vlan_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(vlan, field, value)
    await session.flush()
    await session.refresh(vlan)
    return vlan


async def delete(session: AsyncSession, vlan_id: uuid.UUID) -> None:
    """Delete a VLAN."""
    vlan = await get(session, vlan_id)
    await session.delete(vlan)
    await session.flush()
