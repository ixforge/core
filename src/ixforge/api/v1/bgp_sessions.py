"""BGP session endpoints: CRUD, admin state update, delete."""

import uuid
from typing import Any

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from ixforge.api.deps import AdminUser, CurrentUser, DBSession, IXPId
from ixforge.enums import BGPAdminState
from ixforge.exceptions import ForbiddenError
from ixforge.models.trunk import Trunk, TrunkVLAN
from ixforge.models.user import UserRole
from ixforge.schemas.bgp_session import BGPSessionCreate, BGPSessionRead
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.services import bgp_sessions as bgp_svc

bgp_sessions_router = APIRouter(prefix="/bgp-sessions", tags=["bgp-sessions"])


class BGPAdminStateUpdate(BaseModel):
    admin_state: BGPAdminState


@bgp_sessions_router.post("", response_model=BGPSessionRead, status_code=201)
async def create_bgp_session(
    body: BGPSessionCreate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> dict[str, Any]:
    """Create a new BGP session."""
    bgp = await bgp_svc.create(db, ixp_id, body)
    return await bgp_svc.to_read(db, bgp)


@bgp_sessions_router.get("", response_model=CursorPage[BGPSessionRead])
async def list_bgp_sessions(
    db: DBSession,
    ixp_id: IXPId,
    user: CurrentUser,
    route_server_id: uuid.UUID = Query(),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CursorPage[BGPSessionRead]:
    """List BGP sessions for a route server."""
    params = CursorParams(cursor=cursor, limit=limit)

    if user.role == UserRole.member:
        if user.member_id is None:
            raise ForbiddenError("Member user without assigned member cannot access BGP sessions")
        return await bgp_svc.list_sessions_for_member(db, ixp_id, route_server_id, user.member_id, params)

    return await bgp_svc.list_sessions(db, ixp_id, route_server_id, params)


@bgp_sessions_router.get("/{session_id}", response_model=BGPSessionRead)
async def get_bgp_session(
    session_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    user: CurrentUser,
) -> dict[str, Any]:
    """Get BGP session details."""
    bgp_session = await bgp_svc.get(db, ixp_id, session_id)

    if user.role == UserRole.member:
        if user.member_id is None:
            raise ForbiddenError("Member user without assigned member cannot access BGP sessions")
        trunk_vlan = await db.get(TrunkVLAN, bgp_session.trunk_vlan_id)
        if trunk_vlan is None:
            raise ForbiddenError("You do not have access to this BGP session")
        trunk = await db.get(Trunk, trunk_vlan.trunk_id)
        if trunk is None or trunk.ixp_id != ixp_id or trunk.member_id != user.member_id:
            raise ForbiddenError("You do not have access to this BGP session")

    return await bgp_svc.to_read(db, bgp_session)


@bgp_sessions_router.patch("/{session_id}", response_model=BGPSessionRead)
async def update_bgp_session(
    session_id: uuid.UUID,
    body: BGPAdminStateUpdate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> dict[str, Any]:
    """Update BGP session admin state (up/down)."""
    bgp = await bgp_svc.update_admin_state(db, ixp_id, session_id, body.admin_state.value)
    return await bgp_svc.to_read(db, bgp)


@bgp_sessions_router.delete("/{session_id}", status_code=204)
async def delete_bgp_session(
    session_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Response:
    """Delete a BGP session."""
    await bgp_svc.delete(db, ixp_id, session_id)
    return Response(status_code=204)
