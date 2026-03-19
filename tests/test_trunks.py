"""Tests for Trunk service: CRUD, state machine, VLAN/IP management, connections."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import (
    BGPAdminState,
    BGPOperState,
    ConnectionState,
    ConnectionType,
    MemberState,
    PeeringPolicy,
    TrunkState,
    VLANType,
)
from ixforge.exceptions import ConflictError, NotFoundError, ValidationError
from ixforge.models.bgp_session import BGPSession
from ixforge.models.connection import Connection
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.ixp import IXP
from ixforge.models.location import Location
from ixforge.models.member import Member
from ixforge.models.route_server import RouteServer
from ixforge.models.switch import Switch
from ixforge.models.trunk import Trunk, TrunkVLAN
from ixforge.models.vlan import VLAN
from ixforge.models.vlan_member import VLANMember
from ixforge.schemas.common import CursorParams
from ixforge.schemas.connection import ConnectionCreate
from ixforge.schemas.trunk import TrunkCreate, TrunkUpdate
from ixforge.services import trunks

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_member(db: AsyncSession, ixp: IXP, **overrides) -> Member:
    defaults = {
        "id": uuid.uuid4(),
        "ixp_id": ixp.id,
        "name": f"Trunk Test Net {uuid.uuid4().hex[:6]}",
        "short_name": f"TN{uuid.uuid4().hex[:4]}",
        "asn": 64512 + hash(uuid.uuid4()) % 1000,
        "state": MemberState.provisioning,
        "peering_policy": PeeringPolicy.open,
    }
    defaults.update(overrides)
    member = Member(**defaults)
    db.add(member)
    await db.flush()
    return member


async def _create_trunk(
    db: AsyncSession, ixp: IXP, member: Member, **overrides
) -> Trunk:
    defaults = {
        "id": uuid.uuid4(),
        "ixp_id": ixp.id,
        "member_id": member.id,
        "name": f"Trunk-{uuid.uuid4().hex[:6]}",
        "state": TrunkState.draft,
    }
    defaults.update(overrides)
    trunk = Trunk(**defaults)
    db.add(trunk)
    await db.flush()
    return trunk


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


async def _create_trunk_vlan(
    db: AsyncSession, ixp: IXP, trunk: Trunk, vlan: VLAN
) -> TrunkVLAN:
    tv = TrunkVLAN(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        trunk_id=trunk.id,
        vlan_id=vlan.id,
    )
    db.add(tv)
    await db.flush()
    return tv


async def _create_pool(
    db: AsyncSession, ixp: IXP, vlan: VLAN, network: str = "198.51.100.0/24", af: int = 4
) -> IPPool:
    pool = IPPool(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        vlan_id=vlan.id,
        network=network,
        af=af,
    )
    db.add(pool)
    await db.flush()
    return pool


async def _create_ip_assignment(
    db: AsyncSession, ixp: IXP, pool: IPPool, trunk_vlan: TrunkVLAN, address: str
) -> IPAssignment:
    assignment = IPAssignment(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        pool_id=pool.id,
        trunk_vlan_id=trunk_vlan.id,
        address=address,
    )
    db.add(assignment)
    await db.flush()
    return assignment


async def _create_connection(
    db: AsyncSession, ixp: IXP, trunk: Trunk, switch: Switch, **overrides
) -> Connection:
    defaults = {
        "id": uuid.uuid4(),
        "ixp_id": ixp.id,
        "trunk_id": trunk.id,
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


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestTrunkCRUD:
    async def test_create_trunk(self, db_session: AsyncSession, ixp: IXP):
        member = await _create_member(db_session, ixp)
        data = TrunkCreate(member_id=member.id, name="Primary Trunk")

        trunk = await trunks.create(db_session, ixp.id, data)

        assert trunk.name == "Primary Trunk"
        assert trunk.state == TrunkState.draft
        assert trunk.member_id == member.id
        assert trunk.member.name == member.name

    async def test_create_trunk_with_mac_and_notes(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        data = TrunkCreate(
            member_id=member.id,
            name="Trunk with MAC",
            mac_address="AA:BB:CC:DD:EE:FF",
            notes="Test notes",
        )

        trunk = await trunks.create(db_session, ixp.id, data)

        assert trunk.mac_address == "aa:bb:cc:dd:ee:ff"
        assert trunk.notes == "Test notes"

    async def test_create_trunk_for_terminated_member_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp, state=MemberState.terminated)
        data = TrunkCreate(member_id=member.id, name="Bad Trunk")

        with pytest.raises(ValidationError, match="terminated member"):
            await trunks.create(db_session, ixp.id, data)

    async def test_create_trunk_nonexistent_member_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        data = TrunkCreate(member_id=uuid.uuid4(), name="Bad Trunk")

        with pytest.raises(NotFoundError):
            await trunks.create(db_session, ixp.id, data)

    async def test_create_trunk_member_from_other_ixp_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        other_ixp = IXP(
            name="Other IXP", short_name="OIXP", asn=65999, country="CL", city="X"
        )
        db_session.add(other_ixp)
        await db_session.flush()

        foreign_member = await _create_member(db_session, other_ixp)
        data = TrunkCreate(member_id=foreign_member.id, name="Bad Trunk")

        with pytest.raises(NotFoundError):
            await trunks.create(db_session, ixp.id, data)

    async def test_get_trunk(self, db_session: AsyncSession, ixp: IXP):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)

        result = await trunks.get(db_session, ixp.id, trunk.id)

        assert result.id == trunk.id
        assert result.member.name == member.name

    async def test_get_trunk_not_found(self, db_session: AsyncSession, ixp: IXP):
        with pytest.raises(NotFoundError):
            await trunks.get(db_session, ixp.id, uuid.uuid4())

    async def test_list_trunks(self, db_session: AsyncSession, ixp: IXP):
        member = await _create_member(db_session, ixp)
        for i in range(3):
            await _create_trunk(db_session, ixp, member, name=f"Trunk-{i}")

        result = await trunks.list_trunks(
            db_session, ixp.id, CursorParams(limit=10)
        )

        assert len(result.items) >= 3

    async def test_list_trunks_filter_by_member(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member_a = await _create_member(db_session, ixp)
        member_b = await _create_member(db_session, ixp)
        await _create_trunk(db_session, ixp, member_a, name="Trunk-A")
        await _create_trunk(db_session, ixp, member_b, name="Trunk-B")

        result = await trunks.list_trunks(
            db_session, ixp.id, CursorParams(limit=10), member_id=member_a.id
        )

        assert all(item.member_id == member_a.id for item in result.items)

    async def test_update_trunk(self, db_session: AsyncSession, ixp: IXP):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member, name="Old Name")

        data = TrunkUpdate(name="New Name", notes="Updated notes")
        result = await trunks.update(db_session, ixp.id, trunk.id, data)

        assert result.name == "New Name"
        assert result.notes == "Updated notes"

    async def test_update_decommissioned_trunk_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.decommissioned
        )

        data = TrunkUpdate(name="Nope")
        with pytest.raises(ValidationError, match="decommissioned"):
            await trunks.update(db_session, ixp.id, trunk.id, data)

    async def test_delete_decommissioned_trunk(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.decommissioned
        )

        await trunks.delete(db_session, ixp.id, trunk.id)

        with pytest.raises(NotFoundError):
            await trunks.get(db_session, ixp.id, trunk.id)

    async def test_delete_active_trunk_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.active
        )

        with pytest.raises(ValidationError, match="decommissioned"):
            await trunks.delete(db_session, ixp.id, trunk.id)


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


class TestTrunkStateMachine:
    async def test_draft_to_provisioning(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)

        result = await trunks.transition(
            db_session, trunk.id, TrunkState.provisioning, ixp_id=ixp.id
        )

        assert result.state == TrunkState.provisioning

    async def test_provisioning_to_active_with_complete_setup(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        vlan = await _create_vlan(db_session, ixp)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.provisioning
        )

        # Add connection
        await _create_connection(db_session, ixp, trunk, switch)

        # Assign VLAN
        tv = await _create_trunk_vlan(db_session, ixp, trunk, vlan)

        # Assign IP to production VLAN
        pool = await _create_pool(db_session, ixp, vlan)
        await _create_ip_assignment(db_session, ixp, pool, tv, "198.51.100.1")

        result = await trunks.transition(
            db_session, trunk.id, TrunkState.active, ixp_id=ixp.id
        )

        assert result.state == TrunkState.active

    async def test_provisioning_to_active_without_connection_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.provisioning
        )

        with pytest.raises(ValidationError, match="connection"):
            await trunks.transition(
                db_session, trunk.id, TrunkState.active, ixp_id=ixp.id
            )

    async def test_provisioning_to_active_without_vlan_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.provisioning
        )
        await _create_connection(db_session, ixp, trunk, switch)

        with pytest.raises(ValidationError, match="VLAN"):
            await trunks.transition(
                db_session, trunk.id, TrunkState.active, ixp_id=ixp.id
            )

    async def test_provisioning_to_active_production_vlan_without_ip_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        vlan = await _create_vlan(db_session, ixp)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.provisioning
        )
        await _create_connection(db_session, ixp, trunk, switch)
        await _create_trunk_vlan(db_session, ixp, trunk, vlan)

        with pytest.raises(ValidationError, match="IP"):
            await trunks.transition(
                db_session, trunk.id, TrunkState.active, ixp_id=ixp.id
            )

    async def test_provisioning_to_active_quarantine_vlan_no_ip_ok(
        self, db_session: AsyncSession, ixp: IXP
    ):
        """Non-production VLANs don't require IPs for activation"""
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        vlan = await _create_vlan(db_session, ixp, type=VLANType.quarantine)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.provisioning
        )
        await _create_connection(db_session, ixp, trunk, switch)
        await _create_trunk_vlan(db_session, ixp, trunk, vlan)

        result = await trunks.transition(
            db_session, trunk.id, TrunkState.active, ixp_id=ixp.id
        )

        assert result.state == TrunkState.active

    async def test_provisioning_to_decommissioned(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.provisioning
        )

        result = await trunks.transition(
            db_session, trunk.id, TrunkState.decommissioned, ixp_id=ixp.id
        )

        assert result.state == TrunkState.decommissioned

    async def test_active_to_disabled(self, db_session: AsyncSession, ixp: IXP):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.active
        )

        result = await trunks.transition(
            db_session, trunk.id, TrunkState.disabled, ixp_id=ixp.id
        )

        assert result.state == TrunkState.disabled

    async def test_disabled_to_active_with_setup(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        vlan = await _create_vlan(db_session, ixp)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.disabled
        )
        await _create_connection(db_session, ixp, trunk, switch)
        tv = await _create_trunk_vlan(db_session, ixp, trunk, vlan)
        pool = await _create_pool(db_session, ixp, vlan)
        await _create_ip_assignment(db_session, ixp, pool, tv, "198.51.100.1")

        result = await trunks.transition(
            db_session, trunk.id, TrunkState.active, ixp_id=ixp.id
        )

        assert result.state == TrunkState.active

    async def test_disabled_to_decommissioned_clean(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.disabled
        )

        result = await trunks.transition(
            db_session, trunk.id, TrunkState.decommissioned, ixp_id=ixp.id
        )

        assert result.state == TrunkState.decommissioned

    async def test_invalid_transition_draft_to_active(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)

        with pytest.raises(ValidationError, match="Cannot transition"):
            await trunks.transition(
                db_session, trunk.id, TrunkState.active, ixp_id=ixp.id
            )

    async def test_invalid_transition_active_to_provisioning(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.active
        )

        with pytest.raises(ValidationError, match="Cannot transition"):
            await trunks.transition(
                db_session, trunk.id, TrunkState.provisioning, ixp_id=ixp.id
            )

    async def test_decommission_with_bgp_sessions_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.disabled
        )
        vlan = await _create_vlan(db_session, ixp)
        tv = await _create_trunk_vlan(db_session, ixp, trunk, vlan)

        rs = RouteServer(id=uuid.uuid4(), ixp_id=ixp.id, name="rs-test")
        db_session.add(rs)
        await db_session.flush()

        bgp = BGPSession(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            route_server_id=rs.id,
            trunk_vlan_id=tv.id,
            peer_ip="192.0.2.10",
            peer_asn=64600,
            admin_state=BGPAdminState.up,
            oper_state=BGPOperState.unknown,
            af=4,
        )
        db_session.add(bgp)
        await db_session.flush()

        with pytest.raises(ValidationError, match="BGP"):
            await trunks.transition(
                db_session, trunk.id, TrunkState.decommissioned, ixp_id=ixp.id
            )

    async def test_decommission_with_ips_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.disabled
        )
        vlan = await _create_vlan(db_session, ixp)
        tv = await _create_trunk_vlan(db_session, ixp, trunk, vlan)
        pool = await _create_pool(db_session, ixp, vlan)
        await _create_ip_assignment(db_session, ixp, pool, tv, "198.51.100.1")

        with pytest.raises(ValidationError, match="IP"):
            await trunks.transition(
                db_session, trunk.id, TrunkState.decommissioned, ixp_id=ixp.id
            )

    async def test_decommission_with_vlans_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.disabled
        )
        vlan = await _create_vlan(db_session, ixp)
        await _create_trunk_vlan(db_session, ixp, trunk, vlan)

        with pytest.raises(ValidationError, match="VLAN"):
            await trunks.transition(
                db_session, trunk.id, TrunkState.decommissioned, ixp_id=ixp.id
            )

    async def test_decommission_with_non_decommissioned_connections_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.disabled
        )
        await _create_connection(
            db_session, ixp, trunk, switch, state=ConnectionState.draft
        )

        with pytest.raises(ValidationError, match="connections"):
            await trunks.transition(
                db_session, trunk.id, TrunkState.decommissioned, ixp_id=ixp.id
            )


# ---------------------------------------------------------------------------
# VLAN management
# ---------------------------------------------------------------------------


class TestTrunkVLAN:
    async def test_assign_vlan(self, db_session: AsyncSession, ixp: IXP):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)
        vlan = await _create_vlan(db_session, ixp)

        tv = await trunks.assign_vlan(db_session, ixp.id, trunk.id, vlan.id)

        assert tv.trunk_id == trunk.id
        assert tv.vlan_id == vlan.id
        assert tv.vlan.name == vlan.name

    async def test_assign_duplicate_vlan_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)
        vlan = await _create_vlan(db_session, ixp)

        await trunks.assign_vlan(db_session, ixp.id, trunk.id, vlan.id)

        with pytest.raises(ConflictError, match="already assigned"):
            await trunks.assign_vlan(db_session, ixp.id, trunk.id, vlan.id)

    async def test_assign_vlan_to_decommissioned_trunk_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.decommissioned
        )
        vlan = await _create_vlan(db_session, ixp)

        with pytest.raises(ValidationError, match="decommissioned"):
            await trunks.assign_vlan(db_session, ixp.id, trunk.id, vlan.id)

    async def test_assign_vlan_to_disabled_trunk_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.disabled
        )
        vlan = await _create_vlan(db_session, ixp)

        with pytest.raises(ValidationError, match="disabled"):
            await trunks.assign_vlan(db_session, ixp.id, trunk.id, vlan.id)

    async def test_assign_vlan_from_other_ixp_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        other_ixp = IXP(
            name="Other IXP", short_name="OIXP", asn=65999, country="CL", city="X"
        )
        db_session.add(other_ixp)
        await db_session.flush()

        foreign_vlan = await _create_vlan(db_session, other_ixp, vid=500)
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)

        with pytest.raises(NotFoundError):
            await trunks.assign_vlan(db_session, ixp.id, trunk.id, foreign_vlan.id)

    async def test_assign_private_vlan_authorized(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)
        vlan = await _create_vlan(db_session, ixp, type=VLANType.private)

        # Authorize member for private VLAN
        vm = VLANMember(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            member_id=member.id,
        )
        db_session.add(vm)
        await db_session.flush()

        tv = await trunks.assign_vlan(db_session, ixp.id, trunk.id, vlan.id)
        assert tv.vlan_id == vlan.id

    async def test_assign_private_vlan_unauthorized_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)
        vlan = await _create_vlan(db_session, ixp, type=VLANType.private)

        with pytest.raises(ValidationError, match="not authorized"):
            await trunks.assign_vlan(db_session, ixp.id, trunk.id, vlan.id)

    async def test_unassign_vlan(self, db_session: AsyncSession, ixp: IXP):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)
        vlan = await _create_vlan(db_session, ixp)
        tv = await _create_trunk_vlan(db_session, ixp, trunk, vlan)

        await trunks.unassign_vlan(db_session, ixp.id, trunk.id, tv.id)

        # Verify it's gone
        vlans = await trunks.list_vlans(db_session, ixp.id, trunk.id)
        assert len(vlans) == 0

    async def test_unassign_vlan_not_found(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)

        with pytest.raises(NotFoundError):
            await trunks.unassign_vlan(
                db_session, ixp.id, trunk.id, uuid.uuid4()
            )

    async def test_unassign_vlan_wrong_trunk_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        """Unassigning a TrunkVLAN with wrong trunk_id should fail (ownership check)"""
        member = await _create_member(db_session, ixp)
        trunk_a = await _create_trunk(db_session, ixp, member, name="Trunk-A")
        trunk_b = await _create_trunk(db_session, ixp, member, name="Trunk-B")
        vlan = await _create_vlan(db_session, ixp)
        tv = await _create_trunk_vlan(db_session, ixp, trunk_a, vlan)

        with pytest.raises(NotFoundError):
            await trunks.unassign_vlan(db_session, ixp.id, trunk_b.id, tv.id)

    async def test_unassign_vlan_with_ips_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)
        vlan = await _create_vlan(db_session, ixp)
        tv = await _create_trunk_vlan(db_session, ixp, trunk, vlan)
        pool = await _create_pool(db_session, ixp, vlan)
        await _create_ip_assignment(db_session, ixp, pool, tv, "198.51.100.1")

        with pytest.raises(ConflictError, match="IP"):
            await trunks.unassign_vlan(db_session, ixp.id, trunk.id, tv.id)

    async def test_unassign_vlan_with_bgp_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)
        vlan = await _create_vlan(db_session, ixp)
        tv = await _create_trunk_vlan(db_session, ixp, trunk, vlan)

        rs = RouteServer(id=uuid.uuid4(), ixp_id=ixp.id, name="rs-test")
        db_session.add(rs)
        await db_session.flush()

        bgp = BGPSession(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            route_server_id=rs.id,
            trunk_vlan_id=tv.id,
            peer_ip="192.0.2.10",
            peer_asn=64600,
            admin_state=BGPAdminState.up,
            oper_state=BGPOperState.unknown,
            af=4,
        )
        db_session.add(bgp)
        await db_session.flush()

        with pytest.raises(ConflictError, match="BGP"):
            await trunks.unassign_vlan(db_session, ixp.id, trunk.id, tv.id)

    async def test_list_vlans(self, db_session: AsyncSession, ixp: IXP):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)
        vlan1 = await _create_vlan(db_session, ixp, vid=200)
        vlan2 = await _create_vlan(db_session, ixp, vid=201)
        await _create_trunk_vlan(db_session, ixp, trunk, vlan1)
        await _create_trunk_vlan(db_session, ixp, trunk, vlan2)

        vlans = await trunks.list_vlans(db_session, ixp.id, trunk.id)

        assert len(vlans) == 2
        # Verify vlan relationship is loaded
        vlan_ids = {v.vlan_id for v in vlans}
        assert vlan1.id in vlan_ids
        assert vlan2.id in vlan_ids


# ---------------------------------------------------------------------------
# IP management
# ---------------------------------------------------------------------------


class TestTrunkIP:
    async def test_assign_ip_sequential(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)
        vlan = await _create_vlan(db_session, ixp)
        tv = await _create_trunk_vlan(db_session, ixp, trunk, vlan)
        pool = await _create_pool(
            db_session, ixp, vlan, network="203.0.113.0/24"
        )

        assignment = await trunks.assign_ip(
            db_session, ixp.id, tv.id, pool.id
        )

        assert assignment.address == "203.0.113.1"
        assert assignment.trunk_vlan_id == tv.id

    async def test_assign_ip_manual(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)
        vlan = await _create_vlan(db_session, ixp)
        tv = await _create_trunk_vlan(db_session, ixp, trunk, vlan)
        pool = await _create_pool(
            db_session, ixp, vlan, network="203.0.113.0/24"
        )

        assignment = await trunks.assign_ip(
            db_session, ixp.id, tv.id, pool.id, address="203.0.113.50"
        )

        assert assignment.address == "203.0.113.50"

    async def test_assign_ip_duplicate_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)
        vlan = await _create_vlan(db_session, ixp)
        tv = await _create_trunk_vlan(db_session, ixp, trunk, vlan)
        pool = await _create_pool(
            db_session, ixp, vlan, network="203.0.113.0/24"
        )

        await trunks.assign_ip(
            db_session, ixp.id, tv.id, pool.id, address="203.0.113.50"
        )

        with pytest.raises(ConflictError, match="already assigned"):
            await trunks.assign_ip(
                db_session, ixp.id, tv.id, pool.id, address="203.0.113.50"
            )

    async def test_release_ip(self, db_session: AsyncSession, ixp: IXP):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)
        vlan = await _create_vlan(db_session, ixp)
        tv = await _create_trunk_vlan(db_session, ixp, trunk, vlan)
        pool = await _create_pool(db_session, ixp, vlan)
        assignment = await _create_ip_assignment(
            db_session, ixp, pool, tv, "198.51.100.1"
        )

        await trunks.release_ip(db_session, ixp.id, assignment.id)

        ips = await trunks.list_ips(db_session, ixp.id, tv.id)
        assert len(ips) == 0

    async def test_release_ip_blocked_by_bgp(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)
        vlan = await _create_vlan(db_session, ixp)
        tv = await _create_trunk_vlan(db_session, ixp, trunk, vlan)
        pool = await _create_pool(db_session, ixp, vlan)
        assignment = await _create_ip_assignment(
            db_session, ixp, pool, tv, "198.51.100.1"
        )

        rs = RouteServer(id=uuid.uuid4(), ixp_id=ixp.id, name="rs-test")
        db_session.add(rs)
        await db_session.flush()

        bgp = BGPSession(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            route_server_id=rs.id,
            trunk_vlan_id=tv.id,
            peer_ip="198.51.100.1",
            peer_asn=64600,
            admin_state=BGPAdminState.up,
            oper_state=BGPOperState.unknown,
            af=4,
        )
        db_session.add(bgp)
        await db_session.flush()

        with pytest.raises(ConflictError, match="BGP session"):
            await trunks.release_ip(db_session, ixp.id, assignment.id)

    async def test_release_ip_not_found(
        self, db_session: AsyncSession, ixp: IXP
    ):
        with pytest.raises(NotFoundError):
            await trunks.release_ip(db_session, ixp.id, uuid.uuid4())

    async def test_list_ips(self, db_session: AsyncSession, ixp: IXP):
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)
        vlan = await _create_vlan(db_session, ixp)
        tv = await _create_trunk_vlan(db_session, ixp, trunk, vlan)
        pool = await _create_pool(db_session, ixp, vlan)
        await _create_ip_assignment(db_session, ixp, pool, tv, "198.51.100.1")
        await _create_ip_assignment(db_session, ixp, pool, tv, "198.51.100.2")

        ips = await trunks.list_ips(db_session, ixp.id, tv.id)

        assert len(ips) == 2


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


class TestTrunkConnection:
    async def test_add_connection(self, db_session: AsyncSession, ixp: IXP):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)

        data = ConnectionCreate(
            switch_id=switch.id,
            name="Ethernet1",
            type=ConnectionType.physical,
            speed=10000,
        )
        conn = await trunks.add_connection(
            db_session, ixp.id, trunk.id, data
        )

        assert conn.trunk_id == trunk.id
        assert conn.state == ConnectionState.draft
        assert conn.name == "Ethernet1"
        assert conn.type == ConnectionType.physical

    async def test_add_connection_to_decommissioned_trunk_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        trunk = await _create_trunk(
            db_session, ixp, member, state=TrunkState.decommissioned
        )

        data = ConnectionCreate(
            switch_id=switch.id,
            name="Ethernet1",
            type=ConnectionType.physical,
            speed=10000,
        )
        with pytest.raises(ValidationError, match="decommissioned"):
            await trunks.add_connection(
                db_session, ixp.id, trunk.id, data
            )

    async def test_add_connection_type_consistency(
        self, db_session: AsyncSession, ixp: IXP
    ):
        """All connections in a trunk must have the same type"""
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)

        # Add a physical connection
        await _create_connection(
            db_session, ixp, trunk, switch,
            name="Ethernet1", type=ConnectionType.physical,
        )

        # Try to add a virtual connection -> should fail
        data = ConnectionCreate(
            switch_id=switch.id,
            name="VirtualPort1",
            type=ConnectionType.virtual,
            speed=10000,
        )
        with pytest.raises(ValidationError, match="Type mismatch"):
            await trunks.add_connection(
                db_session, ixp.id, trunk.id, data
            )

    async def test_add_connection_same_type_ok(
        self, db_session: AsyncSession, ixp: IXP
    ):
        """Adding a connection with the same type should succeed"""
        member = await _create_member(db_session, ixp)
        switch = await _create_switch(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)

        await _create_connection(
            db_session, ixp, trunk, switch,
            name="Ethernet1", type=ConnectionType.physical,
        )

        data = ConnectionCreate(
            switch_id=switch.id,
            name="Ethernet2",
            type=ConnectionType.physical,
            speed=10000,
        )
        conn = await trunks.add_connection(
            db_session, ixp.id, trunk.id, data
        )

        assert conn.type == ConnectionType.physical

    async def test_add_connection_switch_from_other_ixp_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ):
        other_ixp = IXP(
            name="Other IXP", short_name="OIXP", asn=65999, country="CL", city="X"
        )
        db_session.add(other_ixp)
        await db_session.flush()

        foreign_switch = await _create_switch(db_session, other_ixp)
        member = await _create_member(db_session, ixp)
        trunk = await _create_trunk(db_session, ixp, member)

        data = ConnectionCreate(
            switch_id=foreign_switch.id,
            name="Ethernet1",
            type=ConnectionType.physical,
            speed=10000,
        )
        with pytest.raises(NotFoundError):
            await trunks.add_connection(
                db_session, ixp.id, trunk.id, data
            )
