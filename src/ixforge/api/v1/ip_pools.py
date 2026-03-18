"""IP pool endpoints: pool CRUD (admin only) plus IP allocation."""

import uuid

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from ixforge.api.deps import AdminUser, DBSession, IXPId
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.ip import IPAssignmentRead, IPPoolCreate, IPPoolRead
from ixforge.services import ipam

ip_pools_router = APIRouter(tags=["ip-pools"])


class IPAllocateRequest(BaseModel):
    trunk_vlan_id: uuid.UUID
    address: str | None = None


@ip_pools_router.get("/ip-pools", response_model=CursorPage[IPPoolRead])
async def list_ip_pools(
    db: DBSession,
    _admin: AdminUser,
    ixp_id: IXPId,
    vlan_id: uuid.UUID = Query(),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CursorPage[IPPoolRead]:
    """List IP pools for a VLAN"""
    params = CursorParams(cursor=cursor, limit=limit)
    return await ipam.list_pools(db, ixp_id, vlan_id, params)


@ip_pools_router.post("/ip-pools", response_model=IPPoolRead, status_code=201)
async def create_ip_pool(
    body: IPPoolCreate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> IPPool:
    """Create an IP pool"""
    return await ipam.create_pool(db, ixp_id, body)


@ip_pools_router.get("/ip-pools/available")
async def get_pools_available(
    db: DBSession,
    _admin: AdminUser,
    ixp_id: IXPId,
    vlan_id: uuid.UUID = Query(),
) -> list[dict[str, object]]:
    """Get pools for a VLAN with availability info (next IP, usage stats)"""
    return await ipam.get_pools_with_availability(db, ixp_id, vlan_id)


@ip_pools_router.get("/ip-pools/{pool_id}", response_model=IPPoolRead)
async def get_ip_pool(
    pool_id: uuid.UUID,
    db: DBSession,
    _admin: AdminUser,
    ixp_id: IXPId,
) -> IPPool:
    """Get IP pool details"""
    return await ipam.get_pool(db, pool_id, ixp_id)


@ip_pools_router.delete("/ip-pools/{pool_id}", status_code=204)
async def delete_ip_pool(
    pool_id: uuid.UUID,
    db: DBSession,
    _admin: AdminUser,
    ixp_id: IXPId,
) -> Response:
    """Delete an IP pool"""
    await ipam.delete_pool(db, pool_id, ixp_id)
    return Response(status_code=204)


@ip_pools_router.get(
    "/ip-pools/{pool_id}/assignments",
    response_model=CursorPage[IPAssignmentRead],
)
async def list_ip_assignments(
    pool_id: uuid.UUID,
    db: DBSession,
    _admin: AdminUser,
    ixp_id: IXPId,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CursorPage[IPAssignmentRead]:
    """List IP assignments in a pool"""
    params = CursorParams(cursor=cursor, limit=limit)
    return await ipam.list_assignments(db, ixp_id, pool_id, params)


@ip_pools_router.post(
    "/ip-pools/{pool_id}/assign",
    response_model=IPAssignmentRead,
    status_code=201,
)
async def allocate_ip(
    pool_id: uuid.UUID,
    body: IPAllocateRequest,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> IPAssignment:
    """Allocate an IP address from a pool.

    If ``address`` is provided, manual allocation is used;
    otherwise the next available address is assigned sequentially.
    """
    if body.address is not None:
        return await ipam.allocate_manual(db, ixp_id, pool_id, body.trunk_vlan_id, body.address)
    return await ipam.allocate_sequential(db, ixp_id, pool_id, body.trunk_vlan_id)


@ip_pools_router.delete("/ip-assignments/{assignment_id}", status_code=204)
async def release_ip(
    assignment_id: uuid.UUID,
    db: DBSession,
    _admin: AdminUser,
    ixp_id: IXPId,
) -> Response:
    """Release an IP assignment"""
    await ipam.release(db, assignment_id, ixp_id)
    return Response(status_code=204)
