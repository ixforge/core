"""Tests for Connection CRUD, state machine, VLAN/IP management."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import (
    ConnectionState,
    ConnectionType,
    MemberState,
    PeeringPolicy,
    PortType,
    VLANType,
)
from ixforge.models.connection import Connection, ConnectionVLAN
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.models.port import Port
from ixforge.models.switch import Switch
from ixforge.models.user import User
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


async def _create_switch_and_port(db: AsyncSession, ixp: IXP) -> tuple[Switch, Port]:
    switch = Switch(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name=f"sw-{uuid.uuid4().hex[:6]}",
        hostname="sw.test.example.net",
        is_active=True,
    )
    db.add(switch)
    await db.flush()

    port = Port(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        switch_id=switch.id,
        name=f"Ethernet{uuid.uuid4().hex[:4]}",
        speed=10000,
        type=PortType.member,
        is_active=True,
    )
    db.add(port)
    await db.flush()
    return switch, port


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
        gateway="198.51.100.1",
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

        resp = await client.post(
            "/api/v1/connections",
            headers=auth_headers,
            json={
                "member_id": str(member.id),
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

    async def test_create_virtual_connection(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)

        resp = await client.post(
            "/api/v1/connections",
            headers=auth_headers,
            json={
                "member_id": str(member.id),
                "type": "virtual",
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

        resp = await client.post(
            "/api/v1/connections",
            headers=auth_headers,
            json={
                "member_id": str(member.id),
                "type": "physical",
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
        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            type=ConnectionType.physical,
            state=ConnectionState.draft,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

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
        for _ in range(3):
            conn = Connection(
                id=uuid.uuid4(),
                ixp_id=ixp.id,
                member_id=member.id,
                type=ConnectionType.physical,
                state=ConnectionState.draft,
                speed=10000,
            )
            db_session.add(conn)
        await db_session.flush()

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
        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            type=ConnectionType.physical,
            state=ConnectionState.draft,
            speed=1000,
        )
        db_session.add(conn)
        await db_session.flush()

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
        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            type=ConnectionType.physical,
            state=ConnectionState.draft,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

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
        _switch, port = await _create_switch_and_port(db_session, ixp)
        vlan = await _create_vlan(db_session, ixp)

        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            port_id=port.id,
            type=ConnectionType.physical,
            state=ConnectionState.provisioning,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

        # Assign VLAN
        conn_vlan = ConnectionVLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            connection_id=conn.id,
            vlan_id=vlan.id,
            tagged=False,
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

    async def test_provisioning_to_active_without_port_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            type=ConnectionType.physical,
            state=ConnectionState.provisioning,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

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
        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            type=ConnectionType.physical,
            state=ConnectionState.provisioning,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

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
        """disabled -> active should work (re-enable)."""
        member = await _create_member(db_session, ixp)
        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            type=ConnectionType.physical,
            state=ConnectionState.disabled,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/transition",
            headers=auth_headers,
            json={"state": "active"},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "active"

    async def test_invalid_transition_draft_to_active(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            type=ConnectionType.physical,
            state=ConnectionState.draft,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

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

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/transition",
            headers=auth_headers,
            json={"state": "provisioning"},
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
        vlan = await _create_vlan(db_session, ixp)
        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            type=ConnectionType.physical,
            state=ConnectionState.draft,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/vlans",
            headers=auth_headers,
            json={"vlan_id": str(vlan.id), "tagged": False},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["vlan_id"] == str(vlan.id)
        assert body["tagged"] is False

    async def test_assign_duplicate_vlan_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        vlan = await _create_vlan(db_session, ixp)
        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            type=ConnectionType.physical,
            state=ConnectionState.draft,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

        # First assignment
        cv = ConnectionVLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            connection_id=conn.id,
            vlan_id=vlan.id,
            tagged=False,
        )
        db_session.add(cv)
        await db_session.flush()

        # Duplicate
        resp = await client.post(
            f"/api/v1/connections/{conn.id}/vlans",
            headers=auth_headers,
            json={"vlan_id": str(vlan.id), "tagged": True},
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
        vlan = await _create_vlan(db_session, ixp)
        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            type=ConnectionType.physical,
            state=ConnectionState.draft,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

        cv = ConnectionVLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            connection_id=conn.id,
            vlan_id=vlan.id,
            tagged=False,
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
        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            type=ConnectionType.physical,
            state=ConnectionState.draft,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

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
        vlan = await _create_vlan(db_session, ixp)
        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            type=ConnectionType.physical,
            state=ConnectionState.draft,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="203.0.113.0/24",
            gateway="203.0.113.1",
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
        assert resp.json()["address"] == "203.0.113.2"

    async def test_assign_ip_manual(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        vlan = await _create_vlan(db_session, ixp)
        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            type=ConnectionType.physical,
            state=ConnectionState.draft,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="203.0.113.0/24",
            gateway="203.0.113.1",
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
        vlan = await _create_vlan(db_session, ixp)
        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            type=ConnectionType.physical,
            state=ConnectionState.draft,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

        assignment = await _create_pool_and_assign_ip(db_session, ixp, vlan, conn)

        resp = await client.delete(
            f"/api/v1/connections/{conn.id}/ips/{assignment.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204
