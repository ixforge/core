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
    VLANType,
)
from ixforge.models.bgp_session import BGPSession
from ixforge.models.connection import Connection
from ixforge.models.ip import IPPool
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.models.route_server import RouteServer
from ixforge.models.rs_ip_assignment import RSIPAssignment
from ixforge.models.vlan import VLAN


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

    async def test_create_duplicate_hostname_returns_409(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Creating a RS with a duplicate hostname should return 409"""
        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="rs-dup",
            hostname="rs-dup.example.net",
            asn=65000,
            software="bird",
            is_active=True,
        )
        db_session.add(rs)
        await db_session.flush()

        resp = await client.post(
            "/api/v1/route-servers",
            headers=auth_headers,
            json={
                "name": "rs-dup-2",
                "hostname": "rs-dup.example.net",
                "asn": 65000,
            },
        )
        assert resp.status_code == 409

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
            hostname="rs-bgp-del.example.net",
            asn=65000,
            software="bird",
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
        await db_session.flush()

        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
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
            connection_id=conn.id,
            peer_ip="192.0.2.10",
            peer_asn=64600,
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
            hostname="rs-ip-del.example.net",
            asn=65000,
            software="bird",
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
