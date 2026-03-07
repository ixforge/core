"""Route server VLAN association endpoints (admin only)."""

import uuid

from fastapi import APIRouter, Query, Response

from ixforge.api.deps import AdminUser, DBSession, IXPId
from ixforge.models.route_server_vlan import RouteServerVLAN
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.route_server_vlan import RouteServerVLANCreate, RouteServerVLANRead
from ixforge.services import route_server_vlans as svc

rs_vlans_router = APIRouter(prefix="/route-servers", tags=["route-servers"])


@rs_vlans_router.get("/{rs_id}/vlans", response_model=CursorPage[RouteServerVLANRead])
async def list_rs_vlans(
    rs_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> CursorPage[RouteServerVLANRead]:
    return await svc.list_vlans(db, ixp_id, rs_id, CursorParams(cursor=cursor, limit=limit))


@rs_vlans_router.post("/{rs_id}/vlans", status_code=201, response_model=RouteServerVLANRead)
async def add_rs_vlan(
    rs_id: uuid.UUID, body: RouteServerVLANCreate, db: DBSession, ixp_id: IXPId, _admin: AdminUser
) -> RouteServerVLAN:
    return await svc.add_vlan(db, ixp_id, rs_id, body.vlan_id)


@rs_vlans_router.delete("/{rs_id}/vlans/{vlan_id}", status_code=204)
async def remove_rs_vlan(
    rs_id: uuid.UUID, vlan_id: uuid.UUID, db: DBSession, ixp_id: IXPId, _admin: AdminUser
) -> Response:
    await svc.remove_vlan(db, ixp_id, rs_id, vlan_id)
    return Response(status_code=204)
