"""Event service: audit log creation and listing."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.models.event import Event
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.event import EventRead
from ixforge.services.base import paginate


async def create_event(
    session: AsyncSession,
    *,
    ixp_id: uuid.UUID,
    event_type: str,
    actor_id: uuid.UUID | None,
    resource_type: str,
    resource_id: uuid.UUID,
    data: dict[str, Any],
) -> Event:
    """Create an audit event record."""
    event = Event(
        ixp_id=ixp_id,
        type=event_type,
        actor_id=actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
        data=data,
    )
    session.add(event)
    await session.flush()
    return event


async def list_events(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    params: CursorParams,
    *,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
) -> CursorPage[EventRead]:
    """List events with optional resource-scoped filtering."""
    stmt = select(Event).where(Event.ixp_id == ixp_id)

    if resource_type is not None:
        stmt = stmt.where(Event.resource_type == resource_type)
    if resource_id is not None:
        stmt = stmt.where(Event.resource_id == resource_id)

    return await paginate(
        session,
        stmt,
        params,
        sort_column=Event.created_at,
        id_column=Event.id,
        schema=EventRead,
    )
