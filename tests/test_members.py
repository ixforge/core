"""Tests for Member CRUD and state machine transitions."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import (
    ConnectionState,
    ConnectionType,
    CustomFieldEntityType,
    MemberState,
    PeeringPolicy,
    TrunkState,
    VLANType,
)
from ixforge.enums import (
    CustomFieldType as CFType,
)
from ixforge.models.connection import Connection
from ixforge.models.custom_field import CustomFieldDefinition
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.ixp import IXP
from ixforge.models.location import Location
from ixforge.models.member import Member
from ixforge.models.switch import Switch
from ixforge.models.trunk import Trunk, TrunkVLAN
from ixforge.models.vlan import VLAN
from ixforge.schemas.member import MemberCreate, MemberUpdate

# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestMemberCRUD:
    async def test_create_member(self, client: AsyncClient, auth_headers: dict, ixp: IXP):
        resp = await client.post(
            "/api/v1/members",
            headers=auth_headers,
            json={
                "name": "Acme Networks",
                "short_name": "ACME",
                "asn": 64512,
                "peering_policy": "open",
                "website": "https://acme.example.net",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Acme Networks"
        assert body["short_name"] == "ACME"
        assert body["asn"] == 64512
        assert body["state"] == "prospect"
        assert body["ixp_id"] == str(ixp.id)

    async def test_get_member(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Fetch Me Inc",
            short_name="FMI",
            asn=64600,
            state=MemberState.prospect,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        resp = await client.get(
            f"/api/v1/members/{member.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(member.id)
        assert body["name"] == "Fetch Me Inc"

    async def test_get_member_not_found(self, client: AsyncClient, auth_headers: dict, ixp: IXP):
        fake_id = uuid.uuid4()
        resp = await client.get(
            f"/api/v1/members/{fake_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_list_members(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        for i in range(3):
            m = Member(
                id=uuid.uuid4(),
                ixp_id=ixp.id,
                name=f"List Net {i}",
                short_name=f"LN{i}",
                asn=64700 + i,
                state=MemberState.prospect,
                peering_policy=PeeringPolicy.open,
            )
            db_session.add(m)
        await db_session.flush()

        resp = await client.get("/api/v1/members", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) >= 3

    async def test_update_member(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Old Name",
            short_name="OLD",
            asn=64800,
            state=MemberState.prospect,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        resp = await client.patch(
            f"/api/v1/members/{member.id}",
            headers=auth_headers,
            json={"name": "New Name", "peering_policy": "selective"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "New Name"
        assert body["peering_policy"] == "selective"

    async def test_create_duplicate_asn_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Original",
            short_name="ORIG",
            asn=64999,
            state=MemberState.prospect,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        resp = await client.post(
            "/api/v1/members",
            headers=auth_headers,
            json={
                "name": "Duplicate ASN",
                "short_name": "DUP",
                "asn": 64999,
            },
        )
        assert resp.status_code == 409

    async def test_create_member_country_uppercase(
        self, client: AsyncClient, auth_headers: dict, ixp: IXP
    ):
        """Country should be auto-uppercased"""
        resp = await client.post(
            "/api/v1/members",
            headers=auth_headers,
            json={
                "name": "Country Test Net",
                "short_name": "CTN",
                "asn": 64550,
                "country": "cl",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["country"] == "CL"

    async def test_create_member_country_invalid_rejected(self) -> None:
        """Country with non-alpha characters should be rejected at schema level"""
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MemberCreate(name="Bad", short_name="B", asn=1, country="1X")

    async def test_update_member_country_uppercase(self) -> None:
        """MemberUpdate country should also auto-uppercase"""
        data = MemberUpdate(country="us")
        assert data.country == "US"

    async def test_create_member_required_custom_field_without_extra_data(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Creating a member without extra_data when a required custom field exists should fail"""
        cf = CustomFieldDefinition(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            entity_type=CustomFieldEntityType.member,
            field_name="contract_id",
            field_type=CFType.string,
            is_required=True,
        )
        db_session.add(cf)
        await db_session.flush()

        resp = await client.post(
            "/api/v1/members",
            headers=auth_headers,
            json={
                "name": "No Extra Data Net",
                "short_name": "NEDN",
                "asn": 64513,
            },
        )
        assert resp.status_code == 422

    async def test_update_member_extra_data_null_with_required_field(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Updating a member with extra_data=null when a required custom field exists should fail"""
        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Extra Data Net",
            short_name="EDN",
            asn=64514,
            state=MemberState.prospect,
            peering_policy=PeeringPolicy.open,
            extra_data={"contract_id": "C-001"},
        )
        db_session.add(member)
        await db_session.flush()

        cf = CustomFieldDefinition(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            entity_type=CustomFieldEntityType.member,
            field_name="contract_id",
            field_type=CFType.string,
            is_required=True,
        )
        db_session.add(cf)
        await db_session.flush()

        resp = await client.patch(
            f"/api/v1/members/{member.id}",
            headers=auth_headers,
            json={"extra_data": None},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


async def _create_active_trunk_setup(
    db_session: AsyncSession, ixp: IXP, member: Member,
) -> tuple[Trunk, TrunkVLAN, Connection, VLAN, IPPool, IPAssignment]:
    """Create a complete active trunk with VLAN, connection, and IP assignment."""
    trunk = Trunk(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        member_id=member.id,
        name=f"ae{uuid.uuid4().hex[:4]}",
        state=TrunkState.active,
    )
    db_session.add(trunk)
    await db_session.flush()

    location = Location(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name=f"DC-{uuid.uuid4().hex[:6]}",
        city="Test",
        country="US",
    )
    db_session.add(location)
    await db_session.flush()

    switch = Switch(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name=f"sw-{uuid.uuid4().hex[:6]}",
        location_id=location.id,
        is_active=True,
    )
    db_session.add(switch)
    await db_session.flush()

    vlan = VLAN(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name=f"VLAN-{uuid.uuid4().hex[:6]}",
        vid=100 + hash(uuid.uuid4()) % 3900,
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
        switch_id=switch.id,
        name=f"Ethernet{uuid.uuid4().hex[:4]}",
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
        network="192.0.2.0/24",
        af=4,
    )
    db_session.add(pool)
    await db_session.flush()

    ip_assignment = IPAssignment(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        pool_id=pool.id,
        trunk_vlan_id=trunk_vlan.id,
        address="192.0.2.2",
    )
    db_session.add(ip_assignment)
    await db_session.flush()

    return trunk, trunk_vlan, conn, vlan, pool, ip_assignment


class TestMemberStateMachine:
    async def test_prospect_to_provisioning(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Transition Net",
            short_name="TRN",
            asn=65001,
            state=MemberState.prospect,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/members/{member.id}/transition",
            headers=auth_headers,
            json={"state": "provisioning"},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "provisioning"

    async def test_provisioning_to_active_with_trunk(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Provisioning -> active requires at least one active trunk."""
        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Active Net",
            short_name="ACT",
            asn=65002,
            state=MemberState.provisioning,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        # Create an active trunk
        await _create_active_trunk_setup(db_session, ixp, member)

        # Now transition should succeed
        resp = await client.post(
            f"/api/v1/members/{member.id}/transition",
            headers=auth_headers,
            json={"state": "active"},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "active"

    async def test_invalid_transition_prospect_to_active(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Cannot jump from prospect directly to active."""
        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Invalid Trans",
            short_name="INV",
            asn=65003,
            state=MemberState.prospect,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/members/{member.id}/transition",
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
        """Cannot go backwards from active to provisioning."""
        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Active Back",
            short_name="ACTB",
            asn=65004,
            state=MemberState.active,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/members/{member.id}/transition",
            headers=auth_headers,
            json={"state": "provisioning"},
        )
        assert resp.status_code == 422

    async def test_provisioning_to_terminated(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Terminated Net",
            short_name="TERM",
            asn=65005,
            state=MemberState.provisioning,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/members/{member.id}/transition",
            headers=auth_headers,
            json={"state": "terminated"},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "terminated"

    async def test_provisioning_to_active_without_trunk_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Provisioning -> active without an active trunk should fail."""
        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="No Trunk Net",
            short_name="NTRK",
            asn=65006,
            state=MemberState.provisioning,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/members/{member.id}/transition",
            headers=auth_headers,
            json={"state": "active"},
        )
        assert resp.status_code == 422

    async def test_terminate_member_with_active_trunk_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Cannot terminate a member that has non-decommissioned trunks."""
        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Term Trunk Net",
            short_name="TTN",
            asn=65007,
            state=MemberState.provisioning,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        trunk, _trunk_vlan, _conn, _vlan, _pool, _ip_assignment = await _create_active_trunk_setup(
            db_session, ixp, member,
        )

        # Activate the member (has active trunk)
        resp = await client.post(
            f"/api/v1/members/{member.id}/transition",
            headers=auth_headers,
            json={"state": "active"},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "active"

        # Try to terminate with active trunk -> should fail
        resp = await client.post(
            f"/api/v1/members/{member.id}/transition",
            headers=auth_headers,
            json={"state": "terminated"},
        )
        assert resp.status_code == 422

        # Decommission the trunk: set trunk state directly for test
        trunk.state = TrunkState.decommissioned
        await db_session.flush()

        # Now termination should succeed
        resp = await client.post(
            f"/api/v1/members/{member.id}/transition",
            headers=auth_headers,
            json={"state": "terminated"},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "terminated"
