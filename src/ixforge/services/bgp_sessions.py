"""BGP session service: list, get, admin state management."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import BGPAdminState
from ixforge.exceptions import NotFoundError, ValidationError
from ixforge.models.bgp_session import BGPSession
from ixforge.models.connection import Connection
from ixforge.schemas.bgp_session import BGPSessionRead
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.services.base import paginate

_VALID_ADMIN_VALUES = {s.value for s in BGPAdminState}


async def get(session: AsyncSession, session_id: uuid.UUID) -> BGPSession:
    """Get a BGP session by id or raise NotFoundError."""
    bgp_session = await session.get(BGPSession, session_id)
    if bgp_session is None:
        raise NotFoundError("BGPSession", str(session_id))
    return bgp_session


async def list_sessions(
    session: AsyncSession,
    route_server_id: uuid.UUID,
    params: CursorParams,
) -> CursorPage[BGPSessionRead]:
    """List BGP sessions for a route server with cursor-based pagination."""
    stmt = select(BGPSession).where(BGPSession.route_server_id == route_server_id)
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
    route_server_id: uuid.UUID,
    member_id: uuid.UUID | None,
    params: CursorParams,
) -> CursorPage[BGPSessionRead]:
    """List BGP sessions for a route server filtered by member's connections."""
    stmt = (
        select(BGPSession)
        .join(Connection, BGPSession.connection_id == Connection.id)
        .where(
            BGPSession.route_server_id == route_server_id,
            Connection.member_id == member_id,
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


async def update_admin_state(
    session: AsyncSession,
    session_id: uuid.UUID,
    admin_state: str,
) -> BGPSession:
    """Update the admin_state of a BGP session (up or down)."""
    if admin_state not in _VALID_ADMIN_VALUES:
        raise ValidationError(
            f"Invalid admin_state '{admin_state}': must be one of {sorted(_VALID_ADMIN_VALUES)}"
        )

    bgp_session = await get(session, session_id)
    bgp_session.admin_state = BGPAdminState(admin_state)
    await session.flush()
    return bgp_session
