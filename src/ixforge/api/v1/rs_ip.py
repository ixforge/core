"""Route server IP assignment endpoints (admin only)."""

import uuid

from fastapi import APIRouter, Response

from ixforge.api.deps import AdminUser, DBSession, IXPId
from ixforge.models.rs_ip_assignment import RSIPAssignment
from ixforge.schemas.rs_ip import RSIPAssignmentCreate, RSIPAssignmentRead
from ixforge.services import rs_ip as svc

rs_ip_router = APIRouter(prefix="/route-servers", tags=["route-servers"])


@rs_ip_router.get("/{rs_id}/ips", response_model=list[RSIPAssignmentRead])
async def list_rs_ips(
    rs_id: uuid.UUID, db: DBSession, ixp_id: IXPId, _admin: AdminUser
) -> list[RSIPAssignmentRead]:
    """List all IP assignments for a route server."""
    return await svc.list_assignments(db, ixp_id, rs_id)


@rs_ip_router.post("/{rs_id}/ips", response_model=RSIPAssignmentRead, status_code=201)
async def assign_rs_ip(
    rs_id: uuid.UUID, body: RSIPAssignmentCreate, db: DBSession, ixp_id: IXPId, _admin: AdminUser
) -> RSIPAssignment:
    """Assign an IP from a pool to a route server."""
    return await svc.assign(db, ixp_id, rs_id, body)


@rs_ip_router.delete("/{rs_id}/ips/{assignment_id}", status_code=204)
async def release_rs_ip(
    rs_id: uuid.UUID, assignment_id: uuid.UUID, db: DBSession, ixp_id: IXPId, _admin: AdminUser
) -> Response:
    """Release an RS IP assignment."""
    await svc.release(db, ixp_id, rs_id, assignment_id)
    return Response(status_code=204)
