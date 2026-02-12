"""BGP session endpoints: list, detail, admin state update."""

import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ixforge.api.deps import AdminUser, CurrentUser, DBSession
from ixforge.exceptions import ForbiddenError
from ixforge.models.bgp_session import BGPSession
from ixforge.models.connection import Connection
from ixforge.models.user import UserRole
from ixforge.schemas.bgp_session import BGPSessionRead
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.services import bgp_sessions as bgp_svc

bgp_sessions_router = APIRouter(prefix="/bgp-sessions", tags=["bgp-sessions"])


class BGPAdminStateUpdate(BaseModel):
    admin_state: str


@bgp_sessions_router.get("", response_model=CursorPage[BGPSessionRead])
async def list_bgp_sessions(
    db: DBSession,
    user: CurrentUser,
    route_server_id: uuid.UUID = Query(),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CursorPage[BGPSessionRead]:
    """List BGP sessions for a route server."""
    params = CursorParams(cursor=cursor, limit=limit)

    if user.role == UserRole.member:
        return await bgp_svc.list_sessions_for_member(db, route_server_id, user.member_id, params)

    return await bgp_svc.list_sessions(db, route_server_id, params)


@bgp_sessions_router.get("/{session_id}", response_model=BGPSessionRead)
async def get_bgp_session(
    session_id: uuid.UUID,
    db: DBSession,
    user: CurrentUser,
) -> BGPSession:
    """Get BGP session details."""
    bgp_session = await bgp_svc.get(db, session_id)

    if user.role == UserRole.member:
        connection = await db.get(Connection, bgp_session.connection_id)
        if connection is None or connection.member_id != user.member_id:
            raise ForbiddenError("You do not have access to this BGP session")

    return bgp_session


@bgp_sessions_router.patch("/{session_id}", response_model=BGPSessionRead)
async def update_bgp_session(
    session_id: uuid.UUID,
    body: BGPAdminStateUpdate,
    db: DBSession,
    _admin: AdminUser,
) -> BGPSession:
    """Update BGP session admin state (up/down)."""
    return await bgp_svc.update_admin_state(db, session_id, body.admin_state)
