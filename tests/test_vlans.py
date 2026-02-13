"""Tests for VLAN CRUD endpoints."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import VLANType
from ixforge.models.ixp import IXP
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
