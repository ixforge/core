"""Route server endpoints: CRUD (admin only)."""

import uuid

from fastapi import APIRouter, Query, Response

from ixforge.api.deps import AdminUser, DBSession, IXPId
from ixforge.models.route_server import RouteServer
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.route_server import (
    RouteServerCreate,
    RouteServerRead,
    RouteServerUpdate,
)
from ixforge.services import route_servers as rs_svc

route_servers_router = APIRouter(prefix="/route-servers", tags=["route-servers"])


@route_servers_router.get("", response_model=CursorPage[RouteServerRead])
async def list_route_servers(
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CursorPage[RouteServerRead]:
    """List route servers."""
    params = CursorParams(cursor=cursor, limit=limit)
    return await rs_svc.list_route_servers(db, ixp_id, params)


@route_servers_router.post("", response_model=RouteServerRead, status_code=201)
async def create_route_server(
    body: RouteServerCreate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> RouteServer:
    """Create a route server."""
    return await rs_svc.create(db, ixp_id, body)


@route_servers_router.get("/{route_server_id}", response_model=RouteServerRead)
async def get_route_server(
    route_server_id: uuid.UUID,
    db: DBSession,
    _admin: AdminUser,
) -> RouteServer:
    """Get route server details."""
    return await rs_svc.get(db, route_server_id)


@route_servers_router.patch("/{route_server_id}", response_model=RouteServerRead)
async def update_route_server(
    route_server_id: uuid.UUID,
    body: RouteServerUpdate,
    db: DBSession,
    _admin: AdminUser,
) -> RouteServer:
    """Update a route server."""
    return await rs_svc.update(db, route_server_id, body)


@route_servers_router.delete("/{route_server_id}", status_code=204)
async def delete_route_server(
    route_server_id: uuid.UUID,
    db: DBSession,
    _admin: AdminUser,
) -> Response:
    """Delete a route server."""
    await rs_svc.delete(db, route_server_id)
    return Response(status_code=204)
