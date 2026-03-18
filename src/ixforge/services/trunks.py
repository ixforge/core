"""Trunk service: CRUD, state machine, VLAN/IP management, connection management."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ixforge.enums import ConnectionState, MemberState, TrunkState, VLANType
from ixforge.exceptions import ConflictError, NotFoundError, ValidationError
from ixforge.models.bgp_session import BGPSession
from ixforge.models.connection import Connection
from ixforge.models.ip import IPAssignment
from ixforge.models.member import Member
from ixforge.models.trunk import Trunk, TrunkVLAN
from ixforge.models.vlan import VLAN
from ixforge.models.vlan_member import VLANMember
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.connection import ConnectionCreate
from ixforge.schemas.trunk import TrunkCreate, TrunkRead, TrunkUpdate
from ixforge.services import custom_fields
from ixforge.services.base import paginate
from ixforge.services.events import create_event

# Valid state transitions: source -> set of allowed targets
_TRUNK_TRANSITIONS: dict[str, set[str]] = {
    TrunkState.draft: {TrunkState.provisioning},
    TrunkState.provisioning: {TrunkState.active, TrunkState.decommissioned},
    TrunkState.active: {TrunkState.disabled},
    TrunkState.disabled: {TrunkState.active, TrunkState.decommissioned},
}


async def create(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    data: TrunkCreate,
    *,
    actor_id: uuid.UUID | None = None,
) -> Trunk:
    """Create a new trunk in draft state."""
    member = await session.get(Member, data.member_id)
    if member is None or member.ixp_id != ixp_id:
        raise NotFoundError("Member", str(data.member_id))
    if member.state == MemberState.terminated:
        raise ValidationError("Cannot create trunk for a terminated member")

    if data.extra_data is not None:
        await custom_fields.validate_extra_data(session, ixp_id, "trunk", data.extra_data)

    trunk = Trunk(
        ixp_id=ixp_id,
        member_id=data.member_id,
        name=data.name,
        state=TrunkState.draft,
        mac_address=data.mac_address,
        notes=data.notes,
        extra_data=data.extra_data,
    )
    session.add(trunk)
    await session.flush()

    await create_event(
        session,
        ixp_id=ixp_id,
        event_type="trunk.created",
        actor_id=actor_id,
        resource_type="trunk",
        resource_id=trunk.id,
        data={"member_id": str(data.member_id)},
    )
    return await get(session, ixp_id, trunk.id)


async def get(session: AsyncSession, ixp_id: uuid.UUID, trunk_id: uuid.UUID) -> Trunk:
    """Get a trunk by id or raise NotFoundError.

    Always loads member relationship so TrunkRead
    can populate member_name consistently.
    """
    stmt = (
        select(Trunk)
        .where(Trunk.id == trunk_id)
        .options(joinedload(Trunk.member))
    )
    result = await session.execute(stmt)
    trunk = result.unique().scalar_one_or_none()
    if trunk is None or trunk.ixp_id != ixp_id:
        raise NotFoundError("Trunk", str(trunk_id))
    return trunk


async def list_trunks(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    params: CursorParams,
    *,
    member_id: uuid.UUID | None = None,
) -> CursorPage[TrunkRead]:
    """List trunks with optional member filter."""
    stmt = (
        select(Trunk)
        .where(Trunk.ixp_id == ixp_id)
        .options(joinedload(Trunk.member))
    )
    if member_id is not None:
        stmt = stmt.where(Trunk.member_id == member_id)
    return await paginate(
        session,
        stmt,
        params,
        sort_column=Trunk.created_at,
        id_column=Trunk.id,
        schema=TrunkRead,
    )


async def update(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    trunk_id: uuid.UUID,
    data: TrunkUpdate,
) -> Trunk:
    """Update mutable fields on a trunk (state changes use transition)."""
    trunk = await get(session, ixp_id, trunk_id)
    update_fields = data.model_dump(exclude_unset=True)

    if trunk.state == TrunkState.decommissioned:
        raise ValidationError("Cannot update a decommissioned trunk")

    if "extra_data" in update_fields and update_fields["extra_data"] is not None:
        await custom_fields.validate_extra_data(
            session, ixp_id, "trunk", update_fields["extra_data"]
        )

    for field, value in update_fields.items():
        setattr(trunk, field, value)
    await session.flush()
    return await get(session, ixp_id, trunk_id)


async def transition(
    session: AsyncSession,
    trunk_id: uuid.UUID,
    target_state: TrunkState,
    *,
    ixp_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
) -> Trunk:
    """Transition a trunk to a new state with validation."""
    trunk = await get(session, ixp_id, trunk_id)
    current = trunk.state

    allowed = _TRUNK_TRANSITIONS.get(current, set())
    if target_state not in allowed:
        raise ValidationError(
            f"Cannot transition trunk from '{current}' to '{target_state}'",
            details={"current_state": current, "target_state": target_state},
        )

    # Activation preconditions
    if target_state == TrunkState.active:
        # Requires at least 1 connection
        has_connection = await session.scalar(
            select(Connection.id)
            .where(Connection.trunk_id == trunk_id)
            .limit(1)
        )
        if has_connection is None:
            raise ValidationError(
                "Cannot activate trunk: at least one connection is required"
            )

        # Requires at least 1 TrunkVLAN
        trunk_vlans = (
            await session.execute(
                select(TrunkVLAN).where(TrunkVLAN.trunk_id == trunk_id)
            )
        ).scalars().all()
        if not trunk_vlans:
            raise ValidationError(
                "Cannot activate trunk: at least one VLAN must be assigned"
            )

        # For each production TrunkVLAN, at least 1 IP
        for tv in trunk_vlans:
            vlan = await session.get(VLAN, tv.vlan_id)
            if vlan is not None and vlan.type == VLANType.production:
                has_ip = await session.scalar(
                    select(IPAssignment.id)
                    .where(IPAssignment.trunk_vlan_id == tv.id)
                    .limit(1)
                )
                if has_ip is None:
                    raise ValidationError(
                        "Cannot activate trunk: each production VLAN must have at least one IP"
                    )

    # Decommission preconditions
    if target_state == TrunkState.decommissioned:
        has_bgp = await session.scalar(
            select(BGPSession.id)
            .where(
                BGPSession.trunk_vlan_id.in_(
                    select(TrunkVLAN.id).where(TrunkVLAN.trunk_id == trunk_id)
                )
            )
            .limit(1)
        )
        if has_bgp is not None:
            raise ValidationError(
                "Cannot decommission trunk: delete all BGP sessions first"
            )

        has_ip = await session.scalar(
            select(IPAssignment.id)
            .where(
                IPAssignment.trunk_vlan_id.in_(
                    select(TrunkVLAN.id).where(TrunkVLAN.trunk_id == trunk_id)
                )
            )
            .limit(1)
        )
        if has_ip is not None:
            raise ValidationError(
                "Cannot decommission trunk: release all IPs first"
            )

        has_vlan = await session.scalar(
            select(TrunkVLAN.id)
            .where(TrunkVLAN.trunk_id == trunk_id)
            .limit(1)
        )
        if has_vlan is not None:
            raise ValidationError(
                "Cannot decommission trunk: unassign all VLANs first"
            )

        has_active_conn = await session.scalar(
            select(Connection.id)
            .where(
                Connection.trunk_id == trunk_id,
                Connection.state != ConnectionState.decommissioned,
            )
            .limit(1)
        )
        if has_active_conn is not None:
            raise ValidationError(
                "Cannot decommission trunk: all connections must be decommissioned first"
            )

    old_state = trunk.state
    trunk.state = target_state
    await session.flush()

    await create_event(
        session,
        ixp_id=ixp_id,
        event_type="trunk.state_changed",
        actor_id=actor_id,
        resource_type="trunk",
        resource_id=trunk.id,
        data={"old_state": old_state, "new_state": target_state},
    )
    return await get(session, ixp_id, trunk_id)


async def delete(session: AsyncSession, ixp_id: uuid.UUID, trunk_id: uuid.UUID) -> None:
    """Delete a decommissioned trunk."""
    trunk = await get(session, ixp_id, trunk_id)
    if trunk.state != TrunkState.decommissioned:
        raise ValidationError("Trunk must be decommissioned before deletion")
    await session.delete(trunk)
    await session.flush()


# ---------------------------------------------------------------------------
# VLAN management
# ---------------------------------------------------------------------------


async def assign_vlan(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    trunk_id: uuid.UUID,
    vlan_id: uuid.UUID,
) -> TrunkVLAN:
    """Assign a VLAN to a trunk."""
    trunk = await get(session, ixp_id, trunk_id)
    if trunk.state in (TrunkState.disabled, TrunkState.decommissioned):
        raise ValidationError(
            f"Cannot assign resources to a {trunk.state} trunk"
        )

    # Validate that the VLAN belongs to the same IXP
    vlan = await session.get(VLAN, vlan_id)
    if vlan is None or vlan.ixp_id != ixp_id:
        raise NotFoundError("VLAN", str(vlan_id))

    # Check for duplicate assignment
    existing = await session.scalar(
        select(TrunkVLAN.id)
        .where(
            TrunkVLAN.trunk_id == trunk_id,
            TrunkVLAN.vlan_id == vlan_id,
        )
        .limit(1)
    )
    if existing is not None:
        raise ConflictError(
            f"VLAN {vlan_id} is already assigned to trunk {trunk_id}"
        )

    # Validate private VLAN access
    if vlan.type == VLANType.private:
        is_authorized = await session.scalar(
            select(VLANMember.id).where(
                VLANMember.vlan_id == vlan_id,
                VLANMember.member_id == trunk.member_id,
            ).limit(1)
        )
        if is_authorized is None:
            raise ValidationError("Member is not authorized for this private VLAN")

    tv = TrunkVLAN(
        ixp_id=ixp_id,
        trunk_id=trunk_id,
        vlan_id=vlan_id,
    )
    session.add(tv)
    await session.flush()

    # Return with vlan loaded for enrichment
    stmt = (
        select(TrunkVLAN)
        .where(TrunkVLAN.id == tv.id)
        .options(joinedload(TrunkVLAN.vlan))
    )
    result = await session.execute(stmt)
    return result.unique().scalar_one()


async def unassign_vlan(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    trunk_id: uuid.UUID,
    trunk_vlan_id: uuid.UUID,
) -> None:
    """Remove a VLAN assignment from a trunk.

    Validates ownership (TrunkVLAN.trunk_id == trunk_id) and that
    no IPs or BGP sessions reference this TrunkVLAN.
    """
    stmt = select(TrunkVLAN).where(
        TrunkVLAN.id == trunk_vlan_id,
        TrunkVLAN.trunk_id == trunk_id,
        TrunkVLAN.ixp_id == ixp_id,
    )
    result = await session.execute(stmt)
    tv = result.scalar_one_or_none()
    if tv is None:
        raise NotFoundError("TrunkVLAN", str(trunk_vlan_id))

    # Block if IPs are assigned
    has_ip = await session.scalar(
        select(IPAssignment.id)
        .where(IPAssignment.trunk_vlan_id == trunk_vlan_id)
        .limit(1)
    )
    if has_ip is not None:
        raise ConflictError(
            "Cannot unassign VLAN: release all IP assignments first"
        )

    # Block if BGP sessions exist
    has_bgp = await session.scalar(
        select(BGPSession.id)
        .where(BGPSession.trunk_vlan_id == trunk_vlan_id)
        .limit(1)
    )
    if has_bgp is not None:
        raise ConflictError(
            "Cannot unassign VLAN: delete all BGP sessions first"
        )

    await session.delete(tv)
    await session.flush()


async def list_vlans(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    trunk_id: uuid.UUID,
) -> list[TrunkVLAN]:
    """List TrunkVLANs with joinedloaded vlan for name/vid enrichment."""
    await get(session, ixp_id, trunk_id)
    stmt = (
        select(TrunkVLAN)
        .where(
            TrunkVLAN.trunk_id == trunk_id,
            TrunkVLAN.ixp_id == ixp_id,
        )
        .options(joinedload(TrunkVLAN.vlan))
    )
    result = await session.execute(stmt)
    return list(result.unique().scalars().all())


# ---------------------------------------------------------------------------
# IP management
# ---------------------------------------------------------------------------


async def assign_ip(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    trunk_vlan_id: uuid.UUID,
    pool_id: uuid.UUID,
    *,
    address: str | None = None,
) -> IPAssignment:
    """Assign an IP to a TrunkVLAN.

    Delegates to the IPAM service for proper locking and global uniqueness checks.
    If address is None, sequential allocation is used.
    If provided, manual allocation.
    """
    from ixforge.services import ipam

    if address is not None:
        return await ipam.allocate_manual(session, ixp_id, pool_id, trunk_vlan_id, address)
    return await ipam.allocate_sequential(session, ixp_id, pool_id, trunk_vlan_id)


async def release_ip(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    assignment_id: uuid.UUID,
) -> None:
    """Release an IP assignment.

    Blocks release if a BGP session uses this IP.
    """
    assignment = await session.get(IPAssignment, assignment_id)
    if assignment is None or assignment.ixp_id != ixp_id:
        raise NotFoundError("IPAssignment", str(assignment_id))

    has_bgp = await session.scalar(
        select(BGPSession.id).where(
            BGPSession.trunk_vlan_id == assignment.trunk_vlan_id,
            BGPSession.peer_ip == assignment.address,
        ).limit(1)
    )
    if has_bgp is not None:
        raise ConflictError(
            f"Cannot release IP {assignment.address}: has an active BGP session. "
            "Delete the BGP session first."
        )

    await session.delete(assignment)
    await session.flush()


async def list_ips(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    trunk_vlan_id: uuid.UUID,
) -> list[IPAssignment]:
    """List IP assignments for a TrunkVLAN."""
    tv = await session.get(TrunkVLAN, trunk_vlan_id)
    if tv is None or tv.ixp_id != ixp_id:
        raise NotFoundError("TrunkVLAN", str(trunk_vlan_id))
    stmt = (
        select(IPAssignment)
        .where(
            IPAssignment.trunk_vlan_id == trunk_vlan_id,
            IPAssignment.ixp_id == ixp_id,
        )
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


async def add_connection(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    trunk_id: uuid.UUID,
    data: ConnectionCreate,
) -> Connection:
    """Add a connection to a trunk.

    Validates type consistency: all connections in a trunk must have the same type.
    Creates in draft state.
    """
    trunk = await get(session, ixp_id, trunk_id)
    if trunk.state in (TrunkState.disabled, TrunkState.decommissioned):
        raise ValidationError("Cannot add connections to a disabled or decommissioned trunk")

    # Validate switch exists and belongs to same IXP
    from ixforge.models.switch import Switch

    switch = await session.get(Switch, data.switch_id)
    if switch is None or switch.ixp_id != ixp_id:
        raise NotFoundError("Switch", str(data.switch_id))

    # Check type consistency
    existing_type_result = await session.execute(
        select(Connection.type)
        .where(Connection.trunk_id == trunk_id)
        .limit(1)
    )
    existing_type = existing_type_result.scalar_one_or_none()
    if existing_type is not None and existing_type != data.type:
        raise ValidationError(
            f"Type mismatch: trunk already has '{existing_type}' connections, "
            f"cannot add '{data.type}'"
        )

    connection = Connection(
        ixp_id=ixp_id,
        trunk_id=trunk_id,
        switch_id=data.switch_id,
        name=data.name,
        type=data.type,
        state=ConnectionState.draft,
        speed=data.speed,
        notes=data.notes,
        extra_data=data.extra_data,
    )
    session.add(connection)
    await session.flush()
    return connection
