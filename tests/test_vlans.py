"""Tests for VLAN CRUD endpoints."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import VLANType
from ixforge.models.ip import IPPool
from ixforge.models.ixp import IXP
from ixforge.models.route_server import RouteServer
from ixforge.models.route_server_vlan import RouteServerVLAN
from ixforge.models.vlan import VLAN


class TestVLANCRUD:
    async def test_create_vlan(self, client: AsyncClient, auth_headers: dict, ixp: IXP):
        resp = await client.post(
            "/api/v1/vlans",
            headers=auth_headers,
            json={
                "name": "Production Peering",
                "vid": 100,
                "type": "production",
                "description": "Main peering VLAN",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Production Peering"
        assert body["vid"] == 100
        assert body["type"] == "production"

    async def test_create_vlan_invalid_vid_rejected(
        self, client: AsyncClient, auth_headers: dict, ixp: IXP
    ):
        resp = await client.post(
            "/api/v1/vlans",
            headers=auth_headers,
            json={"name": "Bad VLAN", "vid": 5000, "type": "production"},
        )
        assert resp.status_code == 422

    async def test_get_vlan(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        vlan = VLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Get VLAN",
            vid=200,
            type=VLANType.production,
        )
        db_session.add(vlan)
        await db_session.flush()

        resp = await client.get(f"/api/v1/vlans/{vlan.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["vid"] == 200

    async def test_list_vlans(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        for i in range(3):
            v = VLAN(
                id=uuid.uuid4(),
                ixp_id=ixp.id,
                name=f"List VLAN {i}",
                vid=500 + i,
                type=VLANType.production,
            )
            db_session.add(v)
        await db_session.flush()

        resp = await client.get("/api/v1/vlans", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 3

    async def test_update_vlan(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        vlan = VLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Old VLAN",
            vid=600,
            type=VLANType.production,
        )
        db_session.add(vlan)
        await db_session.flush()

        resp = await client.patch(
            f"/api/v1/vlans/{vlan.id}",
            headers=auth_headers,
            json={"name": "Updated VLAN", "type": "quarantine"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated VLAN"
        assert resp.json()["type"] == "quarantine"

    async def test_delete_vlan(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        vlan = VLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Del VLAN",
            vid=700,
            type=VLANType.production,
        )
        db_session.add(vlan)
        await db_session.flush()

        resp = await client.delete(f"/api/v1/vlans/{vlan.id}", headers=auth_headers)
        assert resp.status_code == 204

        resp = await client.get(f"/api/v1/vlans/{vlan.id}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_create_duplicate_vid_returns_409(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Creating a VLAN with a duplicate VID should return 409"""
        vlan = VLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Dup VID VLAN",
            vid=800,
            type=VLANType.production,
        )
        db_session.add(vlan)
        await db_session.flush()

        resp = await client.post(
            "/api/v1/vlans",
            headers=auth_headers,
            json={"name": "Another VLAN", "vid": 800, "type": "production"},
        )
        assert resp.status_code == 409

    async def test_delete_vlan_with_pool_returns_409(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Deleting a VLAN that has IP pools must return 409"""
        vlan = VLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="VLAN with pool",
            vid=810,
            type=VLANType.production,
        )
        db_session.add(vlan)
        await db_session.flush()

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="203.0.113.0/24",
            af=4,
        )
        db_session.add(pool)
        await db_session.flush()

        resp = await client.delete(f"/api/v1/vlans/{vlan.id}", headers=auth_headers)
        assert resp.status_code == 409

    async def test_delete_vlan_with_rs_vlan_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Deleting a VLAN that has RS-VLAN associations must return 409"""
        vlan = VLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="VLAN with RS",
            vid=820,
            type=VLANType.production,
        )
        db_session.add(vlan)
        await db_session.flush()

        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="rs-vlan-del",
            hostname="rs-vlan-del.example.net",
            asn=65000,
        )
        db_session.add(rs)
        await db_session.flush()

        rs_vlan = RouteServerVLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            route_server_id=rs.id,
            vlan_id=vlan.id,
        )
        db_session.add(rs_vlan)
        await db_session.flush()

        resp = await client.delete(f"/api/v1/vlans/{vlan.id}", headers=auth_headers)
        assert resp.status_code == 409
