"""Port service: CRUD plus member assignment/release."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import ConflictError, NotFoundError
from ixforge.models.port import Port
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.port import PortCreate, PortRead, PortUpdate
from ixforge.services.base import paginate


async def create(
    session: AsyncSession,
    data: PortCreate,
) -> Port:
    """Create a port on a switch."""
    port = Port(
        switch_id=data.switch_id,
        name=data.name,
        speed=data.speed,
        type=data.type,
        member_id=data.member_id,
        is_active=data.is_active,
        extra_data=data.extra_data,
    )
    session.add(port)
    await session.flush()
    return port


async def get(session: AsyncSession, port_id: uuid.UUID) -> Port:
    """Get a port by id or raise NotFoundError."""
    port = await session.get(Port, port_id)
    if port is None:
        raise NotFoundError("Port", str(port_id))
    return port


async def list_ports(
    session: AsyncSession,
    switch_id: uuid.UUID,
    params: CursorParams,
) -> CursorPage[PortRead]:
    """List ports on a switch with cursor-based pagination."""
    stmt = select(Port).where(Port.switch_id == switch_id)
    return await paginate(
        session,
        stmt,
        params,
        sort_column=Port.created_at,
        id_column=Port.id,
        schema=PortRead,
    )


async def update(
    session: AsyncSession,
    port_id: uuid.UUID,
    data: PortUpdate,
) -> Port:
    """Update port fields."""
    port = await get(session, port_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(port, field, value)
    await session.flush()
    return port


async def delete(session: AsyncSession, port_id: uuid.UUID) -> None:
    """Delete a port."""
    port = await get(session, port_id)
    await session.delete(port)
    await session.flush()


async def assign(
    session: AsyncSession,
    port_id: uuid.UUID,
    member_id: uuid.UUID,
) -> Port:
    """Assign a port to a member. Fails if already assigned."""
    port = await session.get(Port, port_id, with_for_update=True)
    if port is None:
        raise NotFoundError("Port", str(port_id))
    if port.member_id is not None:
        raise ConflictError(f"Port {port_id} is already assigned to member {port.member_id}")
    port.member_id = member_id
    try:
        await session.flush()
    except IntegrityError:
        raise ConflictError(f"Port {port_id} was assigned concurrently") from None
    return port


async def release(session: AsyncSession, port_id: uuid.UUID) -> Port:
    """Release a port from its current member assignment."""
    port = await get(session, port_id)
    if port.member_id is None:
        raise ConflictError(f"Port {port_id} is not assigned to any member")
    port.member_id = None
    await session.flush()
    return port
