"""Tests para las API keys de usuario: creacion, listado y revocacion."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.models.user import User


async def _create_key(
    client: AsyncClient, auth_headers: dict, user_id: uuid.UUID, name: str = "collector",
) -> dict:
    resp = await client.post(
        f"/api/v1/users/{user_id}/api-keys",
        headers=auth_headers,
        json={"name": name, "scopes": ["monitoring:read"]},
    )
    assert resp.status_code == 201
    return resp.json()


class TestUserAPIKeyRevoke:
    async def test_revoke_key(
        self, client: AsyncClient, auth_headers: dict, admin_user: User,
    ):
        created = await _create_key(client, auth_headers, admin_user.id)

        resp = await client.delete(
            f"/api/v1/users/{admin_user.id}/api-keys/{created['id']}", headers=auth_headers,
        )
        assert resp.status_code == 204

    async def test_revoked_key_stops_authenticating(
        self, client: AsyncClient, auth_headers: dict, admin_user: User, ixp,
    ):
        """Una key revocada no debe seguir sirviendo para autenticar."""
        created = await _create_key(client, auth_headers, admin_user.id, name="a-revocar")
        raw_key = created["raw_key"]

        resp = await client.get("/api/v1/monitoring/targets", headers={"X-API-Key": raw_key})
        assert resp.status_code == 200

        resp = await client.delete(
            f"/api/v1/users/{admin_user.id}/api-keys/{created['id']}", headers=auth_headers,
        )
        assert resp.status_code == 204

        resp = await client.get("/api/v1/monitoring/targets", headers={"X-API-Key": raw_key})
        assert resp.status_code == 401

    async def test_revoke_removes_key_from_listing(
        self, client: AsyncClient, auth_headers: dict, admin_user: User,
    ):
        created = await _create_key(client, auth_headers, admin_user.id, name="listada")

        await client.delete(
            f"/api/v1/users/{admin_user.id}/api-keys/{created['id']}", headers=auth_headers,
        )

        resp = await client.get(f"/api/v1/users/{admin_user.id}/api-keys", headers=auth_headers)
        assert resp.status_code == 200
        assert all(k["id"] != created["id"] for k in resp.json()["items"])

    async def test_revoke_key_of_other_user_is_404(
        self, client: AsyncClient, auth_headers: dict, admin_user: User, member_user: User,
    ):
        """No se puede revocar la key de otro usuario pasando su propio user_id."""
        created = await _create_key(client, auth_headers, admin_user.id, name="ajena")

        resp = await client.delete(
            f"/api/v1/users/{member_user.id}/api-keys/{created['id']}", headers=auth_headers,
        )
        assert resp.status_code == 404

        resp = await client.get(f"/api/v1/users/{admin_user.id}/api-keys", headers=auth_headers)
        assert any(k["id"] == created["id"] for k in resp.json()["items"])

    async def test_revoke_unknown_key_is_404(
        self, client: AsyncClient, auth_headers: dict, admin_user: User,
    ):
        resp = await client.delete(
            f"/api/v1/users/{admin_user.id}/api-keys/{uuid.uuid4()}", headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_revoke_requires_admin(
        self,
        client: AsyncClient,
        auth_headers: dict,
        member_auth_headers: dict,
        admin_user: User,
    ):
        created = await _create_key(client, auth_headers, admin_user.id, name="protegida")

        resp = await client.delete(
            f"/api/v1/users/{admin_user.id}/api-keys/{created['id']}",
            headers=member_auth_headers,
        )
        assert resp.status_code == 403

    async def test_revoke_requires_auth(
        self, client: AsyncClient, auth_headers: dict, admin_user: User,
    ):
        created = await _create_key(client, auth_headers, admin_user.id, name="sin-auth")

        resp = await client.delete(
            f"/api/v1/users/{admin_user.id}/api-keys/{created['id']}",
        )
        assert resp.status_code == 401


class TestUserAPIKeyRSKeyIsolation:
    async def test_cannot_revoke_rs_key_through_user_endpoint(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, ixp,
    ):
        """Una key de route server no se revoca por el endpoint de usuario.

        Las keys de usuario y las de route server son mutuamente excluyentes.
        """
        from ixforge.models.route_server import RouteServer

        rs = RouteServer(
            id=uuid.uuid4(), ixp_id=ixp.id, name="rs-iso", ip_v4="192.0.2.250", is_active=True,
        )
        db_session.add(rs)
        await db_session.flush()

        created = await client.post(
            f"/api/v1/route-servers/{rs.id}/api-keys", headers=auth_headers, json={"name": "rs-k"},
        )
        key_id = created.json()["id"]

        users = await client.get("/api/v1/users", headers=auth_headers)
        user_id = users.json()["items"][0]["id"]

        resp = await client.delete(
            f"/api/v1/users/{user_id}/api-keys/{key_id}", headers=auth_headers,
        )
        assert resp.status_code == 404
