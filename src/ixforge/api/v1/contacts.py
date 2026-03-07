"""Contact endpoints: CRUD nested under members."""

import uuid

from fastapi import APIRouter, Query, Response

from ixforge.api.deps import CurrentUser, DBSession, IXPId
from ixforge.exceptions import ForbiddenError
from ixforge.models.contact import Contact
from ixforge.models.user import User, UserRole
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.contact import ContactCreate, ContactRead, ContactUpdate
from ixforge.services import contacts as contact_svc

contacts_router = APIRouter(tags=["contacts"])


def _check_member_access(user: User, member_id: uuid.UUID) -> None:
    """Verify that a non-admin user can only access their own member's data."""
    if user.role == UserRole.admin:
        return
    if user.member_id != member_id:
        raise ForbiddenError("You can only access contacts for your own member")


@contacts_router.get(
    "/members/{member_id}/contacts",
    response_model=CursorPage[ContactRead],
)
async def list_contacts(
    member_id: uuid.UUID,
    db: DBSession,
    user: CurrentUser,
    ixp_id: IXPId,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CursorPage[ContactRead]:
    """List contacts for a member."""
    _check_member_access(user, member_id)
    params = CursorParams(cursor=cursor, limit=limit)
    return await contact_svc.list_contacts(db, ixp_id, member_id, params)


@contacts_router.post(
    "/members/{member_id}/contacts",
    response_model=ContactRead,
    status_code=201,
)
async def create_contact(
    member_id: uuid.UUID,
    body: ContactCreate,
    db: DBSession,
    ixp_id: IXPId,
    user: CurrentUser,
) -> Contact:
    """Create a contact for a member."""
    _check_member_access(user, member_id)
    return await contact_svc.create(db, ixp_id, member_id, body)


@contacts_router.patch("/contacts/{contact_id}", response_model=ContactRead)
async def update_contact(
    contact_id: uuid.UUID,
    body: ContactUpdate,
    db: DBSession,
    user: CurrentUser,
    ixp_id: IXPId,
) -> Contact:
    """Update a contact."""
    contact = await contact_svc.get(db, ixp_id, contact_id)
    _check_member_access(user, contact.member_id)
    return await contact_svc.update(db, ixp_id, contact_id, body)


@contacts_router.delete("/contacts/{contact_id}", status_code=204)
async def delete_contact(
    contact_id: uuid.UUID,
    db: DBSession,
    user: CurrentUser,
    ixp_id: IXPId,
) -> Response:
    """Delete a contact."""
    contact = await contact_svc.get(db, ixp_id, contact_id)
    _check_member_access(user, contact.member_id)
    await contact_svc.delete(db, ixp_id, contact_id)
    return Response(status_code=204)
