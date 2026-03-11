"""Tests for Switch CRUD endpoints."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.models.ixp import IXP
from ixforge.models.location import Location
from ixforge.models.switch import Switch
from ixforge.models.user import User


class TestSwitchCRUD:
    async def test_create_switch(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        location = Location(
            id=uuid.uuid4(), ixp_id=ixp.id, name="DC-create", city="Test", country="US",
        )
        db_session.add(location)
        await db_session.flush()

        resp = await client.post(
            "/api/v1/switches",
            headers=auth_headers,
            json={
                "name": "sw-core-01",
                "vendor": "Arista",
                "model": "DCS-7280SR",
                "management_ip": "10.0.0.1",
                "location_id": str(location.id),
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "sw-core-01"
        assert body["vendor"] == "Arista"
        assert body["is_active"] is True

    async def test_get_switch(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        location = Location(
            id=uuid.uuid4(), ixp_id=ixp.id, name="DC-get", city="Test", country="US",
        )
        db_session.add(location)
        await db_session.flush()

        sw = Switch(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="sw-get",
            is_active=True,
            location_id=location.id,
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
        location = Location(
            id=uuid.uuid4(), ixp_id=ixp.id, name="DC-list", city="Test", country="US",
        )
        db_session.add(location)
        await db_session.flush()

        for i in range(3):
            sw = Switch(
                id=uuid.uuid4(),
                ixp_id=ixp.id,
                name=f"sw-list-{i}",
                is_active=True,
                location_id=location.id,
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
        location = Location(
            id=uuid.uuid4(), ixp_id=ixp.id, name="DC-upd", city="Test", country="US",
        )
        db_session.add(location)
        await db_session.flush()

        sw = Switch(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="sw-old",
            is_active=True,
            location_id=location.id,
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
        location = Location(
            id=uuid.uuid4(), ixp_id=ixp.id, name="DC-del", city="Test", country="US",
        )
        db_session.add(location)
        await db_session.flush()

        sw = Switch(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="sw-del",
            is_active=True,
            location_id=location.id,
        )
        db_session.add(sw)
        await db_session.flush()

        resp = await client.delete(f"/api/v1/switches/{sw.id}", headers=auth_headers)
        assert resp.status_code == 204

        # Confirm it is gone
        resp = await client.get(f"/api/v1/switches/{sw.id}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_create_switch_with_location(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        loc = Location(ixp_id=ixp.id, name="DC-sw-loc", city="Test", country="US")
        db_session.add(loc)
        await db_session.flush()

        resp = await client.post(
            "/api/v1/switches",
            headers=auth_headers,
            json={
                "name": "sw-loc-01",
                "location_id": str(loc.id),
            },
        )
        assert resp.status_code == 201
        assert resp.json()["location_id"] == str(loc.id)

    async def test_update_switch_location(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        loc = Location(ixp_id=ixp.id, name="DC-sw-upd", city="Test", country="US")
        db_session.add(loc)
        await db_session.flush()

        loc2 = Location(ixp_id=ixp.id, name="DC-sw-upd-orig", city="Test", country="US")
        db_session.add(loc2)
        await db_session.flush()

        sw = Switch(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="sw-loc-upd",
            is_active=True,
            location_id=loc2.id,
        )
        db_session.add(sw)
        await db_session.flush()

        resp = await client.patch(
            f"/api/v1/switches/{sw.id}",
            headers=auth_headers,
            json={"location_id": str(loc.id)},
        )
        assert resp.status_code == 200
        assert resp.json()["location_id"] == str(loc.id)

    async def test_member_cannot_access_switches(
        self,
        client: AsyncClient,
        member_auth_headers: dict,
        member_user: User,
        ixp: IXP,
    ):
        resp = await client.get("/api/v1/switches", headers=member_auth_headers)
        assert resp.status_code == 403


class TestSwitchSNMP:
    async def test_update_switch_clear_snmp_community(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        location = Location(
            id=uuid.uuid4(), ixp_id=ixp.id, name="DC-snmp", city="Test", country="US",
        )
        db_session.add(location)
        await db_session.flush()

        # Create switch with SNMP community
        resp = await client.post(
            "/api/v1/switches",
            headers=auth_headers,
            json={
                "name": "sw-snmp-clear",
                "snmp_community": "public",
                "location_id": str(location.id),
            },
        )
        assert resp.status_code == 201
        switch_id = resp.json()["id"]

        # Verify the switch was created (snmp_community is not in SwitchRead)
        sw = await db_session.get(Switch, uuid.UUID(switch_id))
        assert sw is not None
        assert sw.snmp_community_encrypted is not None

        # Clear SNMP community by sending null
        resp = await client.patch(
            f"/api/v1/switches/{switch_id}",
            headers=auth_headers,
            json={"snmp_community": None},
        )
        assert resp.status_code == 200

        # Verify it was cleared
        await db_session.refresh(sw)
        assert sw.snmp_community_encrypted is None
