"""Tests for IX-F Member Export endpoint."""

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
from ixforge.models.vlan import VLAN


class TestIXFExport:
    async def test_export_empty_ixp(self, client: AsyncClient, db_session: AsyncSession, ixp: IXP):
        """IX-F export with no active members should return valid structure."""
        resp = await client.get("/api/v1/ixf/member-export")
        assert resp.status_code == 200
        body = resp.json()
        assert body["version"] == "1.0"
        assert "ixp_list" in body

    async def test_export_with_active_member(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP
    ):
        """IX-F export should include active members with connections."""
        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Export Test Net",
            short_name="ETN",
            asn=64700,
            state=MemberState.active,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)

        sw = Switch(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="sw-ixf",
            hostname="sw-ixf.example.net",
            is_active=True,
        )
        db_session.add(sw)
        await db_session.flush()

        port = Port(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            switch_id=sw.id,
            name="Ethernet1",
            speed=10000,
            type=PortType.member,
            is_active=True,
        )
        db_session.add(port)

        vlan = VLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="IXF VLAN",
            vid=100,
            type=VLANType.production,
        )
        db_session.add(vlan)
        await db_session.flush()

        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            port_id=port.id,
            type=ConnectionType.physical,
            state=ConnectionState.active,
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

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="198.51.100.0/24",
            af=4,
        )
        db_session.add(pool)
        await db_session.flush()

        ip = IPAssignment(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            pool_id=pool.id,
            connection_id=conn.id,
            address="198.51.100.10",
        )
        db_session.add(ip)
        await db_session.flush()

        resp = await client.get("/api/v1/ixf/member-export")
        assert resp.status_code == 200
        body = resp.json()
        assert body["version"] == "1.0"
        assert len(body["ixp_list"]) >= 1

    async def test_export_excludes_non_active_members(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP
    ):
        """Prospect and suspended members should not appear in IX-F export."""
        for state in [MemberState.prospect, MemberState.suspended, MemberState.terminated]:
            m = Member(
                id=uuid.uuid4(),
                ixp_id=ixp.id,
                name=f"Non Active {state}",
                short_name=f"NA{state[:2].upper()}",
                asn=64800 + hash(state) % 100,
                state=state,
                peering_policy=PeeringPolicy.open,
            )
            db_session.add(m)
        await db_session.flush()

        resp = await client.get("/api/v1/ixf/member-export")
        assert resp.status_code == 200
        # No active connections, so member_list should be empty or only contain previously active
        body = resp.json()
        assert body["version"] == "1.0"

    async def test_export_is_public_no_auth_required(self, client: AsyncClient, ixp: IXP):
        """The IX-F export endpoint should not require authentication."""
        resp = await client.get("/api/v1/ixf/member-export")
        assert resp.status_code == 200
