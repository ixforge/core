"""Tests for authentication: login, JWT, API key, RBAC."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.models.api_key import APIKey
from ixforge.models.ixp import IXP
from ixforge.models.user import User
from ixforge.services.auth import hash_api_key

# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class TestLogin:
    async def test_login_valid_credentials(self, client: AsyncClient, admin_user: User, ixp: IXP):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "adminpass123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient, admin_user: User, ixp: IXP):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient, ixp: IXP):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "irrelevant"},
        )
        assert resp.status_code == 401

    async def test_login_inactive_user(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP
    ):
        from ixforge.services.auth import hash_password

        user = User(
            id=uuid.uuid4(),
            email="inactive@example.com",
            hashed_password=hash_password("inactivepass"),
            full_name="Inactive User",
            is_active=False,
        )
        db_session.add(user)
        await db_session.flush()

        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "inactive@example.com", "password": "inactivepass"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# JWT authentication
# ---------------------------------------------------------------------------


class TestJWTAuth:
    async def test_me_with_valid_token(
        self, client: AsyncClient, admin_user: User, auth_headers: dict
    ):
        resp = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == admin_user.email
        assert body["id"] == str(admin_user.id)

    async def test_me_without_token(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    async def test_me_with_invalid_token(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )
        assert resp.status_code == 401

    async def test_me_with_expired_token_format(self, client: AsyncClient):
        # A token for a non-existent user should fail.
        from ixforge.services.auth import create_access_token

        token = create_access_token(subject=str(uuid.uuid4()))
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# API key authentication
# ---------------------------------------------------------------------------


class TestAPIKeyAuth:
    async def test_auth_with_valid_api_key(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        ixp: IXP,
    ):
        raw_key = "ixf_testapikey1234567890abcdef1234567890abcdef1234567890abcdef12345678"
        key_hash = hash_api_key(raw_key)
        api_key = APIKey(
            id=uuid.uuid4(),
            key_hash=key_hash,
            prefix=raw_key[:12],
            name="Test Key",
            scopes=["read"],
            user_id=admin_user.id,
            is_active=True,
        )
        db_session.add(api_key)
        await db_session.flush()

        resp = await client.get(
            "/api/v1/auth/me",
            headers={"X-API-Key": raw_key},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(admin_user.id)

    async def test_auth_with_invalid_api_key(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"X-API-Key": "ixf_nonexistent_key_value"},
        )
        assert resp.status_code == 401

    async def test_auth_with_inactive_api_key(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
    ):
        raw_key = "ixf_inactivekey1234567890abcdef1234567890abcdef1234567890abcdef12345"
        key_hash = hash_api_key(raw_key)
        api_key = APIKey(
            id=uuid.uuid4(),
            key_hash=key_hash,
            prefix=raw_key[:12],
            name="Inactive Key",
            scopes=[],
            user_id=admin_user.id,
            is_active=False,
        )
        db_session.add(api_key)
        await db_session.flush()

        resp = await client.get(
            "/api/v1/auth/me",
            headers={"X-API-Key": raw_key},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


class TestRBAC:
    async def test_admin_can_list_users(
        self, client: AsyncClient, admin_user: User, auth_headers: dict
    ):
        resp = await client.get("/api/v1/users", headers=auth_headers)
        assert resp.status_code == 200

    async def test_member_cannot_list_users(
        self,
        client: AsyncClient,
        member_user: User,
        member_auth_headers: dict,
    ):
        resp = await client.get("/api/v1/users", headers=member_auth_headers)
        assert resp.status_code == 403

    async def test_admin_can_create_member(
        self,
        client: AsyncClient,
        admin_user: User,
        auth_headers: dict,
        ixp: IXP,
    ):
        resp = await client.post(
            "/api/v1/members",
            headers=auth_headers,
            json={
                "name": "RBAC Test Network",
                "short_name": "RBAC",
                "asn": 65100,
            },
        )
        assert resp.status_code == 201

    async def test_member_cannot_create_member(
        self,
        client: AsyncClient,
        member_user: User,
        member_auth_headers: dict,
        ixp: IXP,
    ):
        resp = await client.post(
            "/api/v1/members",
            headers=member_auth_headers,
            json={
                "name": "Should Fail Network",
                "short_name": "FAIL",
                "asn": 65101,
            },
        )
        assert resp.status_code == 403
