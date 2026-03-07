"""Connection endpoints: CRUD, state transitions, VLAN/IP management."""

import uuid

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from ixforge.api.deps import AdminUser, CurrentUser, DBSession, IXPId
from ixforge.exceptions import ForbiddenError
from ixforge.models.connection import Connection, ConnectionVLAN
from ixforge.models.ip import IPAssignment
from ixforge.models.user import UserRole
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.connection import (
    ConnectionCreate,
    ConnectionRead,
    ConnectionState,
    ConnectionUpdate,
    ConnectionVLANCreate,
)
from ixforge.schemas.ip import IPAssignmentRead
from ixforge.services import connections as conn_svc

connections_router = APIRouter(prefix="/connections", tags=["connections"])


class ConnectionStateTransition(BaseModel):
    state: ConnectionState


class ConnectionVLANRead(BaseModel):
    id: uuid.UUID
    connection_id: uuid.UUID
    vlan_id: uuid.UUID
    tagged: bool

    model_config = {"from_attributes": True}


class ConnectionIPRequest(BaseModel):
    pool_id: uuid.UUID
    address: str | None = None


@connections_router.get("", response_model=CursorPage[ConnectionRead])
async def list_connections(
    db: DBSession,
    user: CurrentUser,
    _ixp_id: IXPId,
    member_id: uuid.UUID = Query(),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CursorPage[ConnectionRead]:
    """List connections for a member.

    Admins can list any member's connections; member users can only list
    their own.
    """
    if user.role == UserRole.member:
        if user.member_id is None:
            raise ForbiddenError("Member user without assigned member cannot access connections")
        if member_id != user.member_id:
            raise ForbiddenError("You can only view your own connections")

    params = CursorParams(cursor=cursor, limit=limit)
    return await conn_svc.list_connections(db, member_id, params)


@connections_router.post("", response_model=ConnectionRead, status_code=201)
async def create_connection(
    body: ConnectionCreate,
    db: DBSession,
    ixp_id: IXPId,
    admin: AdminUser,
) -> Connection:
    """Create a connection."""
    return await conn_svc.create(db, ixp_id, body, actor_id=admin.id)


@connections_router.get("/{connection_id}", response_model=ConnectionRead)
async def get_connection(
    connection_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    user: CurrentUser,
) -> Connection:
    """Get connection details.

    Admins can view any connection; member users can only view their own.
    """
    connection = await conn_svc.get(db, ixp_id, connection_id)

    if user.role == UserRole.member:
        if user.member_id is None:
            raise ForbiddenError("Member user without assigned member cannot access connections")
        if connection.member_id != user.member_id:
            raise ForbiddenError("You do not have access to this connection")

    return connection


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


@connections_router.post(
    "/{connection_id}/vlans",
    response_model=ConnectionVLANRead,
    status_code=201,
)
async def assign_vlan(
    connection_id: uuid.UUID,
    body: ConnectionVLANCreate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> ConnectionVLAN:
    """Assign a VLAN to a connection."""
    return await conn_svc.assign_vlan(db, ixp_id, connection_id, body)


@connections_router.delete("/{connection_id}/vlans/{vlan_id}", status_code=204)
async def unassign_vlan(
    connection_id: uuid.UUID,
    vlan_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Response:
    """Remove a VLAN from a connection."""
    await conn_svc.unassign_vlan(db, ixp_id, connection_id, vlan_id)
    return Response(status_code=204)


@connections_router.post(
    "/{connection_id}/ips",
    response_model=IPAssignmentRead,
    status_code=201,
)
async def assign_ip(
    connection_id: uuid.UUID,
    body: ConnectionIPRequest,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> IPAssignment:
    """Assign an IP to a connection from a pool."""
    return await conn_svc.assign_ip(db, ixp_id, connection_id, body.pool_id, address=body.address)


@connections_router.delete("/{connection_id}/ips/{assignment_id}", status_code=204)
async def release_ip(
    connection_id: uuid.UUID,
    assignment_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Response:
    """Release an IP assignment from a connection."""
    await conn_svc.release_ip(db, ixp_id, connection_id, assignment_id)
    return Response(status_code=204)
