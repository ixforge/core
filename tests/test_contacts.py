"""Tests for Contact CRUD endpoints."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import ContactRole, MemberState, PeeringPolicy
from ixforge.models.contact import Contact
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.models.user import User, UserRole
from ixforge.services.auth import create_access_token, hash_password


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

    async def test_create_contact_nonexistent_member_returns_404(
        self,
        client: AsyncClient,
        auth_headers: dict,
        ixp: IXP,
    ):
        """Creating a contact for a member_id that doesn't exist should return 404"""
        bad_member_id = uuid.uuid4()
        resp = await client.post(
            f"/api/v1/members/{bad_member_id}/contacts",
            headers=auth_headers,
            json={
                "name": "Ghost Contact",
                "email": "ghost@example.net",
                "role": "noc",
            },
        )
        assert resp.status_code == 404


async def _create_member_user(
    db: AsyncSession, member_id: uuid.UUID | None = None
) -> tuple[User, dict[str, str]]:
    """Create a member-role user and return (user, auth_headers)"""
    user = User(
        id=uuid.uuid4(),
        email=f"member-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password=hash_password("testpass123"),
        full_name="Test Member User",
        role=UserRole.member,
        member_id=member_id,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    token = create_access_token(subject=str(user.id))
    headers = {"Authorization": f"Bearer {token}"}
    return user, headers


class TestContactMemberAccess:
    async def test_member_can_list_own_contacts(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """A member user can list contacts for their own member"""
        member = await _create_member(db_session, ixp)
        _user, headers = await _create_member_user(db_session, member_id=member.id)

        contact = Contact(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            name="Own Contact",
            email="own@example.net",
            role=ContactRole.noc,
        )
        db_session.add(contact)
        await db_session.flush()

        resp = await client.get(
            f"/api/v1/members/{member.id}/contacts",
            headers=headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 1

    async def test_member_can_get_own_contact(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """A member user can view a contact belonging to their own member"""
        member = await _create_member(db_session, ixp)
        _user, headers = await _create_member_user(db_session, member_id=member.id)

        contact = Contact(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            name="My Contact",
            email="mine@example.net",
            role=ContactRole.technical,
        )
        db_session.add(contact)
        await db_session.flush()

        resp = await client.get(
            f"/api/v1/members/{member.id}/contacts",
            headers=headers,
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(item["id"] == str(contact.id) for item in items)

    async def test_member_cannot_list_other_member_contacts(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """A member user cannot list contacts for another member (403)"""
        member_a = await _create_member(db_session, ixp)
        member_b = await _create_member(db_session, ixp)
        _user, headers_a = await _create_member_user(db_session, member_id=member_a.id)

        resp = await client.get(
            f"/api/v1/members/{member_b.id}/contacts",
            headers=headers_a,
        )
        assert resp.status_code == 403
