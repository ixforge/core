"""Member service: CRUD, state machine, event emission."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import ConflictError, NotFoundError, ValidationError
from ixforge.models.connection import Connection, ConnectionVLAN
from ixforge.models.ip import IPAssignment
from ixforge.models.member import Member
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.member import MemberCreate, MemberRead, MemberState, MemberUpdate
from ixforge.services import custom_fields
from ixforge.services.base import paginate
from ixforge.services.events import create_event

# Valid state transitions: source -> set of allowed targets.
_MEMBER_TRANSITIONS: dict[str, set[str]] = {
    MemberState.prospect: {MemberState.provisioning},
    MemberState.provisioning: {MemberState.active, MemberState.terminated},
    MemberState.active: {MemberState.suspended, MemberState.terminated},
    MemberState.suspended: {MemberState.active, MemberState.terminated},
}


async def create(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    data: MemberCreate,
    *,
    actor_id: uuid.UUID | None = None,
) -> Member:
    """Create a new member in prospect state."""
    if data.extra_data is not None:
        await custom_fields.validate_extra_data(session, ixp_id, "member", data.extra_data)

    member = Member(
        ixp_id=ixp_id,
        name=data.name,
        short_name=data.short_name,
        asn=data.asn,
        state=MemberState.prospect,
        peering_policy=data.peering_policy,
        peering_policy_details=data.peering_policy_details,
        website=data.website,
        peeringdb_id=data.peeringdb_id,
        extra_data=data.extra_data,
    )
    session.add(member)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(f"Member with ASN {data.asn} already exists in this IXP") from exc

    await create_event(
        session,
        ixp_id=ixp_id,
        event_type="member.created",
        actor_id=actor_id,
        resource_type="member",
        resource_id=member.id,
        data={"name": member.name, "asn": member.asn},
    )
    return member


async def get(session: AsyncSession, member_id: uuid.UUID) -> Member:
    """Get a member by id or raise NotFoundError."""
    member = await session.get(Member, member_id)
    if member is None:
        raise NotFoundError("Member", str(member_id))
    return member


async def list_members(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    params: CursorParams,
) -> CursorPage[MemberRead]:
    """List members for an IXP with cursor-based pagination."""
    stmt = select(Member).where(Member.ixp_id == ixp_id)
    return await paginate(
        session,
        stmt,
        params,
        sort_column=Member.created_at,
        id_column=Member.id,
        schema=MemberRead,
    )


async def update(
    session: AsyncSession,
    member_id: uuid.UUID,
    data: MemberUpdate,
    *,
    actor_id: uuid.UUID | None = None,
) -> Member:
    """Update mutable fields on an existing member."""
    member = await get(session, member_id)
    update_fields = data.model_dump(exclude_unset=True)

    if "extra_data" in update_fields and update_fields["extra_data"] is not None:
        await custom_fields.validate_extra_data(
            session, member.ixp_id, "member", update_fields["extra_data"]
        )

    for field, value in update_fields.items():
        setattr(member, field, value)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("Member update caused a conflict") from exc

    await session.refresh(member)
    await create_event(
        session,
        ixp_id=member.ixp_id,
        event_type="member.updated",
        actor_id=actor_id,
        resource_type="member",
        resource_id=member.id,
        data={"updated_fields": list(update_fields.keys())},
    )
    return member


async def _has_complete_connection(session: AsyncSession, member_id: uuid.UUID) -> bool:
    """Check whether the member has at least one connection with a port, VLAN, and IP."""
    stmt = (
        select(Connection.id)
        .where(Connection.member_id == member_id)
        .where(Connection.port_id.is_not(None))
    )
    result = await session.execute(stmt)
    connection_ids = [row[0] for row in result.all()]

    for conn_id in connection_ids:
        has_vlan = await session.scalar(
            select(ConnectionVLAN.id).where(ConnectionVLAN.connection_id == conn_id).limit(1)
        )
        if has_vlan is None:
            continue

        has_ip = await session.scalar(
            select(IPAssignment.id).where(IPAssignment.connection_id == conn_id).limit(1)
        )
        if has_ip is not None:
            return True

    return False


async def transition(
    session: AsyncSession,
    member_id: uuid.UUID,
    target_state: MemberState,
    *,
    actor_id: uuid.UUID | None = None,
) -> Member:
    """Transition a member to a new state with validation."""
    member = await get(session, member_id)
    current = member.state

    allowed = _MEMBER_TRANSITIONS.get(current, set())
    if target_state not in allowed:
        raise ValidationError(
            f"Cannot transition member from '{current}' to '{target_state}'",
            details={"current_state": current, "target_state": target_state},
        )

    # provisioning -> active requires a complete connection.
    if (
        current == MemberState.provisioning
        and target_state == MemberState.active
        and not await _has_complete_connection(session, member_id)
    ):
        raise ValidationError(
            "Cannot activate member: at least one connection must have "
            "a port, VLAN, and IP assigned"
        )

    old_state = member.state
    member.state = target_state
    await session.flush()
    await session.refresh(member)

    await create_event(
        session,
        ixp_id=member.ixp_id,
        event_type="member.state_changed",
        actor_id=actor_id,
        resource_type="member",
        resource_id=member.id,
        data={"old_state": old_state, "new_state": target_state},
    )

    if target_state == MemberState.active or old_state == MemberState.active:
        try:
            from ixforge.tasks.config import regenerate_configs_for_member

            await regenerate_configs_for_member.defer_async(
                member_id=str(member_id),
                triggered_by="member.state_changed",
            )
        except Exception:
            import structlog

            structlog.get_logger().warning(
                "config_regeneration.defer_failed",
                member_id=str(member_id),
            )

    return member
