"""Switch endpoints: CRUD (admin only)."""

import uuid

from fastapi import APIRouter, Query, Response

from ixforge.api.deps import AdminUser, DBSession, IXPId
from ixforge.models.switch import Switch
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.switch import SwitchCreate, SwitchRead, SwitchUpdate
from ixforge.services import switches as switch_svc

switches_router = APIRouter(prefix="/switches", tags=["switches"])


@switches_router.get("", response_model=CursorPage[SwitchRead])
async def list_switches(
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CursorPage[SwitchRead]:
    """List switches."""
    params = CursorParams(cursor=cursor, limit=limit)
    return await switch_svc.list_switches(db, ixp_id, params)


@switches_router.post("", response_model=SwitchRead, status_code=201)
async def create_switch(
    body: SwitchCreate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Switch:
    """Create a switch."""
    return await switch_svc.create(db, ixp_id, body)


@switches_router.get("/{switch_id}", response_model=SwitchRead)
async def get_switch(
    switch_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Switch:
    """Get switch details."""
    return await switch_svc.get(db, ixp_id, switch_id)


@switches_router.patch("/{switch_id}", response_model=SwitchRead)
async def update_switch(
    switch_id: uuid.UUID,
    body: SwitchUpdate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Switch:
    """Update a switch."""
    return await switch_svc.update(db, ixp_id, switch_id, body)


@switches_router.delete("/{switch_id}", status_code=204)
async def delete_switch(
    switch_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Response:
    """Delete a switch."""
    await switch_svc.delete(db, ixp_id, switch_id)
    return Response(status_code=204)
