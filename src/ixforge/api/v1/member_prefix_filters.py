"""Endpoints de filtros de prefijos por miembro y familia (admin only)."""

import uuid

from fastapi import APIRouter, Response

from ixforge.api.deps import AdminUser, DBSession, IXPId
from ixforge.models.member_prefix_filter import MemberPrefixFilter
from ixforge.schemas.member_prefix_filter import (
    MemberPrefixFilterRead,
    MemberPrefixFilterWrite,
)
from ixforge.services import member_prefix_filters as pf_svc

member_prefix_filters_router = APIRouter(
    prefix="/members/{member_id}/prefix-filters", tags=["member-prefix-filters"]
)


@member_prefix_filters_router.get("/{af}", response_model=MemberPrefixFilterRead)
async def get_prefix_filter(
    member_id: uuid.UUID,
    af: int,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> MemberPrefixFilter:
    """Get the prefix filter of a member for one address family."""
    return await pf_svc.get(db, ixp_id, member_id, af)


@member_prefix_filters_router.put("/{af}", response_model=MemberPrefixFilterRead)
async def put_prefix_filter(
    member_id: uuid.UUID,
    af: int,
    body: MemberPrefixFilterWrite,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> MemberPrefixFilter:
    """Create or replace the prefix filter of a member for one address family."""
    return await pf_svc.upsert(db, ixp_id, member_id, af, body)


@member_prefix_filters_router.delete("/{af}", status_code=204)
async def delete_prefix_filter(
    member_id: uuid.UUID,
    af: int,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Response:
    """Delete the prefix filter, which disables prefix filtering for that family."""
    await pf_svc.delete(db, ixp_id, member_id, af)
    return Response(status_code=204)
