"""Event endpoints: list audit events."""

import uuid

from fastapi import APIRouter, Query

from ixforge.api.deps import CurrentUser, DBSession, IXPId
from ixforge.models.user import UserRole
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.event import EventRead
from ixforge.services import events as event_svc

events_router = APIRouter(prefix="/events", tags=["events"])


@events_router.get("", response_model=CursorPage[EventRead])
async def list_events(
    db: DBSession,
    ixp_id: IXPId,
    user: CurrentUser,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    resource_type: str | None = Query(default=None),
    resource_id: uuid.UUID | None = Query(default=None),
) -> CursorPage[EventRead]:
    """List audit events.

    Admins see all events; member users see events for their own
    member resource only.
    """
    params = CursorParams(cursor=cursor, limit=limit)

    # Member users can only see events on their own member resource.
    effective_resource_type = resource_type
    effective_resource_id = resource_id

    if user.role != UserRole.admin:
        effective_resource_type = "member"
        effective_resource_id = user.member_id

    return await event_svc.list_events(
        db,
        ixp_id,
        params,
        resource_type=effective_resource_type,
        resource_id=effective_resource_id,
    )
