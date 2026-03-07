"""Member endpoints: list, create, detail, update, state transition."""

import uuid

from fastapi import APIRouter, Query, Response

from ixforge.api.deps import AdminUser, CurrentUser, DBSession, IXPId
from ixforge.exceptions import ForbiddenError
from ixforge.models.member import Member
from ixforge.models.user import UserRole
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.member import (
    ASNLookupResponse,
    MemberCreate,
    MemberRead,
    MemberStateTransition,
    MemberUpdate,
)
from ixforge.services import members as member_svc
from ixforge.services.asn_lookup import lookup

members_router = APIRouter(prefix="/members", tags=["members"])


@members_router.get("", response_model=CursorPage[MemberRead])
async def list_members(
    db: DBSession,
    ixp_id: IXPId,
    user: CurrentUser,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CursorPage[MemberRead]:
    """List members. Admins see all; members see only their own."""
    params = CursorParams(cursor=cursor, limit=limit)

    if user.role == UserRole.member:
        # Member users see only their own member record
        if user.member_id is None:
            return CursorPage(items=[], next_cursor=None, has_more=False)
        member = await member_svc.get(db, ixp_id, user.member_id)
        return CursorPage(
            items=[MemberRead.model_validate(member)],
            next_cursor=None,
            has_more=False,
        )

    return await member_svc.list_members(db, ixp_id, params)


@members_router.post("", response_model=MemberRead, status_code=201)
async def create_member(
    body: MemberCreate,
    db: DBSession,
    ixp_id: IXPId,
    admin: AdminUser,
) -> Member:
    """Create a new member (admin only)."""
    return await member_svc.create(db, ixp_id, body, actor_id=admin.id)


@members_router.get("/asn-lookup", response_model=ASNLookupResponse)
async def get_asn_name(
    db: DBSession,
    _ixp_id: IXPId,
    _user: CurrentUser,
    asn: int = Query(ge=1, le=4294967295),
) -> dict[str, object]:
    name = await lookup(db, asn)
    return {"asn": asn, "name": name}


@members_router.get("/{member_id}/asn-name", response_model=ASNLookupResponse)
async def get_member_asn_name(
    member_id: uuid.UUID, db: DBSession, ixp_id: IXPId, user: CurrentUser
) -> dict[str, object]:
    """Return ASN name for a member (best-effort, may return null)."""
    if user.role != UserRole.admin and user.member_id != member_id:
        raise ForbiddenError("You can only view your own member record")
    member = await member_svc.get(db, ixp_id, member_id)
    name = await lookup(db, member.asn)
    return {"asn": member.asn, "name": name}


@members_router.get("/{member_id}", response_model=MemberRead)
async def get_member(
    member_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    user: CurrentUser,
) -> Member:
    """Get member details."""
    if user.role != UserRole.admin and user.member_id != member_id:
        raise ForbiddenError("You can only view your own member record")
    return await member_svc.get(db, ixp_id, member_id)


@members_router.patch("/{member_id}", response_model=MemberRead)
async def update_member(
    member_id: uuid.UUID,
    body: MemberUpdate,
    db: DBSession,
    admin: AdminUser,
    ixp_id: IXPId,
) -> Member:
    """Update a member (admin only)."""
    return await member_svc.update(db, ixp_id, member_id, body, actor_id=admin.id)


@members_router.post("/{member_id}/transition", response_model=MemberRead)
async def transition_member(
    member_id: uuid.UUID,
    body: MemberStateTransition,
    db: DBSession,
    admin: AdminUser,
    ixp_id: IXPId,
) -> Member:
    """Transition a member to a new state (admin only)."""
    return await member_svc.transition(db, ixp_id, member_id, body.state, actor_id=admin.id)


@members_router.delete("/{member_id}", status_code=204)
async def delete_member(
    member_id: uuid.UUID,
    db: DBSession,
    admin: AdminUser,
    ixp_id: IXPId,
) -> Response:
    """Hard delete a terminated member (admin only)."""
    await member_svc.delete(db, ixp_id, member_id, actor_id=admin.id)
    return Response(status_code=204)
