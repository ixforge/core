"""Route server service: CRUD operations."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import ConflictError, NotFoundError
from ixforge.models.bgp_session import BGPSession
from ixforge.models.route_server import RouteServer
from ixforge.models.rs_ip_assignment import RSIPAssignment
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.route_server import RouteServerCreate, RouteServerRead, RouteServerUpdate
from ixforge.services.base import paginate


async def create(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    data: RouteServerCreate,
) -> RouteServer:
    """Create a route server."""
    rs = RouteServer(
        ixp_id=ixp_id,
        name=data.name,
        ip_v4=data.ip_v4,
        ip_v6=data.ip_v6,
        is_active=data.is_active,
        notes=data.notes,
    )
    session.add(rs)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("Route server could not be created due to a conflict") from exc
    return rs


async def get(session: AsyncSession, ixp_id: uuid.UUID, route_server_id: uuid.UUID) -> RouteServer:
    """Get a route server by id or raise NotFoundError."""
    rs = await session.get(RouteServer, route_server_id)
    if rs is None or rs.ixp_id != ixp_id:
        raise NotFoundError("RouteServer", str(route_server_id))
    return rs


async def list_route_servers(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    params: CursorParams,
) -> CursorPage[RouteServerRead]:
    """List route servers for an IXP with cursor-based pagination."""
    stmt = select(RouteServer).where(RouteServer.ixp_id == ixp_id)
    return await paginate(
        session,
        stmt,
        params,
        sort_column=RouteServer.created_at,
        id_column=RouteServer.id,
        schema=RouteServerRead,
    )


async def update(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    route_server_id: uuid.UUID,
    data: RouteServerUpdate,
) -> RouteServer:
    """Update a route server."""
    rs = await get(session, ixp_id, route_server_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(rs, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "Route server could not be updated due to a conflict"
        ) from exc
    await session.refresh(rs)
    return rs


async def delete(session: AsyncSession, ixp_id: uuid.UUID, route_server_id: uuid.UUID) -> None:
    """Delete a route server."""
    rs = await get(session, ixp_id, route_server_id)

    has_bgp = await session.scalar(
        select(BGPSession.id)
        .where(BGPSession.route_server_id == route_server_id)
        .limit(1)
    )
    if has_bgp is not None:
        raise ConflictError("Cannot delete route server: BGP sessions are still active")

    has_rs_ip = await session.scalar(
        select(RSIPAssignment.id)
        .where(RSIPAssignment.route_server_id == route_server_id)
        .limit(1)
    )
    if has_rs_ip is not None:
        raise ConflictError("Cannot delete route server: IP assignments are still active")

    await session.delete(rs)
    await session.flush()
