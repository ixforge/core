"""Connection service: CRUD, state machine, event emission."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ixforge.exceptions import NotFoundError, ValidationError
from ixforge.models.connection import Connection
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.connection import (
    ConnectionRead,
    ConnectionState,
)
from ixforge.schemas.connection import ConnectionUpdate as ConnectionUpdateSchema
from ixforge.services import custom_fields
from ixforge.services.base import paginate
from ixforge.services.events import create_event

# Valid state transitions: source -> set of allowed targets
_CONNECTION_TRANSITIONS: dict[str, set[str]] = {
    ConnectionState.draft: {ConnectionState.provisioning},
    ConnectionState.provisioning: {ConnectionState.active, ConnectionState.decommissioned},
    ConnectionState.active: {ConnectionState.disabled},
    ConnectionState.disabled: {ConnectionState.active, ConnectionState.decommissioned},
}


async def get(session: AsyncSession, ixp_id: uuid.UUID, connection_id: uuid.UUID) -> Connection:
    """Get a connection by id or raise NotFoundError.

    Always loads trunk relationship for consistent access.
    """
    stmt = (
        select(Connection)
        .where(Connection.id == connection_id)
        .options(joinedload(Connection.trunk))
    )
    result = await session.execute(stmt)
    connection = result.unique().scalar_one_or_none()
    if connection is None or connection.ixp_id != ixp_id:
        raise NotFoundError("Connection", str(connection_id))
    return connection


async def list_connections(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    params: CursorParams,
    *,
    switch_id: uuid.UUID | None = None,
    member_id: uuid.UUID | None = None,
) -> CursorPage[ConnectionRead]:
    """List connections with optional switch and member filters."""
    from ixforge.models.trunk import Trunk

    stmt = (
        select(Connection)
        .where(Connection.ixp_id == ixp_id)
        .options(joinedload(Connection.trunk))
    )
    if switch_id is not None:
        stmt = stmt.where(Connection.switch_id == switch_id)
    if member_id is not None:
        stmt = stmt.join(Trunk, Connection.trunk_id == Trunk.id).where(Trunk.member_id == member_id)
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
    ixp_id: uuid.UUID,
    connection_id: uuid.UUID,
    data: ConnectionUpdateSchema,
) -> Connection:
    """Update mutable fields on a connection (state changes use transition)."""
    connection = await get(session, ixp_id, connection_id)
    update_fields = data.model_dump(exclude_unset=True)

    # Defensive: state changes must go through transition()
    if "state" in update_fields:
        raise ValidationError("Cannot modify state directly, use the transition endpoint")

    if "extra_data" in update_fields and update_fields["extra_data"] is not None:
        await custom_fields.validate_extra_data(
            session, ixp_id, "connection", update_fields["extra_data"]
        )

    if "switch_id" in update_fields and update_fields["switch_id"] is not None:
        from ixforge.models.switch import Switch

        switch = await session.get(Switch, update_fields["switch_id"])
        if switch is None or switch.ixp_id != ixp_id:
            raise NotFoundError("Switch", str(update_fields["switch_id"]))

    if "type" in update_fields and update_fields["type"] is not None:
        # Validate type consistency: all connections in the same trunk must have the same type
        new_type = update_fields["type"]
        other_connections = await session.execute(
            select(Connection.type)
            .where(
                Connection.trunk_id == connection.trunk_id,
                Connection.id != connection_id,
            )
        )
        for (other_type,) in other_connections.all():
            if other_type != new_type:
                raise ValidationError(
                    "All connections in a trunk must have the same type"
                )

    for field, value in update_fields.items():
        setattr(connection, field, value)
    await session.flush()
    return await get(session, ixp_id, connection_id)


async def transition(
    session: AsyncSession,
    connection_id: uuid.UUID,
    target_state: ConnectionState,
    *,
    ixp_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
) -> Connection:
    """Transition a connection to a new state with validation."""
    connection = await get(session, ixp_id, connection_id)
    current = connection.state

    allowed = _CONNECTION_TRANSITIONS.get(current, set())
    if target_state not in allowed:
        raise ValidationError(
            f"Cannot transition connection from '{current}' to '{target_state}'",
            details={"current_state": current, "target_state": target_state},
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
            from ixforge.tasks.config import regenerate_configs_for_trunk

            await regenerate_configs_for_trunk.defer_async(
                trunk_id=str(connection.trunk_id),
                triggered_by="connection.state_changed",
            )
        except Exception:
            import structlog

            structlog.get_logger().warning(
                "config_regeneration.defer_failed",
                connection_id=str(connection_id),
                exc_info=True,
            )

    return await get(session, ixp_id, connection_id)


async def delete(session: AsyncSession, ixp_id: uuid.UUID, connection_id: uuid.UUID) -> None:
    """Delete a decommissioned connection."""
    connection = await get(session, ixp_id, connection_id)
    if connection.state != ConnectionState.decommissioned:
        raise ValidationError("Connection must be decommissioned before deletion")
    await session.delete(connection)
    await session.flush()
