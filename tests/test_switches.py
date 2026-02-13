"""Tests for Switch CRUD endpoints."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.models.ixp import IXP
from ixforge.models.switch import Switch
from ixforge.models.user import User


class TestSwitchCRUD:
    async def test_create_switch(self, client: AsyncClient, auth_headers: dict, ixp: IXP):
        resp = await client.post(
            "/api/v1/switches",
            headers=auth_headers,
            json={
                "name": "sw-core-01",
                "hostname": "sw-core-01.ixp.example.net",
                "vendor": "Arista",
                "model": "DCS-7280SR",
                "management_ip": "10.0.0.1",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "sw-core-01"
        assert body["hostname"] == "sw-core-01.ixp.example.net"
        assert body["vendor"] == "Arista"
        assert body["is_active"] is True

    async def test_get_switch(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        sw = Switch(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="sw-get",
            hostname="sw-get.ixp.example.net",
            is_active=True,
        )
        db_session.add(sw)
        await db_session.flush()

        resp = await client.get(f"/api/v1/switches/{sw.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == str(sw.id)

    async def test_get_switch_not_found(self, client: AsyncClient, auth_headers: dict, ixp: IXP):
        resp = await client.get(f"/api/v1/switches/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_list_switches(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        for i in range(3):
            sw = Switch(
                id=uuid.uuid4(),
                ixp_id=ixp.id,
                name=f"sw-list-{i}",
                hostname=f"sw-list-{i}.example.net",
                is_active=True,
            )
            db_session.add(sw)
        await db_session.flush()

        resp = await client.get("/api/v1/switches", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 3

    async def test_update_switch(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        sw = Switch(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="sw-old",
            hostname="sw-old.example.net",
            is_active=True,
        )
        db_session.add(sw)
        await db_session.flush()

        resp = await client.patch(
            f"/api/v1/switches/{sw.id}",
            headers=auth_headers,
            json={"name": "sw-new", "vendor": "Juniper"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "sw-new"
        assert body["vendor"] == "Juniper"

    async def test_delete_switch(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        sw = Switch(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="sw-del",
            hostname="sw-del.example.net",
            is_active=True,
        )
        db_session.add(sw)
        await db_session.flush()

        resp = await client.delete(f"/api/v1/switches/{sw.id}", headers=auth_headers)
        assert resp.status_code == 204

        # Confirm it is gone
        resp = await client.get(f"/api/v1/switches/{sw.id}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_member_cannot_access_switches(
        self,
        client: AsyncClient,
        member_auth_headers: dict,
        member_user: User,
        ixp: IXP,
    ):
        resp = await client.get("/api/v1/switches", headers=member_auth_headers)
        assert resp.status_code == 403
