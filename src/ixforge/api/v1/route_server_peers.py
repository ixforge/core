"""Endpoints de peers de route server que no son miembros (admin only)."""

import uuid

from fastapi import APIRouter, Query, Response

from ixforge.api.deps import AdminUser, DBSession, IXPId
from ixforge.models.route_server_peer import RouteServerPeer
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.route_server_peer import (
    RouteServerPeerCreate,
    RouteServerPeerRead,
    RouteServerPeerUpdate,
)
from ixforge.services import route_server_peers as peers_svc

route_server_peers_router = APIRouter(
    prefix="/route-servers/{route_server_id}/peers", tags=["route-server-peers"]
)


@route_server_peers_router.get("", response_model=CursorPage[RouteServerPeerRead])
async def list_peers(
    route_server_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CursorPage[RouteServerPeerRead]:
    """List peers that do not belong to a member."""
    params = CursorParams(cursor=cursor, limit=limit)
    return await peers_svc.list_peers(db, ixp_id, route_server_id, params)


@route_server_peers_router.post("", response_model=RouteServerPeerRead, status_code=201)
async def create_peer(
    route_server_id: uuid.UUID,
    body: RouteServerPeerCreate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> RouteServerPeer:
    """Create an upstream, collector or special peer."""
    return await peers_svc.create(db, ixp_id, route_server_id, body)


@route_server_peers_router.get("/{peer_id}", response_model=RouteServerPeerRead)
async def get_peer(
    route_server_id: uuid.UUID,
    peer_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> RouteServerPeer:
    """Get a peer by id."""
    return await peers_svc.get(db, ixp_id, route_server_id, peer_id)


@route_server_peers_router.patch("/{peer_id}", response_model=RouteServerPeerRead)
async def update_peer(
    route_server_id: uuid.UUID,
    peer_id: uuid.UUID,
    body: RouteServerPeerUpdate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> RouteServerPeer:
    """Update a peer."""
    return await peers_svc.update(db, ixp_id, route_server_id, peer_id, body)


@route_server_peers_router.delete("/{peer_id}", status_code=204)
async def delete_peer(
    route_server_id: uuid.UUID,
    peer_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Response:
    """Delete a peer."""
    await peers_svc.delete(db, ixp_id, route_server_id, peer_id)
    return Response(status_code=204)
