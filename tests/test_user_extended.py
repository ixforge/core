"""Tests for user extended fields and admin protection."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.models.user import User, UserRole
from ixforge.services.auth import create_access_token, hash_password


class TestUserExtendedFields:
    async def test_create_user_with_phone(self, client: AsyncClient, auth_headers: dict) -> None:
        resp = await client.post("/api/v1/users", json={
            "email": "u1@example.com", "password": "pass12345678",
            "full_name": "User One", "role": "member",
            "phone": "+54 11 1234-5678", "position": "NOC Engineer",
        }, headers=auth_headers)
        assert resp.status_code == 201
        assert resp.json()["phone"] == "+54 11 1234-5678"
        assert resp.json()["position"] == "NOC Engineer"

    async def test_update_user_pgp_key(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ) -> None:
        u = User(
            id=uuid.uuid4(), email="u2@ex.com", hashed_password=hash_password("pass"),
            full_name="U2", role=UserRole.member, is_active=True
        )
        db_session.add(u)
        await db_session.flush()
        resp = await client.patch(
            f"/api/v1/users/{u.id}",
            json={"pgp_key": "-----BEGIN PGP PUBLIC KEY BLOCK-----"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["pgp_key"].startswith("-----BEGIN")

    async def test_user_read_includes_extended_fields(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        resp = await client.post("/api/v1/users", json={
            "email": "u3@example.com", "password": "pass12345678",
            "full_name": "User Three",
        }, headers=auth_headers)
        assert resp.status_code == 201
        body = resp.json()
        assert "phone" in body
        assert "position" in body
        assert "pgp_key" in body
        assert body["phone"] is None
        assert body["position"] is None
        assert body["pgp_key"] is None


class TestUserAdminProtection:
    async def test_update_user_cannot_self_deactivate(
        self,
        client: AsyncClient,
        admin_user: User,
        auth_headers: dict,
    ) -> None:
        resp = await client.patch(
            f"/api/v1/users/{admin_user.id}",
            json={"is_active": False},
            headers=auth_headers,
        )
        assert resp.status_code == 409

    async def test_update_user_cannot_self_demote(
        self,
        client: AsyncClient,
        admin_user: User,
        auth_headers: dict,
    ) -> None:
        resp = await client.patch(
            f"/api/v1/users/{admin_user.id}",
            json={"role": "member"},
            headers=auth_headers,
        )
        assert resp.status_code == 409

    async def test_update_user_cannot_demote_last_admin(
        self,
        client: AsyncClient,
        auth_headers: dict,
        admin_user: User,
        db_session: AsyncSession,
    ) -> None:
        """Only one active admin exists, demoting them must fail (self-check)"""
        # admin_user is the sole active admin - try to demote themselves
        resp = await client.patch(
            f"/api/v1/users/{admin_user.id}",
            json={"role": "member"},
            headers=auth_headers,
        )
        assert resp.status_code == 409

    async def test_admin_can_demote_other_admin_when_multiple(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
    ) -> None:
        """When there are multiple active admins, one can demote another"""
        other_admin = User(
            id=uuid.uuid4(),
            email="demotable-admin@example.com",
            hashed_password=hash_password("pass12345678"),
            full_name="Demotable Admin",
            role=UserRole.admin,
            is_active=True,
        )
        db_session.add(other_admin)
        await db_session.flush()

        resp = await client.patch(
            f"/api/v1/users/{other_admin.id}",
            json={"role": "member"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "member"

    async def test_admin_cannot_deactivate_last_active_admin(
        self,
        client: AsyncClient,
        auth_headers: dict,
        admin_user: User,
        db_session: AsyncSession,
    ) -> None:
        """When only one active admin exists, cannot deactivate them (self-check)"""
        # admin_user is the only active admin, try to self-deactivate
        resp = await client.patch(
            f"/api/v1/users/{admin_user.id}",
            json={"is_active": False},
            headers=auth_headers,
        )
        assert resp.status_code == 409
