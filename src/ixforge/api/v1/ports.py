"""Port endpoints: CRUD (admin only) plus assign/release."""

import uuid

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from ixforge.api.deps import AdminUser, DBSession, IXPId
from ixforge.models.port import Port
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.port import PortCreate, PortRead, PortUpdate
from ixforge.services import ports as port_svc

ports_router = APIRouter(prefix="/ports", tags=["ports"])


class PortAssignRequest(BaseModel):
    member_id: uuid.UUID


@ports_router.get("", response_model=CursorPage[PortRead])
async def list_ports(
    db: DBSession,
    _ixp_id: IXPId,
    _admin: AdminUser,
    switch_id: uuid.UUID = Query(),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CursorPage[PortRead]:
    """List ports for a switch."""
    params = CursorParams(cursor=cursor, limit=limit)
    return await port_svc.list_ports(db, switch_id, params)


@ports_router.post("", response_model=PortRead, status_code=201)
async def create_port(
    body: PortCreate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Port:
    """Create a port."""
    return await port_svc.create(db, ixp_id, body)


@ports_router.get("/{port_id}", response_model=PortRead)
async def get_port(
    port_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Port:
    """Get port details."""
    return await port_svc.get(db, ixp_id, port_id)


@ports_router.patch("/{port_id}", response_model=PortRead)
async def update_port(
    port_id: uuid.UUID,
    body: PortUpdate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Port:
    """Update a port."""
    return await port_svc.update(db, ixp_id, port_id, body)


@ports_router.delete("/{port_id}", status_code=204)
async def delete_port(
    port_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Response:
    """Delete a port."""
    await port_svc.delete(db, ixp_id, port_id)
    return Response(status_code=204)


@ports_router.post("/{port_id}/assign", response_model=PortRead)
async def assign_port(
    port_id: uuid.UUID,
    body: PortAssignRequest,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Port:
    """Assign a port to a member."""
    return await port_svc.assign(db, ixp_id, port_id, body.member_id)


@ports_router.post("/{port_id}/release", response_model=PortRead)
async def release_port(
    port_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Port:
    """Release a port from its current member assignment."""
    return await port_svc.release(db, ixp_id, port_id)
