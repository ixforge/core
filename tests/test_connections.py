"""Tests for Connection CRUD, state machine, VLAN/IP management."""

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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_member(db: AsyncSession, ixp: IXP, **overrides) -> Member:
    defaults = {
        "id": uuid.uuid4(),
        "ixp_id": ixp.id,
        "name": f"Conn Test Net {uuid.uuid4().hex[:6]}",
        "short_name": f"CN{uuid.uuid4().hex[:4]}",
        "asn": 64512 + hash(uuid.uuid4()) % 1000,
        "state": MemberState.provisioning,
        "peering_policy": PeeringPolicy.open,
    }
    defaults.update(overrides)
    member = Member(**defaults)
    db.add(member)
    await db.flush()
    return member


async def _create_switch(db: AsyncSession, ixp: IXP) -> Switch:
    location = Location(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name=f"DC-{uuid.uuid4().hex[:6]}",
        city="Test",
        country="US",
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
    return switch


async def _create_connection(
    db: AsyncSession, ixp: IXP, member: Member, switch: Switch, **overrides
) -> Connection:
    """Create a connection with all required fields"""
    defaults = {
        "id": uuid.uuid4(),
        "ixp_id": ixp.id,
        "member_id": member.id,
        "switch_id": switch.id,
        "name": f"Ethernet{uuid.uuid4().hex[:4]}",
        "type": ConnectionType.physical,
        "state": ConnectionState.draft,
        "speed": 10000,
    }
    defaults.update(overrides)
    conn = Connection(**defaults)
    db.add(conn)
    await db.flush()
    return conn


async def _create_vlan(db: AsyncSession, ixp: IXP, **overrides) -> VLAN:
    defaults = {
        "id": uuid.uuid4(),
        "ixp_id": ixp.id,
        "name": f"Test VLAN {uuid.uuid4().hex[:6]}",
        "vid": 100 + hash(uuid.uuid4()) % 3900,
        "type": VLANType.production,
    }
    defaults.update(overrides)
    vlan = VLAN(**defaults)
    db.add(vlan)
    await db.flush()
    return vlan


async def _create_pool_and_assign_ip(
    db: AsyncSession, ixp: IXP, vlan: VLAN, connection: Connection
) -> IPAssignment:
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
        connection_id=connection.id,
        address="198.51.100.2",
    )
    db.add(assignment)
    await db.flush()
    return assignment


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestConnectionCRUD:
    async def test_create_connection(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)

        resp = await client.post(
            "/api/v1/connections",
            headers=auth_headers,
            json={
                "member_id": str(member.id),
                "switch_id": str(switch.id),
                "name": "Ethernet1",
                "type": "physical",
                "speed": 10000,
                "mac_address": "00:11:22:33:44:55",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["state"] == "draft"
        assert body["type"] == "physical"
        assert body["speed"] == 10000
        assert body["mac_address"] == "00:11:22:33:44:55"
        assert body["member_id"] == str(member.id)
        assert body["switch_id"] == str(switch.id)
        assert body["name"] == "Ethernet1"

    async def test_create_virtual_connection(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)

        resp = await client.post(
            "/api/v1/connections",
            headers=auth_headers,
            json={
                "member_id": str(member.id),
                "switch_id": str(switch.id),
                "name": "VirtualPort1",
                "type": "virtual",
                "speed": 10000,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["type"] == "virtual"

    async def test_create_connection_invalid_mac_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)

        resp = await client.post(
            "/api/v1/connections",
            headers=auth_headers,
            json={
                "member_id": str(member.id),
                "switch_id": str(switch.id),
                "name": "Ethernet1",
                "type": "physical",
                "speed": 10000,
                "mac_address": "not-a-mac",
            },
        )
        assert resp.status_code == 422

    async def test_get_connection(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        conn = await _create_connection(db_session, ixp, member, switch)

        resp = await client.get(
            f"/api/v1/connections/{conn.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == str(conn.id)

    async def test_get_connection_not_found(
        self, client: AsyncClient, auth_headers: dict, ixp: IXP
    ):
        resp = await client.get(
            f"/api/v1/connections/{uuid.uuid4()}",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_list_connections(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        for i in range(3):
            await _create_connection(
                db_session, ixp, member, switch, name=f"Ethernet{i}"
            )

        resp = await client.get(
            "/api/v1/connections",
            headers=auth_headers,
            params={"member_id": str(member.id)},
        )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 3

    async def test_update_connection(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        conn = await _create_connection(db_session, ixp, member, switch, speed=1000)

        resp = await client.patch(
            f"/api/v1/connections/{conn.id}",
            headers=auth_headers,
            json={"speed": 10000, "mac_address": "AA:BB:CC:DD:EE:FF"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["speed"] == 10000
        assert body["mac_address"] == "aa:bb:cc:dd:ee:ff"


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


class TestConnectionStateMachine:
    async def test_draft_to_provisioning(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        conn = await _create_connection(db_session, ixp, member, switch)

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/transition",
            headers=auth_headers,
            json={"state": "provisioning"},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "provisioning"

    async def test_provisioning_to_active_with_complete_setup(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        vlan = await _create_vlan(db_session, ixp)

        conn = await _create_connection(
            db_session, ixp, member, switch, state=ConnectionState.provisioning
        )

        # Assign VLAN
        conn_vlan = ConnectionVLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            connection_id=conn.id,
            vlan_id=vlan.id,

        )
        db_session.add(conn_vlan)
        await db_session.flush()

        # Assign IP
        await _create_pool_and_assign_ip(db_session, ixp, vlan, conn)

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/transition",
            headers=auth_headers,
            json={"state": "active"},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "active"

    async def test_provisioning_to_active_without_setup_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        conn = await _create_connection(
            db_session, ixp, member, switch, state=ConnectionState.provisioning
        )

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/transition",
            headers=auth_headers,
            json={"state": "active"},
        )
        assert resp.status_code == 422

    async def test_provisioning_to_decommissioned(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        conn = await _create_connection(
            db_session, ixp, member, switch, state=ConnectionState.provisioning
        )

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/transition",
            headers=auth_headers,
            json={"state": "decommissioned"},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "decommissioned"

    async def test_active_to_disabled(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        conn = await _create_connection(
            db_session, ixp, member, switch, state=ConnectionState.active
        )

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/transition",
            headers=auth_headers,
            json={"state": "disabled"},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "disabled"

    async def test_disabled_to_active(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """disabled -> active requires complete setup (VLAN + IP)."""
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        vlan = await _create_vlan(db_session, ixp)

        conn = await _create_connection(
            db_session, ixp, member, switch, state=ConnectionState.disabled
        )

        # Assign VLAN
        conn_vlan = ConnectionVLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            connection_id=conn.id,
            vlan_id=vlan.id,

        )
        db_session.add(conn_vlan)
        await db_session.flush()

        # Assign IP
        await _create_pool_and_assign_ip(db_session, ixp, vlan, conn)

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/transition",
            headers=auth_headers,
            json={"state": "active"},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "active"

    async def test_disabled_to_active_without_setup_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """disabled -> active without VLAN/IP should be rejected."""
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        conn = await _create_connection(
            db_session, ixp, member, switch, state=ConnectionState.disabled
        )

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/transition",
            headers=auth_headers,
            json={"state": "active"},
        )
        assert resp.status_code == 422

    async def test_invalid_transition_draft_to_active(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        conn = await _create_connection(db_session, ixp, member, switch)

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/transition",
            headers=auth_headers,
            json={"state": "active"},
        )
        assert resp.status_code == 422

    async def test_invalid_transition_active_to_provisioning(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        conn = await _create_connection(
            db_session, ixp, member, switch, state=ConnectionState.active
        )

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/transition",
            headers=auth_headers,
            json={"state": "provisioning"},
        )
        assert resp.status_code == 422

    async def test_decommission_with_bgp_sessions_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Cannot decommission a connection that still has BGP sessions."""
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        conn = await _create_connection(
            db_session, ixp, member, switch, state=ConnectionState.disabled
        )

        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="rs-decomm",
        )
        db_session.add(rs)
        await db_session.flush()

        bgp = BGPSession(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            route_server_id=rs.id,
            connection_id=conn.id,
            peer_ip="192.0.2.10",
            peer_asn=64600,
            admin_state=BGPAdminState.up,
            oper_state=BGPOperState.unknown,
            af=4,
        )
        db_session.add(bgp)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/transition",
            headers=auth_headers,
            json={"state": "decommissioned"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# VLAN assignment
# ---------------------------------------------------------------------------


class TestConnectionVLAN:
    async def test_assign_vlan(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        vlan = await _create_vlan(db_session, ixp)
        conn = await _create_connection(db_session, ixp, member, switch)

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/vlans",
            headers=auth_headers,
            json={"vlan_id": str(vlan.id)},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["vlan_id"] == str(vlan.id)

    async def test_assign_duplicate_vlan_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        vlan = await _create_vlan(db_session, ixp)
        conn = await _create_connection(db_session, ixp, member, switch)

        # First assignment
        cv = ConnectionVLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            connection_id=conn.id,
            vlan_id=vlan.id,

        )
        db_session.add(cv)
        await db_session.flush()

        # Duplicate
        resp = await client.post(
            f"/api/v1/connections/{conn.id}/vlans",
            headers=auth_headers,
            json={"vlan_id": str(vlan.id)},
        )
        assert resp.status_code == 409

    async def test_unassign_vlan(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        vlan = await _create_vlan(db_session, ixp)
        conn = await _create_connection(db_session, ixp, member, switch)

        cv = ConnectionVLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            connection_id=conn.id,
            vlan_id=vlan.id,

        )
        db_session.add(cv)
        await db_session.flush()

        resp = await client.delete(
            f"/api/v1/connections/{conn.id}/vlans/{vlan.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204

    async def test_unassign_vlan_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        conn = await _create_connection(db_session, ixp, member, switch)

        resp = await client.delete(
            f"/api/v1/connections/{conn.id}/vlans/{uuid.uuid4()}",
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# IP assignment via connection endpoints
# ---------------------------------------------------------------------------


class TestConnectionIP:
    async def test_assign_ip_sequential(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        vlan = await _create_vlan(db_session, ixp)
        conn = await _create_connection(db_session, ixp, member, switch)

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="203.0.113.0/24",
            af=4,
        )
        db_session.add(pool)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/ips",
            headers=auth_headers,
            json={"pool_id": str(pool.id)},
        )
        assert resp.status_code == 201
        assert resp.json()["address"] == "203.0.113.1"

    async def test_assign_ip_manual(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        vlan = await _create_vlan(db_session, ixp)
        conn = await _create_connection(db_session, ixp, member, switch)

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="203.0.113.0/24",
            af=4,
        )
        db_session.add(pool)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/ips",
            headers=auth_headers,
            json={"pool_id": str(pool.id), "address": "203.0.113.50"},
        )
        assert resp.status_code == 201
        assert resp.json()["address"] == "203.0.113.50"

    async def test_release_ip(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        vlan = await _create_vlan(db_session, ixp)
        conn = await _create_connection(db_session, ixp, member, switch)

        assignment = await _create_pool_and_assign_ip(db_session, ixp, vlan, conn)

        resp = await client.delete(
            f"/api/v1/connections/{conn.id}/ips/{assignment.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204

    async def test_release_ip_wrong_connection_id_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Releasing an IP with wrong connection_id should return 404 (IDOR prevention)."""
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        vlan = await _create_vlan(db_session, ixp)

        # Connection A owns the IP
        conn_a = await _create_connection(
            db_session, ixp, member, switch, name="EthernetA"
        )

        # Connection B is the attacker
        conn_b = await _create_connection(
            db_session, ixp, member, switch, name="EthernetB"
        )

        assignment = await _create_pool_and_assign_ip(db_session, ixp, vlan, conn_a)

        # Try to release A's IP using B's connection_id
        resp = await client.delete(
            f"/api/v1/connections/{conn_b.id}/ips/{assignment.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Business logic validation
# ---------------------------------------------------------------------------


class TestConnectionBusinessLogic:
    async def test_decommission_with_vlans_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        vlan = await _create_vlan(db_session, ixp)
        conn = await _create_connection(
            db_session, ixp, member, switch, state=ConnectionState.disabled
        )

        cv = ConnectionVLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            connection_id=conn.id,
            vlan_id=vlan.id,

        )
        db_session.add(cv)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/transition",
            headers=auth_headers,
            json={"state": "decommissioned"},
        )
        assert resp.status_code == 422

    async def test_assign_vlan_to_decommissioned_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        vlan = await _create_vlan(db_session, ixp)
        conn = await _create_connection(
            db_session, ixp, member, switch, state=ConnectionState.decommissioned
        )

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/vlans",
            headers=auth_headers,
            json={"vlan_id": str(vlan.id)},
        )
        assert resp.status_code == 422

    async def test_assign_ip_to_disabled_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        vlan = await _create_vlan(db_session, ixp)
        conn = await _create_connection(
            db_session, ixp, member, switch, state=ConnectionState.disabled
        )

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="203.0.113.0/24",
            af=4,
        )
        db_session.add(pool)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/ips",
            headers=auth_headers,
            json={"pool_id": str(pool.id)},
        )
        assert resp.status_code == 422

    async def test_create_connection_for_terminated_member_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp, state=MemberState.terminated)
        switch = await _create_switch(db_session, ixp)

        resp = await client.post(
            "/api/v1/connections",
            headers=auth_headers,
            json={
                "member_id": str(member.id),
                "switch_id": str(switch.id),
                "name": "Ethernet1",
                "type": "physical",
                "speed": 10000,
            },
        )
        assert resp.status_code == 422

    async def test_assign_vlan_from_other_ixp_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Assigning a VLAN that belongs to a different IXP must fail."""
        other_ixp = IXP(name="Other IXP", short_name="OIXP", asn=65999, country="AR", city="X")
        db_session.add(other_ixp)
        await db_session.flush()

        foreign_vlan = await _create_vlan(db_session, other_ixp, vid=500)

        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        conn = await _create_connection(db_session, ixp, member, switch)

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/vlans",
            headers=auth_headers,
            json={"vlan_id": str(foreign_vlan.id)},
        )
        assert resp.status_code == 404

    async def test_create_connection_with_member_from_other_ixp_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Creating a connection with a member from a different IXP must fail."""
        other_ixp = IXP(name="Other IXP 2", short_name="OIX2", asn=65998, country="AR", city="X")
        db_session.add(other_ixp)
        await db_session.flush()

        foreign_member = await _create_member(db_session, other_ixp)
        switch = await _create_switch(db_session, ixp)

        resp = await client.post(
            "/api/v1/connections",
            headers=auth_headers,
            json={
                "member_id": str(foreign_member.id),
                "switch_id": str(switch.id),
                "name": "Ethernet1",
                "type": "physical",
                "speed": 10000,
            },
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Connection deletion
# ---------------------------------------------------------------------------


class TestConnectionDelete:
    async def test_delete_decommissioned_connection(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        conn = await _create_connection(
            db_session, ixp, member, switch, state=ConnectionState.decommissioned
        )

        resp = await client.delete(
            f"/api/v1/connections/{conn.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204

    async def test_delete_active_connection_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        conn = await _create_connection(
            db_session, ixp, member, switch, state=ConnectionState.active
        )

        resp = await client.delete(
            f"/api/v1/connections/{conn.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_delete_nonexistent_connection(
        self,
        client: AsyncClient,
        auth_headers: dict,
        ixp: IXP,
    ):
        resp = await client.delete(
            f"/api/v1/connections/{uuid.uuid4()}",
            headers=auth_headers,
        )
        assert resp.status_code == 404
