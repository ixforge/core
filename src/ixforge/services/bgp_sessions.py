"""BGP session service: CRUD, admin state management."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import BGPAdminState, BGPOperState, TrunkState
from ixforge.exceptions import ConflictError, NotFoundError, ValidationError
from ixforge.models.bgp_session import BGPSession
from ixforge.models.route_server import RouteServer
from ixforge.models.trunk import Trunk, TrunkVLAN
from ixforge.schemas.bgp_session import BGPSessionCreate, BGPSessionRead
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.services.base import paginate

_VALID_ADMIN_VALUES = {s.value for s in BGPAdminState}


async def create(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    data: BGPSessionCreate,
) -> BGPSession:
    """Create a new BGP session."""
    rs = await session.get(RouteServer, data.route_server_id)
    if rs is None or rs.ixp_id != ixp_id:
        raise NotFoundError("RouteServer")

    trunk_vlan = await session.get(TrunkVLAN, data.trunk_vlan_id)
    if trunk_vlan is None or trunk_vlan.ixp_id != ixp_id:
        raise NotFoundError("TrunkVLAN")

    trunk = await session.get(Trunk, trunk_vlan.trunk_id)
    if trunk is None or trunk.state != TrunkState.active:
        raise ValidationError("Trunk must be active to create a BGP session")

    bgp_session = BGPSession(
        ixp_id=ixp_id,
        route_server_id=data.route_server_id,
        trunk_vlan_id=data.trunk_vlan_id,
        peer_ip=data.peer_ip,
        peer_asn=data.peer_asn,
        af=data.af,
        admin_state=BGPAdminState.up,
        oper_state=BGPOperState.unknown,
        max_prefixes=data.max_prefixes,
        import_limit=data.import_limit,
        export_limit=data.export_limit,
    )
    session.add(bgp_session)
    try:
        await session.flush()
    except IntegrityError:
        raise ConflictError(
            "BGP session already exists for this route server, connection, and address family"
        ) from None

    await session.refresh(bgp_session)
    return bgp_session


async def get(session: AsyncSession, ixp_id: uuid.UUID, session_id: uuid.UUID) -> BGPSession:
    """Get a BGP session by id or raise NotFoundError."""
    bgp_session = await session.get(BGPSession, session_id)
    if bgp_session is None or bgp_session.ixp_id != ixp_id:
        raise NotFoundError("BGPSession", str(session_id))
    return bgp_session


async def list_sessions(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    route_server_id: uuid.UUID,
    params: CursorParams,
) -> CursorPage[BGPSessionRead]:
    """List BGP sessions for a route server with cursor-based pagination."""
    stmt = select(BGPSession).where(
        BGPSession.route_server_id == route_server_id,
        BGPSession.ixp_id == ixp_id,
    )
    return await paginate(
        session,
        stmt,
        params,
        sort_column=BGPSession.created_at,
        id_column=BGPSession.id,
        schema=BGPSessionRead,
    )


async def list_sessions_for_member(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    route_server_id: uuid.UUID,
    member_id: uuid.UUID | None,
    params: CursorParams,
) -> CursorPage[BGPSessionRead]:
    """List BGP sessions for a route server filtered by member's trunks."""
    stmt = (
        select(BGPSession)
        .join(TrunkVLAN, BGPSession.trunk_vlan_id == TrunkVLAN.id)
        .join(Trunk, TrunkVLAN.trunk_id == Trunk.id)
        .where(
            BGPSession.route_server_id == route_server_id,
            BGPSession.ixp_id == ixp_id,
            Trunk.member_id == member_id,
        )
    )
    return await paginate(
        session,
        stmt,
        params,
        sort_column=BGPSession.created_at,
        id_column=BGPSession.id,
        schema=BGPSessionRead,
    )


async def delete(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    session_id: uuid.UUID,
) -> None:
    """Delete a BGP session."""
    bgp_session = await get(session, ixp_id, session_id)
    await session.delete(bgp_session)
    await session.flush()


async def update_admin_state(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    session_id: uuid.UUID,
    admin_state: str,
) -> BGPSession:
    """Update the admin_state of a BGP session (up or down)."""
    if admin_state not in _VALID_ADMIN_VALUES:
        raise ValidationError(
            f"Invalid admin_state '{admin_state}': must be one of {sorted(_VALID_ADMIN_VALUES)}"
        )

    bgp_session = await get(session, ixp_id, session_id)
    bgp_session.admin_state = BGPAdminState(admin_state)
    await session.flush()
    await session.refresh(bgp_session)
    return bgp_session
