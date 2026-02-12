"""Route server service: CRUD operations."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import NotFoundError
from ixforge.models.route_server import RouteServer
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
        hostname=data.hostname,
        ip_v4=data.ip_v4,
        ip_v6=data.ip_v6,
        asn=data.asn,
        software=data.software,
        is_active=data.is_active,
    )
    session.add(rs)
    await session.flush()
    return rs


async def get(session: AsyncSession, route_server_id: uuid.UUID) -> RouteServer:
    """Get a route server by id or raise NotFoundError."""
    rs = await session.get(RouteServer, route_server_id)
    if rs is None:
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
    route_server_id: uuid.UUID,
    data: RouteServerUpdate,
) -> RouteServer:
    """Update a route server."""
    rs = await get(session, route_server_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(rs, field, value)
    await session.flush()
    return rs


async def delete(session: AsyncSession, route_server_id: uuid.UUID) -> None:
    """Delete a route server."""
    rs = await get(session, route_server_id)
    await session.delete(rs)
    await session.flush()
