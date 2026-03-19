"""Tests for Location CRUD."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import ConflictError, NotFoundError
from ixforge.models.ixp import IXP
from ixforge.models.location import Location
from ixforge.models.switch import Switch
from ixforge.schemas.location import LocationCreate, LocationUpdate
from ixforge.services import locations as loc_svc


class TestLocationService:
    async def test_create_location(self, db_session: AsyncSession, ixp: IXP) -> None:
        loc = await loc_svc.create(db_session, ixp.id, LocationCreate(name="DC1", city="SCL", country="CL"))
        assert loc.id is not None
        assert loc.name == "DC1"
        assert loc.ixp_id == ixp.id

    async def test_create_duplicate_name_raises(self, db_session: AsyncSession, ixp: IXP) -> None:
        await loc_svc.create(db_session, ixp.id, LocationCreate(name="DC1", city="TestCity", country="US"))
        with pytest.raises(ConflictError):
            await loc_svc.create(db_session, ixp.id, LocationCreate(name="DC1", city="TestCity", country="US"))

    async def test_get_not_found_raises(self, db_session: AsyncSession, ixp: IXP) -> None:
        with pytest.raises(NotFoundError):
            await loc_svc.get(db_session, ixp.id, uuid.uuid4())

    async def test_update_location(self, db_session: AsyncSession, ixp: IXP) -> None:
        loc = await loc_svc.create(db_session, ixp.id, LocationCreate(name="DC1", city="TestCity", country="US"))
        updated = await loc_svc.update(db_session, ixp.id, loc.id, LocationUpdate(city="Rosario"))
        assert updated.city == "Rosario"

    async def test_delete_location(self, db_session: AsyncSession, ixp: IXP) -> None:
        loc = await loc_svc.create(db_session, ixp.id, LocationCreate(name="DC1", city="TestCity", country="US"))
        await loc_svc.delete(db_session, ixp.id, loc.id)

    async def test_delete_location_with_switch_raises(self, db_session: AsyncSession, ixp: IXP) -> None:
        loc = await loc_svc.create(db_session, ixp.id, LocationCreate(name="DC1", city="TestCity", country="US"))
        sw = Switch(ixp_id=ixp.id, name="SW1", location_id=loc.id)
        db_session.add(sw)
        await db_session.flush()
        with pytest.raises(ConflictError):
            await loc_svc.delete(db_session, ixp.id, loc.id)


class TestLocationsAPI:
    async def test_list_locations(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict, db_session: AsyncSession
    ) -> None:
        db_session.add(Location(ixp_id=ixp.id, name="DC1", city="TestCity", country="US"))
        await db_session.flush()
        resp = await client.get("/api/v1/locations", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

    async def test_create_location_api(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict
    ) -> None:
        resp = await client.post("/api/v1/locations", json={"name": "DC1", "city": "TestCity", "country": "US"}, headers=auth_headers)
        assert resp.status_code == 201
        assert resp.json()["name"] == "DC1"

    async def test_get_location_not_found(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        resp = await client.get(f"/api/v1/locations/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_delete_location_with_switch_returns_409(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict, db_session: AsyncSession
    ) -> None:
        loc = Location(ixp_id=ixp.id, name="DC1", city="TestCity", country="US")
        db_session.add(loc)
        await db_session.flush()
        db_session.add(Switch(ixp_id=ixp.id, name="SW1", location_id=loc.id))
        await db_session.flush()
        resp = await client.delete(f"/api/v1/locations/{loc.id}", headers=auth_headers)
        assert resp.status_code == 409

    async def test_get_location_api(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict, db_session: AsyncSession
    ) -> None:
        loc = Location(ixp_id=ixp.id, name="DC-get", city="TestCity", country="US")
        db_session.add(loc)
        await db_session.flush()
        resp = await client.get(f"/api/v1/locations/{loc.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "DC-get"

    async def test_update_location_api(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict, db_session: AsyncSession
    ) -> None:
        loc = Location(ixp_id=ixp.id, name="DC-old", city="TestCity", country="US")
        db_session.add(loc)
        await db_session.flush()
        resp = await client.patch(
            f"/api/v1/locations/{loc.id}",
            json={"name": "DC-new", "city": "Santiago"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "DC-new"
        assert resp.json()["city"] == "Santiago"

    async def test_delete_location_api(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict, db_session: AsyncSession
    ) -> None:
        loc = Location(ixp_id=ixp.id, name="DC-del", city="TestCity", country="US")
        db_session.add(loc)
        await db_session.flush()
        resp = await client.delete(f"/api/v1/locations/{loc.id}", headers=auth_headers)
        assert resp.status_code == 204

    async def test_create_duplicate_location_api(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict, db_session: AsyncSession
    ) -> None:
        db_session.add(Location(ixp_id=ixp.id, name="DC-dup", city="TestCity", country="US"))
        await db_session.flush()
        resp = await client.post(
            "/api/v1/locations", json={"name": "DC-dup", "city": "TestCity", "country": "US"}, headers=auth_headers
        )
        assert resp.status_code == 409

    async def test_member_cannot_access_locations(
        self, client: AsyncClient, member_auth_headers: dict, ixp: IXP
    ) -> None:
        resp = await client.get("/api/v1/locations", headers=member_auth_headers)
        assert resp.status_code == 403
