"""Tests for Contact CRUD endpoints."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import ContactRole, MemberState, PeeringPolicy
from ixforge.models.contact import Contact
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.models.user import User


async def _create_member(db: AsyncSession, ixp: IXP) -> Member:
    m = Member(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name=f"Contact Test Net {uuid.uuid4().hex[:6]}",
        short_name=f"CT{uuid.uuid4().hex[:4]}",
        asn=64512 + hash(uuid.uuid4()) % 1000,
        state=MemberState.active,
        peering_policy=PeeringPolicy.open,
    )
    db.add(m)
    await db.flush()
    return m


class TestContactCRUD:
    async def test_create_contact(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)

        resp = await client.post(
            f"/api/v1/members/{member.id}/contacts",
            headers=auth_headers,
            json={
                "name": "John NOC",
                "email": "john@example.net",
                "phone": "+1-555-0100",
                "role": "noc",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "John NOC"
        assert body["email"] == "john@example.net"
        assert body["role"] == "noc"
        assert body["member_id"] == str(member.id)

    async def test_list_contacts(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)

        for role in ["noc", "admin", "technical"]:
            c = Contact(
                id=uuid.uuid4(),
                ixp_id=ixp.id,
                member_id=member.id,
                name=f"{role.title()} Person",
                email=f"{role}@example.net",
                role=ContactRole(role),
            )
            db_session.add(c)
        await db_session.flush()

        resp = await client.get(
            f"/api/v1/members/{member.id}/contacts",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 3

    async def test_update_contact(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        contact = Contact(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            name="Old Name",
            email="old@example.net",
            role=ContactRole.noc,
        )
        db_session.add(contact)
        await db_session.flush()

        resp = await client.patch(
            f"/api/v1/contacts/{contact.id}",
            headers=auth_headers,
            json={"name": "New Name", "role": "billing"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"
        assert resp.json()["role"] == "billing"

    async def test_delete_contact(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        contact = Contact(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            name="Delete Me",
            email="delete@example.net",
            role=ContactRole.technical,
        )
        db_session.add(contact)
        await db_session.flush()

        resp = await client.delete(
            f"/api/v1/contacts/{contact.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204

    async def test_create_contact_invalid_email_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)

        resp = await client.post(
            f"/api/v1/members/{member.id}/contacts",
            headers=auth_headers,
            json={
                "name": "Bad Email",
                "email": "not-an-email",
                "role": "noc",
            },
        )
        assert resp.status_code == 422
