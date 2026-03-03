"""Tests for Member CRUD and state machine transitions."""

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


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


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

    async def test_provisioning_to_active_with_connection(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Provisioning -> active requires at least one complete connection."""
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

        # Create the supporting infrastructure.
        switch = Switch(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="sw-test",
            hostname="sw-test.ixp.example.net",
            is_active=True,
        )
        db_session.add(switch)
        await db_session.flush()

        port = Port(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            switch_id=switch.id,
            name="Ethernet1",
            speed=10000,
            type=PortType.member,
            is_active=True,
        )
        db_session.add(port)
        await db_session.flush()

        vlan = VLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Peering VLAN",
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

        conn_vlan = ConnectionVLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            connection_id=conn.id,
            vlan_id=vlan.id,
            tagged=False,
        )
        db_session.add(conn_vlan)
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
            connection_id=conn.id,
            address="192.0.2.2",
        )
        db_session.add(ip_assignment)
        await db_session.flush()

        # Now transition should succeed.
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

    async def test_provisioning_to_active_without_connection_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Provisioning -> active without a complete connection should fail."""
        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="No Conn Net",
            short_name="NCON",
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

    async def test_terminate_member_with_active_connection_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Cannot terminate a member that has non-decommissioned connections."""
        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Term Conn Net",
            short_name="TCN",
            asn=65007,
            state=MemberState.provisioning,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        switch = Switch(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="sw-term",
            hostname="sw-term.ixp.example.net",
            is_active=True,
        )
        db_session.add(switch)
        await db_session.flush()

        port = Port(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            switch_id=switch.id,
            name="Ethernet1",
            speed=10000,
            type=PortType.member,
            is_active=True,
        )
        db_session.add(port)
        await db_session.flush()

        vlan = VLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Peering VLAN",
            vid=200,
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

        conn_vlan = ConnectionVLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            connection_id=conn.id,
            vlan_id=vlan.id,
            tagged=False,
        )
        db_session.add(conn_vlan)
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

        ip_assignment = IPAssignment(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            pool_id=pool.id,
            connection_id=conn.id,
            address="198.51.100.2",
        )
        db_session.add(ip_assignment)
        await db_session.flush()

        # Activate the member (has complete connection)
        resp = await client.post(
            f"/api/v1/members/{member.id}/transition",
            headers=auth_headers,
            json={"state": "active"},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "active"

        # Try to terminate with active connection -> should fail
        resp = await client.post(
            f"/api/v1/members/{member.id}/transition",
            headers=auth_headers,
            json={"state": "terminated"},
        )
        assert resp.status_code == 422

        # Decommission the connection: disable, release resources, decommission
        resp = await client.post(
            f"/api/v1/connections/{conn.id}/transition",
            headers=auth_headers,
            json={"state": "disabled"},
        )
        assert resp.status_code == 200

        resp = await client.delete(
            f"/api/v1/connections/{conn.id}/ips/{ip_assignment.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204

        resp = await client.delete(
            f"/api/v1/connections/{conn.id}/vlans/{vlan.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204

        resp = await client.post(
            f"/api/v1/connections/{conn.id}/transition",
            headers=auth_headers,
            json={"state": "decommissioned"},
        )
        assert resp.status_code == 200

        # Now termination should succeed
        resp = await client.post(
            f"/api/v1/members/{member.id}/transition",
            headers=auth_headers,
            json={"state": "terminated"},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "terminated"
