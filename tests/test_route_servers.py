"""Tests for Route Server CRUD endpoints."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.models.ixp import IXP
from ixforge.models.route_server import RouteServer


class TestRouteServerCRUD:
    async def test_create_route_server(self, client: AsyncClient, auth_headers: dict, ixp: IXP):
        resp = await client.post(
            "/api/v1/route-servers",
            headers=auth_headers,
            json={
                "name": "rs1",
                "hostname": "rs1.ixp.example.net",
                "ip_v4": "192.0.2.250",
                "ip_v6": "2001:db8::250",
                "asn": 65000,
                "software": "bird",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "rs1"
        assert body["asn"] == 65000
        assert body["is_active"] is True
        assert body["last_heartbeat_at"] is None
        assert body["agent_version"] is None

    async def test_get_route_server(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="rs-get",
            hostname="rs-get.example.net",
            ip_v4="192.0.2.251",
            asn=65000,
            software="bird",
            is_active=True,
        )
        db_session.add(rs)
        await db_session.flush()

        resp = await client.get(f"/api/v1/route-servers/{rs.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == str(rs.id)

    async def test_get_route_server_not_found(
        self, client: AsyncClient, auth_headers: dict, ixp: IXP
    ):
        resp = await client.get(f"/api/v1/route-servers/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_list_route_servers(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        for i in range(2):
            rs = RouteServer(
                id=uuid.uuid4(),
                ixp_id=ixp.id,
                name=f"rs-list-{i}",
                hostname=f"rs-list-{i}.example.net",
                ip_v4=f"192.0.2.{240 + i}",
                asn=65000,
                software="bird",
                is_active=True,
            )
            db_session.add(rs)
        await db_session.flush()

        resp = await client.get("/api/v1/route-servers", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 2

    async def test_update_route_server(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="rs-old",
            hostname="rs-old.example.net",
            ip_v4="192.0.2.245",
            asn=65000,
            software="bird",
            is_active=True,
        )
        db_session.add(rs)
        await db_session.flush()

        resp = await client.patch(
            f"/api/v1/route-servers/{rs.id}",
            headers=auth_headers,
            json={"name": "rs-new", "is_active": False},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "rs-new"
        assert resp.json()["is_active"] is False

    async def test_delete_route_server(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="rs-del",
            hostname="rs-del.example.net",
            ip_v4="192.0.2.249",
            asn=65000,
            software="bird",
            is_active=True,
        )
        db_session.add(rs)
        await db_session.flush()

        resp = await client.delete(f"/api/v1/route-servers/{rs.id}", headers=auth_headers)
        assert resp.status_code == 204
