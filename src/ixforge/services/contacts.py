"""Contact service: CRUD scoped to a member."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import NotFoundError
from ixforge.models.contact import Contact
from ixforge.models.member import Member
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.contact import ContactCreate, ContactRead, ContactUpdate
from ixforge.services.base import paginate


async def create(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    member_id: uuid.UUID,
    data: ContactCreate,
) -> Contact:
    """Create a contact for a member."""
    member = await session.get(Member, member_id)
    if member is None or member.ixp_id != ixp_id:
        raise NotFoundError("Member", str(member_id))

    contact = Contact(
        ixp_id=ixp_id,
        member_id=member_id,
        name=data.name,
        email=data.email,
        phone=data.phone,
        role=data.role,
    )
    session.add(contact)
    await session.flush()
    return contact


async def get(session: AsyncSession, ixp_id: uuid.UUID, contact_id: uuid.UUID) -> Contact:
    """Get a contact by id or raise NotFoundError."""
    contact = await session.get(Contact, contact_id)
    if contact is None or contact.ixp_id != ixp_id:
        raise NotFoundError("Contact", str(contact_id))
    return contact


async def list_contacts(
    session: AsyncSession,
    member_id: uuid.UUID,
    params: CursorParams,
) -> CursorPage[ContactRead]:
    """List contacts for a specific member."""
    stmt = select(Contact).where(Contact.member_id == member_id)
    return await paginate(
        session,
        stmt,
        params,
        sort_column=Contact.created_at,
        id_column=Contact.id,
        schema=ContactRead,
    )


async def update(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    contact_id: uuid.UUID,
    data: ContactUpdate,
) -> Contact:
    """Update a contact."""
    contact = await get(session, ixp_id, contact_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    await session.flush()
    await session.refresh(contact)
    return contact


async def delete(session: AsyncSession, ixp_id: uuid.UUID, contact_id: uuid.UUID) -> None:
    """Delete a contact."""
    contact = await get(session, ixp_id, contact_id)
    await session.delete(contact)
    await session.flush()
