"""Tests for route server VLAN association service and API."""


import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import VLANType
from ixforge.exceptions import ConflictError, NotFoundError
from ixforge.models.ixp import IXP
from ixforge.models.route_server import RouteServer
from ixforge.models.route_server_vlan import RouteServerVLAN
from ixforge.models.vlan import VLAN
from ixforge.services import route_server_vlans as svc


class TestRSVLANService:
    async def test_add_vlan_to_rs(self, db_session: AsyncSession, ixp: IXP) -> None:
        rs = RouteServer(ixp_id=ixp.id, name="RS1")
        vlan = VLAN(ixp_id=ixp.id, name="IXP", vid=10, type=VLANType.production)
        db_session.add(rs)
        db_session.add(vlan)
        await db_session.flush()
        assoc = await svc.add_vlan(db_session, ixp.id, rs.id, vlan.id)
        assert assoc.route_server_id == rs.id
        assert assoc.vlan_id == vlan.id

    async def test_add_duplicate_vlan_raises(self, db_session: AsyncSession, ixp: IXP) -> None:
        rs = RouteServer(ixp_id=ixp.id, name="RS2")
        vlan = VLAN(ixp_id=ixp.id, name="IXP2", vid=11, type=VLANType.production)
        db_session.add(rs)
        db_session.add(vlan)
        await db_session.flush()
        await svc.add_vlan(db_session, ixp.id, rs.id, vlan.id)
        with pytest.raises(ConflictError):
            await svc.add_vlan(db_session, ixp.id, rs.id, vlan.id)

    async def test_remove_vlan_from_rs(self, db_session: AsyncSession, ixp: IXP) -> None:
        rs = RouteServer(ixp_id=ixp.id, name="RS3")
        vlan = VLAN(ixp_id=ixp.id, name="IXP3", vid=12, type=VLANType.production)
        db_session.add(rs)
        db_session.add(vlan)
        await db_session.flush()
        await svc.add_vlan(db_session, ixp.id, rs.id, vlan.id)
        await svc.remove_vlan(db_session, ixp.id, rs.id, vlan.id)

    async def test_remove_nonexistent_vlan_raises(self, db_session: AsyncSession, ixp: IXP) -> None:
        rs = RouteServer(ixp_id=ixp.id, name="RS6")
        vlan = VLAN(ixp_id=ixp.id, name="IXP6", vid=14, type=VLANType.production)
        db_session.add(rs)
        db_session.add(vlan)
        await db_session.flush()
        with pytest.raises(NotFoundError):
            await svc.remove_vlan(db_session, ixp.id, rs.id, vlan.id)

    async def test_add_vlan_rs_wrong_ixp_raises(self, db_session: AsyncSession, ixp: IXP) -> None:
        other_ixp = IXP(name="Other IXP A", short_name="OTA", asn=65100, country="CL", city="X")
        db_session.add(other_ixp)
        await db_session.flush()
        rs = RouteServer(ixp_id=other_ixp.id, name="RS-other-a")
        vlan = VLAN(ixp_id=ixp.id, name="IXP-local", vid=20, type=VLANType.production)
        db_session.add(rs)
        db_session.add(vlan)
        await db_session.flush()
        with pytest.raises(NotFoundError):
            await svc.add_vlan(db_session, ixp.id, rs.id, vlan.id)

    async def test_add_vlan_vlan_wrong_ixp_raises(self, db_session: AsyncSession, ixp: IXP) -> None:
        other_ixp = IXP(name="Other IXP B", short_name="OTB", asn=65101, country="CL", city="X")
        db_session.add(other_ixp)
        await db_session.flush()
        rs = RouteServer(ixp_id=ixp.id, name="RS-local-b")
        vlan = VLAN(ixp_id=other_ixp.id, name="IXP-other-b", vid=21, type=VLANType.production)
        db_session.add(rs)
        db_session.add(vlan)
        await db_session.flush()
        with pytest.raises(NotFoundError):
            await svc.add_vlan(db_session, ixp.id, rs.id, vlan.id)

    async def test_remove_vlan_wrong_ixp_raises(self, db_session: AsyncSession, ixp: IXP) -> None:
        other_ixp = IXP(name="Other IXP C", short_name="OTC", asn=65102, country="CL", city="X")
        db_session.add(other_ixp)
        await db_session.flush()
        rs = RouteServer(ixp_id=other_ixp.id, name="RS-other-c")
        vlan = VLAN(ixp_id=other_ixp.id, name="IXP-other-c", vid=22, type=VLANType.production)
        db_session.add(rs)
        db_session.add(vlan)
        await db_session.flush()
        assoc = RouteServerVLAN(ixp_id=other_ixp.id, route_server_id=rs.id, vlan_id=vlan.id)
        db_session.add(assoc)
        await db_session.flush()
        with pytest.raises(NotFoundError):
            await svc.remove_vlan(db_session, ixp.id, rs.id, vlan.id)


class TestRSVLANAPI:
    async def test_list_rs_vlans(self, client: AsyncClient, ixp: IXP, auth_headers: dict, db_session: AsyncSession) -> None:
        rs = RouteServer(ixp_id=ixp.id, name="RS4")
        db_session.add(rs)
        await db_session.flush()
        resp = await client.get(f"/api/v1/route-servers/{rs.id}/vlans", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_add_vlan_api(self, client: AsyncClient, ixp: IXP, auth_headers: dict, db_session: AsyncSession) -> None:
        rs = RouteServer(ixp_id=ixp.id, name="RS5")
        vlan = VLAN(ixp_id=ixp.id, name="IXP5", vid=13, type=VLANType.production)
        db_session.add(rs)
        db_session.add(vlan)
        await db_session.flush()
        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/vlans",
            json={"vlan_id": str(vlan.id)},
            headers=auth_headers,
        )
        assert resp.status_code == 201

    async def test_delete_vlan_api(self, client: AsyncClient, ixp: IXP, auth_headers: dict, db_session: AsyncSession) -> None:
        rs = RouteServer(ixp_id=ixp.id, name="RS7")
        vlan = VLAN(ixp_id=ixp.id, name="IXP7", vid=15, type=VLANType.production)
        db_session.add(rs)
        db_session.add(vlan)
        await db_session.flush()
        # Add the VLAN association first
        add_resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/vlans",
            json={"vlan_id": str(vlan.id)},
            headers=auth_headers,
        )
        assert add_resp.status_code == 201
        # Delete it
        del_resp = await client.delete(
            f"/api/v1/route-servers/{rs.id}/vlans/{vlan.id}",
            headers=auth_headers,
        )
        assert del_resp.status_code == 204
