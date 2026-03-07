"""VLAN endpoints: CRUD (admin only)."""

import uuid

from fastapi import APIRouter, Query, Response

from ixforge.api.deps import AdminUser, DBSession, IXPId
from ixforge.models.vlan import VLAN
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.vlan import VLANCreate, VLANRead, VLANUpdate
from ixforge.services import vlans as vlan_svc

vlans_router = APIRouter(prefix="/vlans", tags=["vlans"])


@vlans_router.get("", response_model=CursorPage[VLANRead])
async def list_vlans(
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CursorPage[VLANRead]:
    """List VLANs."""
    params = CursorParams(cursor=cursor, limit=limit)
    return await vlan_svc.list_vlans(db, ixp_id, params)


@vlans_router.post("", response_model=VLANRead, status_code=201)
async def create_vlan(
    body: VLANCreate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> VLAN:
    """Create a VLAN."""
    return await vlan_svc.create(db, ixp_id, body)


@vlans_router.get("/{vlan_id}", response_model=VLANRead)
async def get_vlan(
    vlan_id: uuid.UUID,
    db: DBSession,
    _admin: AdminUser,
    ixp_id: IXPId,
) -> VLAN:
    """Get VLAN details."""
    return await vlan_svc.get(db, ixp_id, vlan_id)


@vlans_router.patch("/{vlan_id}", response_model=VLANRead)
async def update_vlan(
    vlan_id: uuid.UUID,
    body: VLANUpdate,
    db: DBSession,
    _admin: AdminUser,
    ixp_id: IXPId,
) -> VLAN:
    """Update a VLAN."""
    return await vlan_svc.update(db, ixp_id, vlan_id, body)


@vlans_router.delete("/{vlan_id}", status_code=204)
async def delete_vlan(
    vlan_id: uuid.UUID,
    db: DBSession,
    _admin: AdminUser,
    ixp_id: IXPId,
) -> Response:
    """Delete a VLAN."""
    await vlan_svc.delete(db, ixp_id, vlan_id)
    return Response(status_code=204)
