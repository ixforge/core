"""Tests for ConnectionService: CRUD and state machine."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import ConnectionState, ConnectionType, MemberState
from ixforge.exceptions import NotFoundError, ValidationError
from ixforge.models.connection import Connection
from ixforge.models.ixp import IXP
from ixforge.models.location import Location
from ixforge.models.member import Member
from ixforge.models.switch import Switch
from ixforge.models.trunk import Trunk
from ixforge.services import connections as conn_svc
from tests.factories import ConnectionFactory, MemberFactory, SwitchFactory, TrunkFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup(db: AsyncSession, ixp: IXP) -> tuple[Member, Trunk, Switch]:
    """Create member, trunk, location and switch for connection tests."""
    member = MemberFactory.build(ixp_id=ixp.id, state=MemberState.active)
    db.add(member)

    trunk = TrunkFactory.build(ixp_id=ixp.id, member_id=member.id)
    db.add(trunk)

    location = Location(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name=f"DC-{uuid.uuid4().hex[:6]}",
        city="Test City",
        country="US",
    )
    db.add(location)
    await db.flush()

    switch = SwitchFactory.build(ixp_id=ixp.id, location_id=location.id)
    db.add(switch)
    await db.flush()

    return member, trunk, switch


async def _make_connection(
    db: AsyncSession,
    ixp: IXP,
    trunk: Trunk,
    switch: Switch,
    **overrides,
) -> Connection:
    conn = ConnectionFactory.build(
        ixp_id=ixp.id,
        trunk_id=trunk.id,
        switch_id=switch.id,
        **overrides,
    )
    db.add(conn)
    await db.flush()
    return conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetConnection:
    async def test_get_connection(self, db_session: AsyncSession, ixp: IXP) -> None:
        member, trunk, switch = await _setup(db_session, ixp)
        conn = await _make_connection(db_session, ixp, trunk, switch)

        result = await conn_svc.get(db_session, ixp.id, conn.id)

        assert result.id == conn.id
        assert result.trunk_id == trunk.id

    async def test_get_connection_not_found(self, db_session: AsyncSession, ixp: IXP) -> None:
        with pytest.raises(NotFoundError):
            await conn_svc.get(db_session, ixp.id, uuid.uuid4())

    async def test_get_connection_wrong_ixp(self, db_session: AsyncSession, ixp: IXP) -> None:
        member, trunk, switch = await _setup(db_session, ixp)
        conn = await _make_connection(db_session, ixp, trunk, switch)

        with pytest.raises(NotFoundError):
            await conn_svc.get(db_session, uuid.uuid4(), conn.id)


class TestUpdateConnection:
    async def test_update_connection(self, db_session: AsyncSession, ixp: IXP) -> None:
        from ixforge.schemas.connection import ConnectionUpdate

        member, trunk, switch = await _setup(db_session, ixp)
        conn = await _make_connection(db_session, ixp, trunk, switch, speed=1000)

        result = await conn_svc.update(
            db_session, ixp.id, conn.id, ConnectionUpdate(speed=10000, notes="updated")
        )

        assert result.speed == 10000
        assert result.notes == "updated"

    async def test_update_connection_type_consistency(
        self, db_session: AsyncSession, ixp: IXP
    ) -> None:
        """Changing type is rejected if other connections in trunk have a different type."""
        from ixforge.schemas.connection import ConnectionUpdate

        member, trunk, switch = await _setup(db_session, ixp)

        # First connection: physical
        await _make_connection(
            db_session, ixp, trunk, switch, type=ConnectionType.physical, name="Ethernet1"
        )
        # Second connection: physical — we try to change it to virtual
        conn2 = await _make_connection(
            db_session, ixp, trunk, switch, type=ConnectionType.physical, name="Ethernet2"
        )

        with pytest.raises(ValidationError):
            await conn_svc.update(
                db_session,
                ixp.id,
                conn2.id,
                ConnectionUpdate(type=ConnectionType.virtual),
            )

    async def test_update_connection_type_same_type_allowed(
        self, db_session: AsyncSession, ixp: IXP
    ) -> None:
        """Changing type is allowed when all other connections already match."""
        from ixforge.schemas.connection import ConnectionUpdate

        member, trunk, switch = await _setup(db_session, ixp)

        await _make_connection(
            db_session, ixp, trunk, switch, type=ConnectionType.physical, name="Ethernet1"
        )
        conn2 = await _make_connection(
            db_session, ixp, trunk, switch, type=ConnectionType.physical, name="Ethernet2"
        )

        # Changing to the same type as peers: should be fine
        result = await conn_svc.update(
            db_session,
            ixp.id,
            conn2.id,
            ConnectionUpdate(type=ConnectionType.physical),
        )
        assert result.type == ConnectionType.physical

    async def test_update_switch_wrong_ixp_rejected(
        self, db_session: AsyncSession, ixp: IXP
    ) -> None:
        """Switching to a switch that belongs to another IXP is rejected."""
        from ixforge.schemas.connection import ConnectionUpdate

        member, trunk, switch = await _setup(db_session, ixp)
        conn = await _make_connection(db_session, ixp, trunk, switch)

        with pytest.raises(NotFoundError):
            await conn_svc.update(
                db_session, ixp.id, conn.id, ConnectionUpdate(switch_id=uuid.uuid4())
            )


class TestConnectionStateMachine:
    async def test_transition_draft_to_provisioning(
        self, db_session: AsyncSession, ixp: IXP
    ) -> None:
        member, trunk, switch = await _setup(db_session, ixp)
        conn = await _make_connection(db_session, ixp, trunk, switch, state=ConnectionState.draft)

        result = await conn_svc.transition(
            db_session, conn.id, ConnectionState.provisioning, ixp_id=ixp.id
        )

        assert result.state == ConnectionState.provisioning

    async def test_transition_provisioning_to_active(
        self, db_session: AsyncSession, ixp: IXP
    ) -> None:
        """provisioning -> active should work without VLAN/IP (now on trunk)."""
        member, trunk, switch = await _setup(db_session, ixp)
        conn = await _make_connection(
            db_session, ixp, trunk, switch, state=ConnectionState.provisioning
        )

        result = await conn_svc.transition(
            db_session, conn.id, ConnectionState.active, ixp_id=ixp.id
        )

        assert result.state == ConnectionState.active

    async def test_transition_provisioning_to_decommissioned(
        self, db_session: AsyncSession, ixp: IXP
    ) -> None:
        member, trunk, switch = await _setup(db_session, ixp)
        conn = await _make_connection(
            db_session, ixp, trunk, switch, state=ConnectionState.provisioning
        )

        result = await conn_svc.transition(
            db_session, conn.id, ConnectionState.decommissioned, ixp_id=ixp.id
        )

        assert result.state == ConnectionState.decommissioned

    async def test_transition_active_to_disabled(
        self, db_session: AsyncSession, ixp: IXP
    ) -> None:
        member, trunk, switch = await _setup(db_session, ixp)
        conn = await _make_connection(
            db_session, ixp, trunk, switch, state=ConnectionState.active
        )

        result = await conn_svc.transition(
            db_session, conn.id, ConnectionState.disabled, ixp_id=ixp.id
        )

        assert result.state == ConnectionState.disabled

    async def test_transition_disabled_to_active(
        self, db_session: AsyncSession, ixp: IXP
    ) -> None:
        member, trunk, switch = await _setup(db_session, ixp)
        conn = await _make_connection(
            db_session, ixp, trunk, switch, state=ConnectionState.disabled
        )

        result = await conn_svc.transition(
            db_session, conn.id, ConnectionState.active, ixp_id=ixp.id
        )

        assert result.state == ConnectionState.active

    async def test_transition_disabled_to_decommissioned(
        self, db_session: AsyncSession, ixp: IXP
    ) -> None:
        member, trunk, switch = await _setup(db_session, ixp)
        conn = await _make_connection(
            db_session, ixp, trunk, switch, state=ConnectionState.disabled
        )

        result = await conn_svc.transition(
            db_session, conn.id, ConnectionState.decommissioned, ixp_id=ixp.id
        )

        assert result.state == ConnectionState.decommissioned

    async def test_transition_invalid(self, db_session: AsyncSession, ixp: IXP) -> None:
        """draft -> active is an invalid transition."""
        member, trunk, switch = await _setup(db_session, ixp)
        conn = await _make_connection(db_session, ixp, trunk, switch, state=ConnectionState.draft)

        with pytest.raises(ValidationError):
            await conn_svc.transition(
                db_session, conn.id, ConnectionState.active, ixp_id=ixp.id
            )

    async def test_transition_decommissioned_to_anything_invalid(
        self, db_session: AsyncSession, ixp: IXP
    ) -> None:
        member, trunk, switch = await _setup(db_session, ixp)
        conn = await _make_connection(
            db_session, ixp, trunk, switch, state=ConnectionState.decommissioned
        )

        with pytest.raises(ValidationError):
            await conn_svc.transition(
                db_session, conn.id, ConnectionState.draft, ixp_id=ixp.id
            )


class TestDeleteConnection:
    async def test_delete_connection(self, db_session: AsyncSession, ixp: IXP) -> None:
        member, trunk, switch = await _setup(db_session, ixp)
        conn = await _make_connection(
            db_session, ixp, trunk, switch, state=ConnectionState.decommissioned
        )

        await conn_svc.delete(db_session, ixp.id, conn.id)

        with pytest.raises(NotFoundError):
            await conn_svc.get(db_session, ixp.id, conn.id)

    async def test_delete_connection_not_decommissioned(
        self, db_session: AsyncSession, ixp: IXP
    ) -> None:
        member, trunk, switch = await _setup(db_session, ixp)
        conn = await _make_connection(
            db_session, ixp, trunk, switch, state=ConnectionState.active
        )

        with pytest.raises(ValidationError):
            await conn_svc.delete(db_session, ixp.id, conn.id)


class TestListConnections:
    async def test_list_connections_by_switch(self, db_session: AsyncSession, ixp: IXP) -> None:
        from ixforge.schemas.common import CursorParams

        member, trunk, switch = await _setup(db_session, ixp)

        # Create a second switch to verify filtering
        location2 = Location(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name=f"DC-other-{uuid.uuid4().hex[:6]}",
            city="Other City",
            country="US",
        )
        db_session.add(location2)
        await db_session.flush()
        switch2 = SwitchFactory.build(ixp_id=ixp.id, location_id=location2.id)
        db_session.add(switch2)
        await db_session.flush()

        conn1 = await _make_connection(db_session, ixp, trunk, switch, name="Ethernet1")
        conn2 = await _make_connection(db_session, ixp, trunk, switch, name="Ethernet2")
        await _make_connection(db_session, ixp, trunk, switch2, name="Ethernet3")

        page = await conn_svc.list_connections(
            db_session, ixp.id, CursorParams(), switch_id=switch.id
        )

        ids = {item.id for item in page.items}
        assert conn1.id in ids
        assert conn2.id in ids
        assert len(page.items) == 2

    async def test_list_connections_no_filter(self, db_session: AsyncSession, ixp: IXP) -> None:
        from ixforge.schemas.common import CursorParams

        member, trunk, switch = await _setup(db_session, ixp)
        await _make_connection(db_session, ixp, trunk, switch, name="Ethernet1")
        await _make_connection(db_session, ixp, trunk, switch, name="Ethernet2")

        page = await conn_svc.list_connections(db_session, ixp.id, CursorParams())

        assert len(page.items) >= 2
