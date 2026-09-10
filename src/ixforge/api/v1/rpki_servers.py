"""Endpoints de servidores RTR para RPKI (admin only)."""

import uuid

from fastapi import APIRouter, Query, Response

from ixforge.api.deps import AdminUser, DBSession, IXPId
from ixforge.models.rpki_server import RPKIServer
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.rpki_server import (
    RPKIServerCreate,
    RPKIServerRead,
    RPKIServerUpdate,
)
from ixforge.services import rpki_servers as rpki_svc

rpki_servers_router = APIRouter(prefix="/rpki-servers", tags=["rpki-servers"])


@rpki_servers_router.get("", response_model=CursorPage[RPKIServerRead])
async def list_rpki_servers(
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CursorPage[RPKIServerRead]:
    """List RTR servers."""
    params = CursorParams(cursor=cursor, limit=limit)
    return await rpki_svc.list_servers(db, ixp_id, params)


@rpki_servers_router.post("", response_model=RPKIServerRead, status_code=201)
async def create_rpki_server(
    body: RPKIServerCreate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> RPKIServer:
    """Create an RTR server."""
    return await rpki_svc.create(db, ixp_id, body)


@rpki_servers_router.get("/{server_id}", response_model=RPKIServerRead)
async def get_rpki_server(
    server_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> RPKIServer:
    """Get an RTR server by id."""
    return await rpki_svc.get(db, ixp_id, server_id)


@rpki_servers_router.patch("/{server_id}", response_model=RPKIServerRead)
async def update_rpki_server(
    server_id: uuid.UUID,
    body: RPKIServerUpdate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> RPKIServer:
    """Update an RTR server."""
    return await rpki_svc.update(db, ixp_id, server_id, body)


@rpki_servers_router.delete("/{server_id}", status_code=204)
async def delete_rpki_server(
    server_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Response:
    """Delete an RTR server."""
    await rpki_svc.delete(db, ixp_id, server_id)
    return Response(status_code=204)
