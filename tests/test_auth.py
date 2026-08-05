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
    async def _make_key(
        self, db_session: AsyncSession, user: User, scopes: list[str], raw_key: str
    ) -> APIKey:
        api_key = APIKey(
            id=uuid.uuid4(),
            key_hash=hash_api_key(raw_key),
            prefix=raw_key[:12],
            name="Test Key",
            scopes=scopes,
            user_id=user.id,
            is_active=True,
        )
        db_session.add(api_key)
        await db_session.flush()
        return api_key

    async def test_key_without_matching_scope_is_forbidden(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        ixp: IXP,
    ):
        """Una key valida sin el scope del endpoint recibe 403 (no autoriza)."""
        raw_key = "ixf_testapikey1234567890abcdef1234567890abcdef1234567890abcdef12345678"
        await self._make_key(db_session, admin_user, ["monitoring:read"], raw_key)

        resp = await client.get("/api/v1/auth/me", headers={"X-API-Key": raw_key})
        assert resp.status_code == 403

    async def test_monitoring_key_cannot_reach_management_api(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        ixp: IXP,
    ):
        """Regresion de escalada: una key monitoring:read no toca el API de gestion."""
        raw_key = "ixf_escalationkey7890abcdef1234567890abcdef1234567890abcdef123456789012"
        await self._make_key(db_session, admin_user, ["monitoring:read"], raw_key)

        listed = await client.get("/api/v1/users", headers={"X-API-Key": raw_key})
        assert listed.status_code == 403

        created = await client.post(
            "/api/v1/members",
            headers={"X-API-Key": raw_key},
            json={"name": "Escalada", "short_name": "ESC", "asn": 65099},
        )
        assert created.status_code == 403

    async def test_scoped_key_reads_its_resource(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        ixp: IXP,
    ):
        """Una key members:read puede leer /members pero no escribir ni tocar otro recurso."""
        raw_key = "ixf_membersread567890abcdef1234567890abcdef1234567890abcdef1234567890"
        await self._make_key(db_session, admin_user, ["members:read"], raw_key)

        assert (await client.get(
            "/api/v1/members", headers={"X-API-Key": raw_key})).status_code == 200
        # sin members:write no puede crear
        assert (await client.post(
            "/api/v1/members", headers={"X-API-Key": raw_key},
            json={"name": "X", "short_name": "X", "asn": 65001})).status_code == 403
        # sin trunks:read no puede leer otro recurso
        assert (await client.get(
            "/api/v1/trunks", headers={"X-API-Key": raw_key})).status_code == 403

    async def test_scoped_key_writes_with_write_scope(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        ixp: IXP,
    ):
        """Una key members:write (sobre un admin) puede crear miembros."""
        raw_key = "ixf_memberswrite67890abcdef1234567890abcdef1234567890abcdef1234567890"
        await self._make_key(db_session, admin_user, ["members:write"], raw_key)

        resp = await client.post(
            "/api/v1/members", headers={"X-API-Key": raw_key},
            json={"name": "ConScope", "short_name": "CS", "asn": 65002},
        )
        assert resp.status_code == 201

    async def test_double_lock_role_still_applies(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        member_user: User,
        ixp: IXP,
    ):
        """Doble candado: aunque la key tenga members:write, si el usuario es member
        (no admin) el rol lo frena en un endpoint admin-only."""
        raw_key = "ixf_memberrolekey7890abcdef1234567890abcdef1234567890abcdef1234567890"
        await self._make_key(db_session, member_user, ["members:write"], raw_key)

        resp = await client.post(
            "/api/v1/members", headers={"X-API-Key": raw_key},
            json={"name": "Y", "short_name": "Y", "asn": 65003},
        )
        assert resp.status_code == 403

    async def test_monitoring_key_still_authorizes_monitoring(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        ixp: IXP,
    ):
        """El fix no debe romper al collector: monitoring:read sigue sirviendo en /monitoring."""
        raw_key = "ixf_monitoringkey34567890abcdef1234567890abcdef1234567890abcdef12345678"
        await self._make_key(db_session, admin_user, ["monitoring:read"], raw_key)

        resp = await client.get("/api/v1/monitoring/targets", headers={"X-API-Key": raw_key})
        assert resp.status_code == 200

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
