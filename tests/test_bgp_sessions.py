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
    VLANType,
)
from ixforge.models.bgp_session import BGPSession
from ixforge.models.connection import Connection, ConnectionVLAN
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.ixp import IXP
from ixforge.models.location import Location
from ixforge.models.member import Member
from ixforge.models.route_server import RouteServer
from ixforge.models.switch import Switch
from ixforge.models.vlan import VLAN


async def _create_active_connection(
    db: AsyncSession, ixp: IXP, member: Member
) -> Connection:
    """Create a connection in active state with full setup (VLAN + IP)."""
    location = Location(
        id=uuid.uuid4(), ixp_id=ixp.id, name=f"DC-{uuid.uuid4().hex[:6]}",
        city="Test", country="US",
    )
    db.add(location)
    await db.flush()

    switch = Switch(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name=f"sw-{uuid.uuid4().hex[:6]}",
        location_id=location.id,
        is_active=True,
    )
    db.add(switch)
    await db.flush()

    conn = Connection(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        member_id=member.id,
        switch_id=switch.id,
        name=f"Ethernet{uuid.uuid4().hex[:4]}",
        type=ConnectionType.physical,
        state=ConnectionState.active,
        speed=10000,
    )
    db.add(conn)
    await db.flush()

    vlan = VLAN(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name=f"Test VLAN {uuid.uuid4().hex[:6]}",
        vid=100 + hash(uuid.uuid4()) % 3900,
        type=VLANType.production,
    )
    db.add(vlan)
    await db.flush()

    cv = ConnectionVLAN(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        connection_id=conn.id,
        vlan_id=vlan.id,
    )
    db.add(cv)
    await db.flush()

    pool = IPPool(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        vlan_id=vlan.id,
        network="198.51.100.0/24",
        af=4,
    )
    db.add(pool)
    await db.flush()

    assignment = IPAssignment(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        pool_id=pool.id,
        connection_id=conn.id,
        address=f"198.51.100.{2 + hash(uuid.uuid4()) % 200}",
    )
    db.add(assignment)
    await db.flush()

    return conn


async def _setup_bgp_session(db: AsyncSession, ixp: IXP) -> tuple[RouteServer, BGPSession]:
    rs = RouteServer(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name="rs-bgp",
        ip_v4="192.0.2.250",
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

    location = Location(
        id=uuid.uuid4(), ixp_id=ixp.id, name=f"DC-bgp-{uuid.uuid4().hex[:6]}",
        city="Test", country="US",
    )
    db.add(location)
    await db.flush()

    switch = Switch(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name=f"sw-bgp-{uuid.uuid4().hex[:6]}",
        location_id=location.id,
        is_active=True,
    )
    db.add(switch)
    await db.flush()

    conn = Connection(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        member_id=member.id,
        switch_id=switch.id,
        name=f"Ethernet{uuid.uuid4().hex[:4]}",
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


class TestBGPSessionCreate:
    async def test_create_bgp_session(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="rs-create",
            ip_v4="192.0.2.251",
            is_active=True,
        )
        db_session.add(rs)

        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Create Test Net",
            short_name="CTN",
            asn=64700,
            state=MemberState.active,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        conn = await _create_active_connection(db_session, ixp, member)

        resp = await client.post(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            json={
                "route_server_id": str(rs.id),
                "connection_id": str(conn.id),
                "peer_ip": "192.0.2.10",
                "peer_asn": 64700,
                "af": 4,
                "max_prefixes": 100,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["route_server_id"] == str(rs.id)
        assert body["connection_id"] == str(conn.id)
        assert body["peer_ip"] == "192.0.2.10"
        assert body["peer_asn"] == 64700
        assert body["af"] == 4
        assert body["admin_state"] == "up"
        assert body["oper_state"] == "unknown"
        assert body["max_prefixes"] == 100

    async def test_create_bgp_session_duplicate_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="rs-dup",
            ip_v4="192.0.2.252",
            is_active=True,
        )
        db_session.add(rs)

        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Dup Test Net",
            short_name="DTN",
            asn=64701,
            state=MemberState.active,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        conn = await _create_active_connection(db_session, ixp, member)

        payload = {
            "route_server_id": str(rs.id),
            "connection_id": str(conn.id),
            "peer_ip": "192.0.2.20",
            "peer_asn": 64701,
            "af": 4,
        }

        # First creation should succeed
        resp1 = await client.post(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            json=payload,
        )
        assert resp1.status_code == 201

        # Duplicate should be rejected (same RS + conn + AF)
        resp2 = await client.post(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            json=payload,
        )
        assert resp2.status_code == 409

    async def test_create_bgp_session_inactive_connection_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="rs-inact",
            ip_v4="192.0.2.253",
            is_active=True,
        )
        db_session.add(rs)

        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Inactive Test Net",
            short_name="ITN",
            asn=64702,
            state=MemberState.active,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        location = Location(
            id=uuid.uuid4(), ixp_id=ixp.id, name=f"DC-inact-{uuid.uuid4().hex[:6]}",
            city="Test", country="US",
        )
        db_session.add(location)
        await db_session.flush()

        switch = Switch(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name=f"sw-inact-{uuid.uuid4().hex[:6]}",
            location_id=location.id,
            is_active=True,
        )
        db_session.add(switch)
        await db_session.flush()

        # Connection in draft state (not active)
        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            switch_id=switch.id,
            name=f"Ethernet{uuid.uuid4().hex[:4]}",
            type=ConnectionType.physical,
            state=ConnectionState.draft,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

        resp = await client.post(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            json={
                "route_server_id": str(rs.id),
                "connection_id": str(conn.id),
                "peer_ip": "192.0.2.30",
                "peer_asn": 64702,
                "af": 4,
            },
        )
        assert resp.status_code == 422

    async def test_create_bgp_session_wrong_ixp_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        # RS belongs to a different IXP
        other_ixp = IXP(
            id=uuid.uuid4(),
            name="Other IXP",
            short_name=f"OIX{uuid.uuid4().hex[:4]}",
            asn=65999,
        )
        db_session.add(other_ixp)
        await db_session.flush()

        rs_other = RouteServer(
            id=uuid.uuid4(),
            ixp_id=other_ixp.id,
            name="rs-other",
            ip_v4="192.0.2.254",
            is_active=True,
        )
        db_session.add(rs_other)

        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Wrong IXP Test Net",
            short_name="WTN",
            asn=64703,
            state=MemberState.active,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        conn = await _create_active_connection(db_session, ixp, member)

        resp = await client.post(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            json={
                "route_server_id": str(rs_other.id),
                "connection_id": str(conn.id),
                "peer_ip": "192.0.2.40",
                "peer_asn": 64703,
                "af": 4,
            },
        )
        assert resp.status_code == 404


class TestBGPSessionConstraints:
    async def test_create_bgp_session_af_5_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        ixp: IXP,
    ):
        """af must be 4 or 6 (Literal), af=5 should fail Pydantic validation."""
        resp = await client.post(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            json={
                "route_server_id": str(uuid.uuid4()),
                "connection_id": str(uuid.uuid4()),
                "peer_ip": "192.0.2.10",
                "peer_asn": 64500,
                "af": 5,
            },
        )
        assert resp.status_code == 422

    async def test_create_bgp_session_zero_asn_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        ixp: IXP,
    ):
        """peer_asn=0 should fail Pydantic validation (gt=0)."""
        resp = await client.post(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            json={
                "route_server_id": str(uuid.uuid4()),
                "connection_id": str(uuid.uuid4()),
                "peer_ip": "192.0.2.10",
                "peer_asn": 0,
                "af": 4,
            },
        )
        assert resp.status_code == 422

    async def test_create_bgp_session_negative_asn_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        ixp: IXP,
    ):
        """peer_asn=-1 should fail Pydantic validation (gt=0)."""
        resp = await client.post(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            json={
                "route_server_id": str(uuid.uuid4()),
                "connection_id": str(uuid.uuid4()),
                "peer_ip": "192.0.2.10",
                "peer_asn": -1,
                "af": 4,
            },
        )
        assert resp.status_code == 422

    async def test_create_bgp_session_invalid_ip_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        ixp: IXP,
    ):
        """peer_ip='not-an-ip' should fail validation."""
        resp = await client.post(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            json={
                "route_server_id": str(uuid.uuid4()),
                "connection_id": str(uuid.uuid4()),
                "peer_ip": "not-an-ip",
                "peer_asn": 64500,
                "af": 4,
            },
        )
        assert resp.status_code == 422

    async def test_create_bgp_session_ipv6_with_af4_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        ixp: IXP,
    ):
        """IPv6 peer_ip with af=4 should fail validation."""
        resp = await client.post(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            json={
                "route_server_id": str(uuid.uuid4()),
                "connection_id": str(uuid.uuid4()),
                "peer_ip": "2001:db8::1",
                "peer_asn": 64500,
                "af": 4,
            },
        )
        assert resp.status_code == 422

    async def test_create_bgp_session_ipv4_with_af6_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        ixp: IXP,
    ):
        """IPv4 peer_ip with af=6 should fail validation."""
        resp = await client.post(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            json={
                "route_server_id": str(uuid.uuid4()),
                "connection_id": str(uuid.uuid4()),
                "peer_ip": "192.0.2.1",
                "peer_asn": 64500,
                "af": 6,
            },
        )
        assert resp.status_code == 422


class TestBGPSessionDelete:
    async def test_delete_bgp_session(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        _rs, bgp = await _setup_bgp_session(db_session, ixp)

        resp = await client.delete(
            f"/api/v1/bgp-sessions/{bgp.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204

    async def test_delete_bgp_session_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict,
        ixp: IXP,
    ):
        resp = await client.delete(
            f"/api/v1/bgp-sessions/{uuid.uuid4()}",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_delete_bgp_session_wrong_ixp_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Deleting a BGP session from a different IXP should return 404."""
        other_ixp = IXP(
            id=uuid.uuid4(),
            name="Other IXP Del",
            short_name=f"OID{uuid.uuid4().hex[:4]}",
            asn=65999,
        )
        db_session.add(other_ixp)
        await db_session.flush()

        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=other_ixp.id,
            name="rs-other-del",
            is_active=True,
        )
        db_session.add(rs)

        member = Member(
            id=uuid.uuid4(),
            ixp_id=other_ixp.id,
            name="Other Del Net",
            short_name="ODN",
            asn=64800,
            state=MemberState.active,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        location = Location(
            id=uuid.uuid4(), ixp_id=other_ixp.id, name=f"DC-other-{uuid.uuid4().hex[:6]}",
            city="Test", country="US",
        )
        db_session.add(location)
        await db_session.flush()

        switch = Switch(
            id=uuid.uuid4(),
            ixp_id=other_ixp.id,
            name=f"sw-other-{uuid.uuid4().hex[:6]}",
            location_id=location.id,
            is_active=True,
        )
        db_session.add(switch)
        await db_session.flush()

        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=other_ixp.id,
            member_id=member.id,
            switch_id=switch.id,
            name=f"Ethernet{uuid.uuid4().hex[:4]}",
            type=ConnectionType.physical,
            state=ConnectionState.active,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

        bgp = BGPSession(
            id=uuid.uuid4(),
            ixp_id=other_ixp.id,
            route_server_id=rs.id,
            connection_id=conn.id,
            peer_ip="192.0.2.99",
            peer_asn=64800,
            admin_state=BGPAdminState.up,
            oper_state=BGPOperState.unknown,
            af=4,
        )
        db_session.add(bgp)
        await db_session.flush()

        resp = await client.delete(
            f"/api/v1/bgp-sessions/{bgp.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 404
