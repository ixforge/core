"""Tests for IX-F Member Export endpoint."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import (
    ConnectionState,
    ConnectionType,
    MemberState,
    PeeringPolicy,
    TrunkState,
    VLANType,
)
from ixforge.models.connection import Connection
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.ixp import IXP
from ixforge.models.location import Location
from ixforge.models.member import Member
from ixforge.models.switch import Switch
from ixforge.models.trunk import Trunk, TrunkVLAN
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
        """IX-F export should include active members with trunks"""
        # Invalidate the in-memory export cache so we get fresh data
        from ixforge.api.v1 import ixf_export as ixf_mod

        ixf_mod._cache = (None, 0.0)

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

        trunk = Trunk(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            name="ae-ixf",
            state=TrunkState.active,
        )
        db_session.add(trunk)
        await db_session.flush()

        location = Location(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="DC-ixf",
            city="Test",
            country="US",
        )
        db_session.add(location)
        await db_session.flush()

        sw = Switch(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="sw-ixf",
            location_id=location.id,
            is_active=True,
        )
        db_session.add(sw)
        await db_session.flush()

        vlan = VLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="IXF VLAN",
            vid=100,
            type=VLANType.production,
        )
        db_session.add(vlan)
        await db_session.flush()

        trunk_vlan = TrunkVLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            trunk_id=trunk.id,
            vlan_id=vlan.id,
        )
        db_session.add(trunk_vlan)
        await db_session.flush()

        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            trunk_id=trunk.id,
            switch_id=sw.id,
            name="Ethernet1",
            type=ConnectionType.physical,
            state=ConnectionState.active,
            speed=10000,
        )
        db_session.add(conn)
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

        ip = IPAssignment(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            pool_id=pool.id,
            trunk_vlan_id=trunk_vlan.id,
            address="198.51.100.10",
        )
        db_session.add(ip)
        await db_session.flush()

        resp = await client.get("/api/v1/ixf/member-export")
        assert resp.status_code == 200
        body = resp.json()
        assert body["version"] == "1.0"
        assert len(body["ixp_list"]) >= 1

        # Verify member data is actually present in the export
        members_in_export = body.get("member_list", [])
        asns = [m["asnum"] for m in members_in_export]
        assert 64700 in asns, "Active member ASN 64700 should appear in export"

    async def test_export_excludes_non_active_members(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP
    ):
        """Prospect and suspended members should not appear in IX-F export."""
        for i, state in enumerate([MemberState.prospect, MemberState.suspended, MemberState.terminated]):
            m = Member(
                id=uuid.uuid4(),
                ixp_id=ixp.id,
                name=f"Non Active {state}",
                short_name=f"NA{state[:2].upper()}{i}",
                asn=64800 + i,
                state=state,
                peering_policy=PeeringPolicy.open,
            )
            db_session.add(m)
        await db_session.flush()

        resp = await client.get("/api/v1/ixf/member-export")
        assert resp.status_code == 200
        # Non-active members should not appear in export
        body = resp.json()
        assert body["version"] == "1.0"
        exported_asns = {m["asnum"] for m in body.get("member_list", [])}
        for i in range(3):
            assert 64800 + i not in exported_asns, "Non-active member should not appear in export"

    async def test_export_is_public_no_auth_required(self, client: AsyncClient, ixp: IXP):
        """The IX-F export endpoint should not require authentication."""
        resp = await client.get("/api/v1/ixf/member-export")
        assert resp.status_code == 200
