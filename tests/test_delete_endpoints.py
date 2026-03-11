"""Tests for hard-delete endpoints."""

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import MemberState
from ixforge.models.event import Event
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.models.user import User, UserRole
from ixforge.services.auth import hash_password


class TestDeleteMember:
    async def test_delete_terminated_member(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict, db_session: AsyncSession
    ) -> None:
        m = Member(ixp_id=ixp.id, name="ISP", short_name="I", asn=65100, state=MemberState.terminated)
        db_session.add(m)
        await db_session.flush()
        resp = await client.delete(f"/api/v1/members/{m.id}", headers=auth_headers)
        assert resp.status_code == 204

    async def test_delete_active_member_raises_409(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict, db_session: AsyncSession
    ) -> None:
        m = Member(ixp_id=ixp.id, name="ISP2", short_name="I2", asn=65101, state=MemberState.active)
        db_session.add(m)
        await db_session.flush()
        resp = await client.delete(f"/api/v1/members/{m.id}", headers=auth_headers)
        assert resp.status_code == 409

    async def test_delete_member_emits_event(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict, db_session: AsyncSession
    ) -> None:
        m = Member(ixp_id=ixp.id, name="ISP3", short_name="I3", asn=65102, state=MemberState.terminated)
        db_session.add(m)
        await db_session.flush()
        await client.delete(f"/api/v1/members/{m.id}", headers=auth_headers)
        event = await db_session.scalar(select(Event).where(Event.type == "member.deleted"))
        assert event is not None


class TestDeleteUser:
    async def test_delete_inactive_user(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ) -> None:
        u = User(
            id=uuid.uuid4(), email="del@ex.com", hashed_password=hash_password("p"),
            full_name="Del", role=UserRole.member, is_active=False
        )
        db_session.add(u)
        await db_session.flush()
        resp = await client.delete(f"/api/v1/users/{u.id}", headers=auth_headers)
        assert resp.status_code == 204

    async def test_delete_active_user_raises_409(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ) -> None:
        u = User(
            id=uuid.uuid4(), email="act@ex.com", hashed_password=hash_password("p"),
            full_name="Act", role=UserRole.member, is_active=True
        )
        db_session.add(u)
        await db_session.flush()
        resp = await client.delete(f"/api/v1/users/{u.id}", headers=auth_headers)
        assert resp.status_code == 409

    async def test_delete_self_raises_409(
        self, client: AsyncClient, auth_headers: dict, admin_user: User
    ) -> None:
        resp = await client.delete(f"/api/v1/users/{admin_user.id}", headers=auth_headers)
        assert resp.status_code == 409

    async def test_delete_inactive_admin_succeeds(
        self, client: AsyncClient, auth_headers: dict, admin_user: User, db_session: AsyncSession
    ) -> None:
        # admin_user is the only active admin. other_admin is inactive.
        # The active-admin count guard must only apply when the target user is active,
        # so deleting an inactive admin must succeed regardless of how many active admins remain.
        other_admin = User(
            id=uuid.uuid4(), email="other_admin@ex.com", hashed_password=hash_password("p"),
            full_name="Other Admin", role=UserRole.admin, is_active=False,
        )
        db_session.add(other_admin)
        await db_session.flush()
        resp = await client.delete(f"/api/v1/users/{other_admin.id}", headers=auth_headers)
        assert resp.status_code == 204
