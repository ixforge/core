"""Connection service: CRUD, state machine, VLAN/IP management, event emission."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ixforge.enums import MemberState
from ixforge.exceptions import ConflictError, NotFoundError, ValidationError
from ixforge.models.bgp_session import BGPSession
from ixforge.models.connection import Connection, ConnectionVLAN
from ixforge.models.ip import IPAssignment
from ixforge.models.member import Member
from ixforge.models.vlan import VLAN
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.connection import (
    ConnectionCreate,
    ConnectionRead,
    ConnectionState,
    ConnectionVLANCreate,
)
from ixforge.schemas.connection import ConnectionUpdate as ConnectionUpdateSchema
from ixforge.services import custom_fields
from ixforge.services.base import paginate
from ixforge.services.events import create_event

# Valid state transitions: source -> set of allowed targets.
_CONNECTION_TRANSITIONS: dict[str, set[str]] = {
    ConnectionState.draft: {ConnectionState.provisioning},
    ConnectionState.provisioning: {ConnectionState.active, ConnectionState.decommissioned},
    ConnectionState.active: {ConnectionState.disabled},
    ConnectionState.disabled: {ConnectionState.active, ConnectionState.decommissioned},
}


async def create(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    data: ConnectionCreate,
    *,
    actor_id: uuid.UUID | None = None,
) -> Connection:
    """Create a new connection in draft state."""
    member = await session.get(Member, data.member_id)
    if member is None or member.ixp_id != ixp_id:
        raise NotFoundError("Member", str(data.member_id))
    if member.state == MemberState.terminated:
        raise ValidationError("Cannot create connection for a terminated member")

    if data.extra_data is not None:
        await custom_fields.validate_extra_data(session, ixp_id, "connection", data.extra_data)

    connection = Connection(
        ixp_id=ixp_id,
        member_id=data.member_id,
        port_id=data.port_id,
        type=data.type,
        state=ConnectionState.draft,
        mac_address=data.mac_address,
        speed=data.speed,
        extra_data=data.extra_data,
    )
    session.add(connection)
    await session.flush()

    await create_event(
        session,
        ixp_id=ixp_id,
        event_type="connection.created",
        actor_id=actor_id,
        resource_type="connection",
        resource_id=connection.id,
        data={"member_id": str(data.member_id), "type": data.type},
    )
    return await get(session, connection.id)


async def get(session: AsyncSession, connection_id: uuid.UUID) -> Connection:
    """Get a connection by id or raise NotFoundError.

    Always loads member and port relationships so ConnectionRead
    can populate member_name/port_name consistently.
    """
    stmt = (
        select(Connection)
        .where(Connection.id == connection_id)
        .options(joinedload(Connection.member), joinedload(Connection.port))
    )
    result = await session.execute(stmt)
    connection = result.unique().scalar_one_or_none()
    if connection is None:
        raise NotFoundError("Connection", str(connection_id))
    return connection


async def list_connections(
    session: AsyncSession,
    member_id: uuid.UUID,
    params: CursorParams,
) -> CursorPage[ConnectionRead]:
    """List connections for a member with cursor-based pagination."""
    stmt = (
        select(Connection)
        .where(Connection.member_id == member_id)
        .options(joinedload(Connection.member), joinedload(Connection.port))
    )
    return await paginate(
        session,
        stmt,
        params,
        sort_column=Connection.created_at,
        id_column=Connection.id,
        schema=ConnectionRead,
    )


async def update(
    session: AsyncSession,
    connection_id: uuid.UUID,
    data: ConnectionUpdateSchema,
) -> Connection:
    """Update mutable fields on a connection (state changes use transition)."""
    connection = await get(session, connection_id)
    update_fields = data.model_dump(exclude_unset=True)

    # Defensive: state changes must go through transition()
    if "state" in update_fields:
        raise ValidationError("Cannot modify state directly, use the transition endpoint")

    if "extra_data" in update_fields and update_fields["extra_data"] is not None:
        from ixforge.models.member import Member

        member = await session.get(Member, connection.member_id)
        if member is not None:
            await custom_fields.validate_extra_data(
                session, member.ixp_id, "connection", update_fields["extra_data"]
            )

    for field, value in update_fields.items():
        setattr(connection, field, value)
    await session.flush()
    return await get(session, connection_id)


async def _has_complete_setup(session: AsyncSession, connection_id: uuid.UUID) -> bool:
    """Check whether the connection has a port, at least one VLAN, and at least one IP."""
    connection = await get(session, connection_id)
    if connection.port_id is None:
        return False

    has_vlan = await session.scalar(
        select(ConnectionVLAN.id).where(ConnectionVLAN.connection_id == connection_id).limit(1)
    )
    if has_vlan is None:
        return False

    has_ip = await session.scalar(
        select(IPAssignment.id).where(IPAssignment.connection_id == connection_id).limit(1)
    )
    return has_ip is not None


async def transition(
    session: AsyncSession,
    connection_id: uuid.UUID,
    target_state: ConnectionState,
    *,
    ixp_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
) -> Connection:
    """Transition a connection to a new state with validation."""
    connection = await get(session, connection_id)
    current = connection.state

    allowed = _CONNECTION_TRANSITIONS.get(current, set())
    if target_state not in allowed:
        raise ValidationError(
            f"Cannot transition connection from '{current}' to '{target_state}'",
            details={"current_state": current, "target_state": target_state},
        )

    # Activating a connection requires port + VLAN + IP
    if (
        target_state == ConnectionState.active
        and not await _has_complete_setup(session, connection_id)
    ):
        raise ValidationError("Cannot activate connection: port, VLAN, and IP must be assigned")

    if target_state == ConnectionState.decommissioned:
        has_vlan = await session.scalar(
            select(ConnectionVLAN.id)
            .where(ConnectionVLAN.connection_id == connection_id)
            .limit(1)
        )
        has_ip = await session.scalar(
            select(IPAssignment.id)
            .where(IPAssignment.connection_id == connection_id)
            .limit(1)
        )
        if has_vlan is not None or has_ip is not None:
            raise ValidationError(
                "Cannot decommission connection: release all VLANs and IPs first"
            )

        has_bgp = await session.scalar(
            select(BGPSession.id)
            .where(BGPSession.connection_id == connection_id)
            .limit(1)
        )
        if has_bgp is not None:
            raise ValidationError(
                "Cannot decommission connection: delete all BGP sessions first"
            )

    old_state = connection.state
    connection.state = target_state
    await session.flush()

    await create_event(
        session,
        ixp_id=ixp_id,
        event_type="connection.state_changed",
        actor_id=actor_id,
        resource_type="connection",
        resource_id=connection.id,
        data={"old_state": old_state, "new_state": target_state},
    )

    if target_state == ConnectionState.active or old_state == ConnectionState.active:
        try:
            from ixforge.tasks.config import regenerate_configs_for_connection

            await regenerate_configs_for_connection.defer_async(
                connection_id=str(connection_id),
                triggered_by="connection.state_changed",
            )
        except Exception:
            import structlog

            structlog.get_logger().warning(
                "config_regeneration.defer_failed",
                connection_id=str(connection_id),
            )

    return await get(session, connection_id)


async def assign_vlan(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    connection_id: uuid.UUID,
    data: ConnectionVLANCreate,
) -> ConnectionVLAN:
    """Assign a VLAN to a connection."""
    connection = await get(session, connection_id)
    if connection.state in (ConnectionState.disabled, ConnectionState.decommissioned):
        raise ValidationError(
            f"Cannot assign resources to a {connection.state} connection"
        )

    # Validate that the VLAN belongs to the same IXP
    vlan = await session.get(VLAN, data.vlan_id)
    if vlan is None or vlan.ixp_id != ixp_id:
        raise NotFoundError("VLAN", str(data.vlan_id))

    # Check for duplicate assignment.
    existing = await session.scalar(
        select(ConnectionVLAN.id)
        .where(
            ConnectionVLAN.connection_id == connection_id,
            ConnectionVLAN.vlan_id == data.vlan_id,
        )
        .limit(1)
    )
    if existing is not None:
        raise ConflictError(
            f"VLAN {data.vlan_id} is already assigned to connection {connection_id}"
        )

    cv = ConnectionVLAN(
        ixp_id=ixp_id,
        connection_id=connection_id,
        vlan_id=data.vlan_id,
        tagged=data.tagged,
    )
    session.add(cv)
    await session.flush()
    return cv


async def unassign_vlan(
    session: AsyncSession,
    connection_id: uuid.UUID,
    vlan_id: uuid.UUID,
) -> None:
    """Remove a VLAN assignment from a connection."""
    stmt = select(ConnectionVLAN).where(
        ConnectionVLAN.connection_id == connection_id,
        ConnectionVLAN.vlan_id == vlan_id,
    )
    result = await session.execute(stmt)
    cv = result.scalar_one_or_none()
    if cv is None:
        raise NotFoundError("ConnectionVLAN")
    await session.delete(cv)
    await session.flush()


async def assign_ip(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    connection_id: uuid.UUID,
    pool_id: uuid.UUID,
    *,
    address: str | None = None,
) -> IPAssignment:
    """Assign an IP to a connection, delegating to IPAM service.

    If address is provided, manual allocation is used; otherwise sequential.
    """
    from ixforge.services import ipam

    connection = await get(session, connection_id)
    if connection.state in (ConnectionState.disabled, ConnectionState.decommissioned):
        raise ValidationError(
            f"Cannot assign resources to a {connection.state} connection"
        )

    if address is not None:
        return await ipam.allocate_manual(session, ixp_id, pool_id, connection_id, address)
    return await ipam.allocate_sequential(session, ixp_id, pool_id, connection_id)


async def delete(session: AsyncSession, connection_id: uuid.UUID) -> None:
    """Delete a decommissioned connection."""
    connection = await get(session, connection_id)
    if connection.state != ConnectionState.decommissioned:
        raise ValidationError("Connection must be decommissioned before deletion")
    await session.delete(connection)
    await session.flush()


async def release_ip(
    session: AsyncSession, connection_id: uuid.UUID, assignment_id: uuid.UUID
) -> None:
    """Release an IP assignment from a connection, delegating to IPAM service.

    Validates that the assignment belongs to the given connection to prevent IDOR.
    """
    from ixforge.services import ipam

    assignment = await session.get(IPAssignment, assignment_id)
    if assignment is None or assignment.connection_id != connection_id:
        raise NotFoundError("IPAssignment")

    await ipam.release(session, assignment_id, assignment.ixp_id)
