"""Tests for BGP Session endpoints."""

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
)
from ixforge.models.bgp_session import BGPSession
from ixforge.models.connection import Connection
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.models.route_server import RouteServer


async def _setup_bgp_session(db: AsyncSession, ixp: IXP) -> tuple[RouteServer, BGPSession]:
    rs = RouteServer(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name="rs-bgp",
        hostname="rs-bgp.example.net",
        ip_v4="192.0.2.250",
        asn=65000,
        software="bird",
        is_active=True,
    )
    db.add(rs)

    member = Member(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name="BGP Test Net",
        short_name="BGPT",
        asn=64600,
        state=MemberState.active,
        peering_policy=PeeringPolicy.open,
    )
    db.add(member)
    await db.flush()

    conn = Connection(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        member_id=member.id,
        type=ConnectionType.physical,
        state=ConnectionState.active,
        speed=10000,
    )
    db.add(conn)
    await db.flush()

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
        max_prefixes=100,
    )
    db.add(bgp)
    await db.flush()
    return rs, bgp


class TestBGPSessionEndpoints:
    async def test_list_bgp_sessions(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs, _bgp = await _setup_bgp_session(db_session, ixp)

        resp = await client.get(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            params={"route_server_id": str(rs.id)},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1
        assert items[0]["peer_asn"] == 64600

    async def test_get_bgp_session(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        _rs, bgp = await _setup_bgp_session(db_session, ixp)

        resp = await client.get(f"/api/v1/bgp-sessions/{bgp.id}", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["peer_ip"] == "192.0.2.10"
        assert body["admin_state"] == "up"
        assert body["oper_state"] == "up"

    async def test_update_admin_state_to_down(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        _rs, bgp = await _setup_bgp_session(db_session, ixp)

        resp = await client.patch(
            f"/api/v1/bgp-sessions/{bgp.id}",
            headers=auth_headers,
            json={"admin_state": "down"},
        )
        assert resp.status_code == 200
        assert resp.json()["admin_state"] == "down"

    async def test_update_admin_state_to_up(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        _rs, bgp = await _setup_bgp_session(db_session, ixp)
        bgp.admin_state = BGPAdminState.down
        await db_session.flush()

        resp = await client.patch(
            f"/api/v1/bgp-sessions/{bgp.id}",
            headers=auth_headers,
            json={"admin_state": "up"},
        )
        assert resp.status_code == 200
        assert resp.json()["admin_state"] == "up"

    async def test_get_nonexistent_bgp_session(
        self, client: AsyncClient, auth_headers: dict, ixp: IXP
    ):
        resp = await client.get(f"/api/v1/bgp-sessions/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404
