"""Tests for IPAM: pool creation, sequential & manual IP allocation, reserved IPs."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import (
    ConnectionState,
    ConnectionType,
    MemberState,
    PeeringPolicy,
    VLANType,
)
from ixforge.models.connection import Connection
from ixforge.models.ip import IPPool
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.models.vlan import VLAN

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_vlan_and_member(
    db_session: AsyncSession, ixp: IXP
) -> tuple[VLAN, Member, Connection]:
    """Create a VLAN, member, and connection for IP allocation tests."""
    vlan = VLAN(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name="IPAM Test VLAN",
        vid=200,
        type=VLANType.production,
    )
    db_session.add(vlan)

    member = Member(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name="IPAM Test Member",
        short_name="IPM",
        asn=65100,
        state=MemberState.provisioning,
        peering_policy=PeeringPolicy.open,
    )
    db_session.add(member)
    await db_session.flush()

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

    return vlan, member, conn


# ---------------------------------------------------------------------------
# Pool creation
# ---------------------------------------------------------------------------


class TestIPPoolCreation:
    async def test_create_ipv4_pool(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        vlan = VLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Pool Create VLAN",
            vid=300,
            type=VLANType.production,
        )
        db_session.add(vlan)
        await db_session.flush()

        resp = await client.post(
            "/api/v1/ip-pools",
            headers=auth_headers,
            json={
                "vlan_id": str(vlan.id),
                "network": "198.51.100.0/24",
                "gateway": "198.51.100.1",
                "af": 4,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["network"] == "198.51.100.0/24"
        assert body["gateway"] == "198.51.100.1"
        assert body["af"] == 4

    async def test_create_ipv6_pool(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        vlan = VLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="IPv6 Pool VLAN",
            vid=301,
            type=VLANType.production,
        )
        db_session.add(vlan)
        await db_session.flush()

        resp = await client.post(
            "/api/v1/ip-pools",
            headers=auth_headers,
            json={
                "vlan_id": str(vlan.id),
                "network": "2001:db8::/64",
                "gateway": "2001:db8::1",
                "af": 6,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["af"] == 6

    async def test_create_pool_invalid_cidr(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, ixp: IXP
    ):
        vlan = VLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Bad CIDR VLAN",
            vid=302,
            type=VLANType.production,
        )
        db_session.add(vlan)
        await db_session.flush()

        resp = await client.post(
            "/api/v1/ip-pools",
            headers=auth_headers,
            json={
                "vlan_id": str(vlan.id),
                "network": "not-a-cidr",
                "gateway": "192.0.2.1",
                "af": 4,
            },
        )
        assert resp.status_code == 422

    async def test_create_pool_gateway_outside_network(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, ixp: IXP
    ):
        vlan = VLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Bad GW VLAN",
            vid=303,
            type=VLANType.production,
        )
        db_session.add(vlan)
        await db_session.flush()

        resp = await client.post(
            "/api/v1/ip-pools",
            headers=auth_headers,
            json={
                "vlan_id": str(vlan.id),
                "network": "198.51.100.0/24",
                "gateway": "10.0.0.1",
                "af": 4,
            },
        )
        assert resp.status_code == 422

    async def test_create_pool_af_mismatch(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, ixp: IXP
    ):
        vlan = VLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="AF Mismatch VLAN",
            vid=304,
            type=VLANType.production,
        )
        db_session.add(vlan)
        await db_session.flush()

        resp = await client.post(
            "/api/v1/ip-pools",
            headers=auth_headers,
            json={
                "vlan_id": str(vlan.id),
                "network": "198.51.100.0/24",
                "gateway": "198.51.100.1",
                "af": 6,
            },
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Sequential allocation
# ---------------------------------------------------------------------------


class TestSequentialAllocation:
    async def test_allocate_first_ip(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        vlan, _member, conn = await _setup_vlan_and_member(db_session, ixp)

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="192.0.2.0/24",
            gateway="192.0.2.1",
            af=4,
        )
        db_session.add(pool)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/ip-pools/{pool.id}/assign",
            headers=auth_headers,
            json={"connection_id": str(conn.id)},
        )
        assert resp.status_code == 201
        body = resp.json()
        # First usable IP after skipping network (192.0.2.0) and gateway (192.0.2.1).
        assert body["address"] == "192.0.2.2"

    async def test_sequential_allocation_skips_gateway(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Allocating multiple IPs should skip reserved addresses."""
        vlan, member, conn1 = await _setup_vlan_and_member(db_session, ixp)

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="203.0.113.0/29",
            gateway="203.0.113.1",
            af=4,
        )
        db_session.add(pool)
        await db_session.flush()

        conn2 = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            type=ConnectionType.physical,
            state=ConnectionState.draft,
            speed=10000,
        )
        db_session.add(conn2)
        await db_session.flush()

        # First allocation: should be .2 (skip .0 network, .1 gateway).
        resp1 = await client.post(
            f"/api/v1/ip-pools/{pool.id}/assign",
            headers=auth_headers,
            json={"connection_id": str(conn1.id)},
        )
        assert resp1.status_code == 201
        assert resp1.json()["address"] == "203.0.113.2"

        # Second allocation: should be .3.
        resp2 = await client.post(
            f"/api/v1/ip-pools/{pool.id}/assign",
            headers=auth_headers,
            json={"connection_id": str(conn2.id)},
        )
        assert resp2.status_code == 201
        assert resp2.json()["address"] == "203.0.113.3"


# ---------------------------------------------------------------------------
# Manual allocation
# ---------------------------------------------------------------------------


class TestManualAllocation:
    async def test_manual_allocate_specific_ip(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        vlan, _member, conn = await _setup_vlan_and_member(db_session, ixp)

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="198.51.100.0/24",
            gateway="198.51.100.1",
            af=4,
        )
        db_session.add(pool)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/ip-pools/{pool.id}/assign",
            headers=auth_headers,
            json={"connection_id": str(conn.id), "address": "198.51.100.50"},
        )
        assert resp.status_code == 201
        assert resp.json()["address"] == "198.51.100.50"

    async def test_manual_allocate_outside_pool_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        vlan, _member, conn = await _setup_vlan_and_member(db_session, ixp)

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="198.51.100.0/24",
            gateway="198.51.100.1",
            af=4,
        )
        db_session.add(pool)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/ip-pools/{pool.id}/assign",
            headers=auth_headers,
            json={"connection_id": str(conn.id), "address": "10.0.0.5"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Reserved IP rejection
# ---------------------------------------------------------------------------


class TestReservedIPRejection:
    async def test_cannot_assign_gateway(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        vlan, _member, conn = await _setup_vlan_and_member(db_session, ixp)

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="198.51.100.0/24",
            gateway="198.51.100.1",
            af=4,
        )
        db_session.add(pool)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/ip-pools/{pool.id}/assign",
            headers=auth_headers,
            json={"connection_id": str(conn.id), "address": "198.51.100.1"},
        )
        assert resp.status_code == 422

    async def test_cannot_assign_network_address(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        vlan, _member, conn = await _setup_vlan_and_member(db_session, ixp)

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="198.51.100.0/24",
            gateway="198.51.100.1",
            af=4,
        )
        db_session.add(pool)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/ip-pools/{pool.id}/assign",
            headers=auth_headers,
            json={"connection_id": str(conn.id), "address": "198.51.100.0"},
        )
        assert resp.status_code == 422

    async def test_cannot_assign_broadcast_address(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        vlan, _member, conn = await _setup_vlan_and_member(db_session, ixp)

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="198.51.100.0/24",
            gateway="198.51.100.1",
            af=4,
        )
        db_session.add(pool)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/ip-pools/{pool.id}/assign",
            headers=auth_headers,
            json={"connection_id": str(conn.id), "address": "198.51.100.255"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Pool exhaustion
# ---------------------------------------------------------------------------


class TestPoolExhaustion:
    async def test_pool_exhausted_returns_conflict(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """A /30 pool has only 2 usable IPs (.1 is gateway, .0 is network, .3 is broadcast)"""
        vlan, member, conn1 = await _setup_vlan_and_member(db_session, ixp)

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="203.0.113.0/30",
            gateway="203.0.113.1",
            af=4,
        )
        db_session.add(pool)
        await db_session.flush()

        resp1 = await client.post(
            f"/api/v1/ip-pools/{pool.id}/assign",
            headers=auth_headers,
            json={"connection_id": str(conn1.id)},
        )
        assert resp1.status_code == 201
        assert resp1.json()["address"] == "203.0.113.2"

        conn2 = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            type=ConnectionType.physical,
            state=ConnectionState.draft,
            speed=10000,
        )
        db_session.add(conn2)
        await db_session.flush()

        resp2 = await client.post(
            f"/api/v1/ip-pools/{pool.id}/assign",
            headers=auth_headers,
            json={"connection_id": str(conn2.id)},
        )
        assert resp2.status_code == 409


# ---------------------------------------------------------------------------
# Sequential skips reserved
# ---------------------------------------------------------------------------


class TestSequentialSkipsReserved:
    async def test_sequential_skips_network_and_broadcast(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """In a /29 pool, sequential allocation should skip .0 (network), .1 (gw), and .7 (broadcast)"""
        vlan, member, conn1 = await _setup_vlan_and_member(db_session, ixp)

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="203.0.113.0/29",
            gateway="203.0.113.1",
            af=4,
        )
        db_session.add(pool)
        await db_session.flush()

        allocated: list[str] = []
        connections = [conn1]
        for _i in range(4):
            c = Connection(
                id=uuid.uuid4(),
                ixp_id=ixp.id,
                member_id=member.id,
                type=ConnectionType.physical,
                state=ConnectionState.draft,
                speed=10000,
            )
            db_session.add(c)
            connections.append(c)
        await db_session.flush()

        for conn in connections:
            resp = await client.post(
                f"/api/v1/ip-pools/{pool.id}/assign",
                headers=auth_headers,
                json={"connection_id": str(conn.id)},
            )
            assert resp.status_code == 201
            allocated.append(resp.json()["address"])

        assert "203.0.113.0" not in allocated
        assert "203.0.113.1" not in allocated
        assert "203.0.113.7" not in allocated
        assert allocated == [
            "203.0.113.2",
            "203.0.113.3",
            "203.0.113.4",
            "203.0.113.5",
            "203.0.113.6",
        ]


# ---------------------------------------------------------------------------
# IPv6 allocation
# ---------------------------------------------------------------------------


class TestIPv6Allocation:
    async def test_ipv6_sequential_allocation(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        vlan, _member, conn = await _setup_vlan_and_member(db_session, ixp)

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="2001:db8::/126",
            gateway="2001:db8::1",
            af=6,
        )
        db_session.add(pool)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/ip-pools/{pool.id}/assign",
            headers=auth_headers,
            json={"connection_id": str(conn.id)},
        )
        assert resp.status_code == 201
        body = resp.json()
        # IPv6 has no reserved network/broadcast, only gateway (::1) is skipped
        # So first available in 2001:db8::/126 is 2001:db8:: (::0)
        assert body["address"] == "2001:db8::"
        assert body["pool_id"] == str(pool.id)
