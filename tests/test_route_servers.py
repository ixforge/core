"""Tests for Route Server CRUD endpoints."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import (
    BGPAdminState,
    BGPOperState,
    ConnectionState,
    ConnectionType,
    MemberState,
    PeeringPolicy,
    TrunkState,
    VLANType,
)
from ixforge.models.bgp_session import BGPSession
from ixforge.models.connection import Connection
from ixforge.models.ip import IPPool
from ixforge.models.ixp import IXP
from ixforge.models.location import Location
from ixforge.models.member import Member
from ixforge.models.route_server import RouteServer
from ixforge.models.rs_ip_assignment import RSIPAssignment
from ixforge.models.switch import Switch
from ixforge.models.trunk import Trunk, TrunkVLAN
from ixforge.models.vlan import VLAN


class TestRouteServerCRUD:
    async def test_create_route_server(self, client: AsyncClient, auth_headers: dict, ixp: IXP):
        resp = await client.post(
            "/api/v1/route-servers",
            headers=auth_headers,
            json={
                "name": "rs1",
                "is_active": True,
                "notes": "Test route server",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "rs1"
        assert body["is_active"] is True
        assert body["notes"] == "Test route server"
        assert body["last_heartbeat_at"] is None
        assert body["agent_version"] is None

    async def test_create_route_server_minimal(self, client: AsyncClient, auth_headers: dict, ixp: IXP):
        resp = await client.post(
            "/api/v1/route-servers",
            headers=auth_headers,
            json={"name": "rs-minimal"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "rs-minimal"
        assert body["is_active"] is True
        assert body["notes"] is None

    async def test_create_route_server_notes_too_long_rejected(
        self, client: AsyncClient, auth_headers: dict, ixp: IXP
    ):
        resp = await client.post(
            "/api/v1/route-servers",
            headers=auth_headers,
            json={"name": "rs-long-notes", "notes": "x" * 1001},
        )
        assert resp.status_code == 422

    async def test_create_route_server_whitespace_notes_becomes_null(
        self, client: AsyncClient, auth_headers: dict, ixp: IXP
    ):
        resp = await client.post(
            "/api/v1/route-servers",
            headers=auth_headers,
            json={"name": "rs-blank-notes", "notes": "   "},
        )
        assert resp.status_code == 201
        assert resp.json()["notes"] is None

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
            ip_v4="192.0.2.251",
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
                ip_v4=f"192.0.2.{240 + i}",
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
            ip_v4="192.0.2.245",
            is_active=True,
        )
        db_session.add(rs)
        await db_session.flush()

        resp = await client.patch(
            f"/api/v1/route-servers/{rs.id}",
            headers=auth_headers,
            json={"name": "rs-new", "is_active": False, "notes": "Updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "rs-new"
        assert resp.json()["is_active"] is False
        assert resp.json()["notes"] == "Updated"

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
            ip_v4="192.0.2.249",
            is_active=True,
        )
        db_session.add(rs)
        await db_session.flush()

        resp = await client.delete(f"/api/v1/route-servers/{rs.id}", headers=auth_headers)
        assert resp.status_code == 204

    async def test_delete_rs_with_bgp_sessions_returns_409(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Deleting a RS with active BGP sessions must return 409"""
        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="rs-bgp-del",
            is_active=True,
        )
        db_session.add(rs)

        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="BGP Del Test",
            short_name="BDT",
            asn=64600,
            state=MemberState.active,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)

        location = Location(
            id=uuid.uuid4(), ixp_id=ixp.id, name="DC-del", city="Test", country="US",
        )
        db_session.add(location)
        await db_session.flush()

        switch = Switch(
            id=uuid.uuid4(), ixp_id=ixp.id, name="sw-del", location_id=location.id,
        )
        db_session.add(switch)
        await db_session.flush()

        trunk = Trunk(
            id=uuid.uuid4(), ixp_id=ixp.id, member_id=member.id,
            name="ae0", state=TrunkState.active,
        )
        db_session.add(trunk)
        vlan = VLAN(id=uuid.uuid4(), ixp_id=ixp.id, name="Peering", vid=100, type=VLANType.production)
        db_session.add(vlan)
        await db_session.flush()
        trunk_vlan = TrunkVLAN(id=uuid.uuid4(), ixp_id=ixp.id, trunk_id=trunk.id, vlan_id=vlan.id)
        db_session.add(trunk_vlan)

        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            trunk_id=trunk.id,
            switch_id=switch.id,
            name="eth-del",
            type=ConnectionType.physical,
            state=ConnectionState.active,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

        bgp = BGPSession(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            route_server_id=rs.id,
            trunk_vlan_id=trunk_vlan.id,
            admin_state=BGPAdminState.up,
            oper_state=BGPOperState.up,
            af=4,
        )
        db_session.add(bgp)
        await db_session.flush()

        resp = await client.delete(f"/api/v1/route-servers/{rs.id}", headers=auth_headers)
        assert resp.status_code == 409

    async def test_delete_rs_with_ip_assignments_returns_409(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Deleting a RS with IP assignments must return 409"""
        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="rs-ip-del",
            is_active=True,
        )
        db_session.add(rs)

        vlan = VLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="RS Del VLAN",
            vid=900,
            type=VLANType.production,
        )
        db_session.add(vlan)
        await db_session.flush()

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="198.51.100.0/24",
            af=4,
        )
        db_session.add(pool)
        await db_session.flush()

        rs_ip = RSIPAssignment(
            ixp_id=ixp.id,
            route_server_id=rs.id,
            pool_id=pool.id,
            address="198.51.100.1",
            af=4,
        )
        db_session.add(rs_ip)
        await db_session.flush()

        resp = await client.delete(f"/api/v1/route-servers/{rs.id}", headers=auth_headers)
        assert resp.status_code == 409
