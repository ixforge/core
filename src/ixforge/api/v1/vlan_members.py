"""VLAN member association endpoints (admin only)."""

import uuid

from fastapi import APIRouter, Query, Response

from ixforge.api.deps import AdminUser, DBSession, IXPId
from ixforge.models.vlan_member import VLANMember
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.vlan_member import VLANMemberCreate, VLANMemberRead
from ixforge.services import vlan_members as svc

vlan_members_router = APIRouter(prefix="/vlans", tags=["vlans"])


@vlan_members_router.get("/{vlan_id}/members", response_model=CursorPage[VLANMemberRead])
async def list_vlan_members(
    vlan_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> CursorPage[VLANMemberRead]:
    return await svc.list_members(db, ixp_id, vlan_id, CursorParams(cursor=cursor, limit=limit))


@vlan_members_router.post("/{vlan_id}/members", status_code=201, response_model=VLANMemberRead)
async def add_vlan_member(
    vlan_id: uuid.UUID, body: VLANMemberCreate, db: DBSession, ixp_id: IXPId, _admin: AdminUser
) -> VLANMember:
    return await svc.add_member(db, ixp_id, vlan_id, body.member_id)


@vlan_members_router.delete("/{vlan_id}/members/{member_id}", status_code=204)
async def remove_vlan_member(
    vlan_id: uuid.UUID, member_id: uuid.UUID, db: DBSession, ixp_id: IXPId, _admin: AdminUser
) -> Response:
    await svc.remove_member(db, ixp_id, vlan_id, member_id)
    return Response(status_code=204)
