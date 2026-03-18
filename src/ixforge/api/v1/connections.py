"""Connection endpoints: CRUD and state transitions."""

import uuid

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from ixforge.api.deps import AdminUser, CurrentUser, DBSession, IXPId
from ixforge.exceptions import NotFoundError
from ixforge.models.connection import Connection
from ixforge.models.user import UserRole
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.connection import (
    ConnectionRead,
    ConnectionState,
    ConnectionUpdate,
)
from ixforge.services import connections as conn_svc

connections_router = APIRouter(prefix="/connections", tags=["connections"])


class ConnectionStateTransition(BaseModel):
    state: ConnectionState


@connections_router.get("", response_model=CursorPage[ConnectionRead])
async def list_connections(
    db: DBSession,
    user: CurrentUser,
    ixp_id: IXPId,
    switch_id: uuid.UUID | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CursorPage[ConnectionRead]:
    """List connections filtered by switch.

    Admins can list any connections; member users can only list their own.
    """
    params = CursorParams(cursor=cursor, limit=limit)
    # Member users: filter connections to only those belonging to their trunks
    member_id = None
    if user.role == UserRole.member:
        member_id = user.member_id
    return await conn_svc.list_connections(db, ixp_id, params, switch_id=switch_id, member_id=member_id)


@connections_router.get("/{connection_id}", response_model=ConnectionRead)
async def get_connection(
    connection_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    user: CurrentUser,
) -> Connection:
    """Get connection details."""
    conn = await conn_svc.get(db, ixp_id, connection_id)
    if user.role == UserRole.member and conn.trunk.member_id != user.member_id:
        raise NotFoundError("connection", connection_id)
    return conn


@connections_router.patch("/{connection_id}", response_model=ConnectionRead)
async def update_connection(
    connection_id: uuid.UUID,
    body: ConnectionUpdate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Connection:
    """Update a connection."""
    return await conn_svc.update(db, ixp_id, connection_id, body)


@connections_router.delete("/{connection_id}", status_code=204)
async def delete_connection(
    connection_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Response:
    """Delete a decommissioned connection."""
    await conn_svc.delete(db, ixp_id, connection_id)
    return Response(status_code=204)


@connections_router.post("/{connection_id}/transition", response_model=ConnectionRead)
async def transition_connection(
    connection_id: uuid.UUID,
    body: ConnectionStateTransition,
    db: DBSession,
    ixp_id: IXPId,
    admin: AdminUser,
) -> Connection:
    """Transition a connection to a new state."""
    return await conn_svc.transition(
        db, connection_id, body.state, ixp_id=ixp_id, actor_id=admin.id
    )
