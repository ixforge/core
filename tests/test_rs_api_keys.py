"""Tests para las API keys de agente vinculadas a un route server."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.models.ixp import IXP
from ixforge.models.route_server import RouteServer


async def _setup_rs(
    db: AsyncSession, ixp: IXP, name: str = "rs-keys-test", ip_v4: str = "192.0.2.240",
) -> RouteServer:
    rs = RouteServer(id=uuid.uuid4(), ixp_id=ixp.id, name=name, ip_v4=ip_v4, is_active=True)
    db.add(rs)
    await db.flush()
    return rs


class TestRSAPIKeyCreate:
    async def test_create_returns_raw_key_with_agent_scope(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, ixp: IXP,
    ):
        rs = await _setup_rs(db_session, ixp)
        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/api-keys",
            headers=auth_headers,
            json={"name": "agent-rs1"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["raw_key"]
        assert body["scopes"] == ["agent:route_server"]
        assert body["name"] == "agent-rs1"
        assert body["is_active"] is True

    async def test_created_key_authorizes_agent_endpoint(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, ixp: IXP,
    ):
        rs = await _setup_rs(db_session, ixp, name="rs-keys-auth")
        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/api-keys",
            headers=auth_headers,
            json={"name": "agente"},
        )
        raw_key = resp.json()["raw_key"]

        # Sin config generada el endpoint devuelve 404, lo que prueba que la auth paso
        resp = await client.get(
            f"/api/v1/route-servers/{rs.id}/agent/config",
            headers={"X-API-Key": raw_key},
        )
        assert resp.status_code == 404

    async def test_key_rejected_for_other_route_server(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, ixp: IXP,
    ):
        rs1 = await _setup_rs(db_session, ixp, name="rs-keys-a")
        rs2 = await _setup_rs(db_session, ixp, name="rs-keys-b", ip_v4="192.0.2.241")
        resp = await client.post(
            f"/api/v1/route-servers/{rs1.id}/api-keys",
            headers=auth_headers,
            json={"name": "agente-a"},
        )
        raw_key = resp.json()["raw_key"]

        resp = await client.get(
            f"/api/v1/route-servers/{rs2.id}/agent/config",
            headers={"X-API-Key": raw_key},
        )
        assert resp.status_code == 403

    async def test_member_cannot_create(
        self, client: AsyncClient, member_auth_headers: dict, db_session: AsyncSession, ixp: IXP,
    ):
        rs = await _setup_rs(db_session, ixp, name="rs-keys-member")
        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/api-keys",
            headers=member_auth_headers,
            json={"name": "no deberia"},
        )
        assert resp.status_code == 403

    async def test_create_for_unknown_rs_is_404(
        self, client: AsyncClient, auth_headers: dict, ixp: IXP,
    ):
        resp = await client.post(
            f"/api/v1/route-servers/{uuid.uuid4()}/api-keys",
            headers=auth_headers,
            json={"name": "fantasma"},
        )
        assert resp.status_code == 404


class TestRSAPIKeyListAndRevoke:
    async def test_list_keys(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, ixp: IXP,
    ):
        rs = await _setup_rs(db_session, ixp, name="rs-keys-list")
        for name in ("k1", "k2"):
            await client.post(
                f"/api/v1/route-servers/{rs.id}/api-keys",
                headers=auth_headers,
                json={"name": name},
            )
        resp = await client.get(
            f"/api/v1/route-servers/{rs.id}/api-keys", headers=auth_headers,
        )
        assert resp.status_code == 200
        names = {k["name"] for k in resp.json()}
        assert names == {"k1", "k2"}
        assert all("raw_key" not in k for k in resp.json())

    async def test_revoke_key(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, ixp: IXP,
    ):
        rs = await _setup_rs(db_session, ixp, name="rs-keys-revoke")
        created = await client.post(
            f"/api/v1/route-servers/{rs.id}/api-keys",
            headers=auth_headers,
            json={"name": "rotar"},
        )
        key_id = created.json()["id"]
        raw_key = created.json()["raw_key"]

        resp = await client.delete(
            f"/api/v1/route-servers/{rs.id}/api-keys/{key_id}", headers=auth_headers,
        )
        assert resp.status_code == 204

        resp = await client.get(
            f"/api/v1/route-servers/{rs.id}/agent/config",
            headers={"X-API-Key": raw_key},
        )
        assert resp.status_code == 401

    async def test_revoke_key_of_other_rs_is_404(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, ixp: IXP,
    ):
        rs1 = await _setup_rs(db_session, ixp, name="rs-keys-r1")
        rs2 = await _setup_rs(db_session, ixp, name="rs-keys-r2", ip_v4="192.0.2.242")
        created = await client.post(
            f"/api/v1/route-servers/{rs1.id}/api-keys",
            headers=auth_headers,
            json={"name": "cruzada"},
        )
        key_id = created.json()["id"]

        resp = await client.delete(
            f"/api/v1/route-servers/{rs2.id}/api-keys/{key_id}", headers=auth_headers,
        )
        assert resp.status_code == 404
