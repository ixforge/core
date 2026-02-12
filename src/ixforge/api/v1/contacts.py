"""Contact endpoints: CRUD nested under members."""

import uuid

from fastapi import APIRouter, Query, Response

from ixforge.api.deps import DBSession, MemberOrAdminUser
from ixforge.models.contact import Contact
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.contact import ContactCreate, ContactRead, ContactUpdate
from ixforge.services import contacts as contact_svc

contacts_router = APIRouter(tags=["contacts"])


@contacts_router.get(
    "/members/{member_id}/contacts",
    response_model=CursorPage[ContactRead],
)
async def list_contacts(
    member_id: uuid.UUID,
    db: DBSession,
    _user: MemberOrAdminUser,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CursorPage[ContactRead]:
    """List contacts for a member."""
    params = CursorParams(cursor=cursor, limit=limit)
    return await contact_svc.list_contacts(db, member_id, params)


@contacts_router.post(
    "/members/{member_id}/contacts",
    response_model=ContactRead,
    status_code=201,
)
async def create_contact(
    member_id: uuid.UUID,
    body: ContactCreate,
    db: DBSession,
    _user: MemberOrAdminUser,
) -> Contact:
    """Create a contact for a member."""
    return await contact_svc.create(db, member_id, body)


@contacts_router.patch("/contacts/{contact_id}", response_model=ContactRead)
async def update_contact(
    contact_id: uuid.UUID,
    body: ContactUpdate,
    db: DBSession,
    _user: MemberOrAdminUser,
) -> Contact:
    """Update a contact."""
    return await contact_svc.update(db, contact_id, body)


@contacts_router.delete("/contacts/{contact_id}", status_code=204)
async def delete_contact(
    contact_id: uuid.UUID,
    db: DBSession,
    _user: MemberOrAdminUser,
) -> Response:
    """Delete a contact."""
    await contact_svc.delete(db, contact_id)
    return Response(status_code=204)
