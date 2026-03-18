"""Trunk endpoints: CRUD, state transitions, VLAN/IP/connection management."""

import uuid

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel
from sqlalchemy import select

from ixforge.api.deps import AdminUser, CurrentUser, DBSession, IXPId
from ixforge.exceptions import ForbiddenError, NotFoundError
from ixforge.models.connection import Connection
from ixforge.models.trunk import Trunk
from ixforge.models.user import UserRole
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.connection import ConnectionCreate, ConnectionRead
from ixforge.schemas.ip import IPAssignmentRead
from ixforge.schemas.trunk import (
    TrunkCreate,
    TrunkRead,
    TrunkStateTransition,
    TrunkUpdate,
    TrunkVLANCreate,
    TrunkVLANRead,
)
from ixforge.services import trunks

trunks_router = APIRouter(prefix="/trunks", tags=["trunks"])


async def _verify_trunk_vlan_ownership(
    db: DBSession, ixp_id: uuid.UUID, trunk_id: uuid.UUID, trunk_vlan_id: uuid.UUID
) -> None:
    """Verify that a TrunkVLAN belongs to the given trunk"""
    from ixforge.models.trunk import TrunkVLAN

    tv = await db.scalar(
        select(TrunkVLAN.id).where(
            TrunkVLAN.id == trunk_vlan_id,
            TrunkVLAN.trunk_id == trunk_id,
            TrunkVLAN.ixp_id == ixp_id,
        )
    )
    if tv is None:
        raise NotFoundError("TrunkVLAN", str(trunk_vlan_id))


class _IPAssignBody(BaseModel):
    pool_id: uuid.UUID
    address: str | None = None


@trunks_router.get("", response_model=CursorPage[TrunkRead])
async def list_trunks(
    db: DBSession,
    user: CurrentUser,
    ixp_id: IXPId,
    member_id: uuid.UUID | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CursorPage[TrunkRead]:
    """List trunks.

    Admins can list all trunks with optional member_id filter.
    Member users only see their own trunks.
    """
    params = CursorParams(cursor=cursor, limit=limit)
    if user.role == UserRole.member:
        if user.member_id is None:
            raise ForbiddenError("Member user without assigned member cannot access trunks")
        return await trunks.list_trunks(db, ixp_id, params, member_id=user.member_id)
    return await trunks.list_trunks(db, ixp_id, params, member_id=member_id)


@trunks_router.post("", response_model=TrunkRead, status_code=201)
async def create_trunk(
    body: TrunkCreate,
    db: DBSession,
    ixp_id: IXPId,
    admin: AdminUser,
) -> Trunk:
    """Create a new trunk in draft state."""
    return await trunks.create(db, ixp_id, body, actor_id=admin.id)


@trunks_router.get("/{trunk_id}", response_model=TrunkRead)
async def get_trunk(
    trunk_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    user: CurrentUser,
) -> Trunk:
    """Get trunk details."""
    trunk = await trunks.get(db, ixp_id, trunk_id)
    if user.role == UserRole.member:
        if user.member_id is None:
            raise ForbiddenError("Member user without assigned member cannot access trunks")
        if trunk.member_id != user.member_id:
            raise NotFoundError("Trunk", str(trunk_id))
    return trunk


@trunks_router.patch("/{trunk_id}", response_model=TrunkRead)
async def update_trunk(
    trunk_id: uuid.UUID,
    body: TrunkUpdate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Trunk:
    """Update mutable trunk fields."""
    return await trunks.update(db, ixp_id, trunk_id, body)


@trunks_router.delete("/{trunk_id}", status_code=204)
async def delete_trunk(
    trunk_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Response:
    """Delete a decommissioned trunk."""
    await trunks.delete(db, ixp_id, trunk_id)
    return Response(status_code=204)


@trunks_router.post("/{trunk_id}/transition", response_model=TrunkRead)
async def transition_trunk(
    trunk_id: uuid.UUID,
    body: TrunkStateTransition,
    db: DBSession,
    ixp_id: IXPId,
    admin: AdminUser,
) -> Trunk:
    """Transition a trunk to a new state."""
    return await trunks.transition(db, trunk_id, body.state, ixp_id=ixp_id, actor_id=admin.id)


# ---------------------------------------------------------------------------
# VLAN sub-resources
# ---------------------------------------------------------------------------


@trunks_router.get("/{trunk_id}/vlans", response_model=list[TrunkVLANRead])
async def list_trunk_vlans(
    trunk_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    user: CurrentUser,
) -> list:
    """List VLANs assigned to a trunk."""
    if user.role == UserRole.member:
        if user.member_id is None:
            raise ForbiddenError("Member user without assigned member cannot access trunks")
        trunk = await trunks.get(db, ixp_id, trunk_id)
        if trunk.member_id != user.member_id:
            raise NotFoundError("Trunk", str(trunk_id))
    return await trunks.list_vlans(db, ixp_id, trunk_id)


@trunks_router.post("/{trunk_id}/vlans", response_model=TrunkVLANRead, status_code=201)
async def assign_vlan(
    trunk_id: uuid.UUID,
    body: TrunkVLANCreate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> object:
    """Assign a VLAN to a trunk."""
    return await trunks.assign_vlan(db, ixp_id, trunk_id, body.vlan_id)


@trunks_router.delete("/{trunk_id}/vlans/{trunk_vlan_id}", status_code=204)
async def unassign_vlan(
    trunk_id: uuid.UUID,
    trunk_vlan_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Response:
    """Unassign a VLAN from a trunk."""
    await trunks.unassign_vlan(db, ixp_id, trunk_id, trunk_vlan_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# IP sub-resources (nested under VLAN)
# ---------------------------------------------------------------------------


@trunks_router.get(
    "/{trunk_id}/vlans/{trunk_vlan_id}/ips",
    response_model=list[IPAssignmentRead],
)
async def list_trunk_vlan_ips(
    trunk_id: uuid.UUID,
    trunk_vlan_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    user: CurrentUser,
) -> list:
    """List IP assignments for a trunk VLAN."""
    await _verify_trunk_vlan_ownership(db, ixp_id, trunk_id, trunk_vlan_id)
    if user.role == UserRole.member:
        if user.member_id is None:
            raise ForbiddenError("Member user without assigned member cannot access trunks")
        trunk = await trunks.get(db, ixp_id, trunk_id)
        if trunk.member_id != user.member_id:
            raise NotFoundError("Trunk", str(trunk_id))
    return await trunks.list_ips(db, ixp_id, trunk_vlan_id)


@trunks_router.post(
    "/{trunk_id}/vlans/{trunk_vlan_id}/ips",
    response_model=IPAssignmentRead,
    status_code=201,
)
async def assign_ip(
    trunk_id: uuid.UUID,
    trunk_vlan_id: uuid.UUID,
    body: _IPAssignBody,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> object:
    """Assign an IP to a trunk VLAN."""
    await _verify_trunk_vlan_ownership(db, ixp_id, trunk_id, trunk_vlan_id)
    return await trunks.assign_ip(db, ixp_id, trunk_vlan_id, body.pool_id, address=body.address)


@trunks_router.delete(
    "/{trunk_id}/vlans/{trunk_vlan_id}/ips/{assignment_id}",
    status_code=204,
)
async def release_ip(
    trunk_id: uuid.UUID,
    trunk_vlan_id: uuid.UUID,
    assignment_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Response:
    """Release an IP assignment from a trunk VLAN."""
    await _verify_trunk_vlan_ownership(db, ixp_id, trunk_id, trunk_vlan_id)
    await trunks.release_ip(db, ixp_id, assignment_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Connection sub-resources
# ---------------------------------------------------------------------------


@trunks_router.get("/{trunk_id}/connections", response_model=list[ConnectionRead])
async def list_trunk_connections(
    trunk_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    user: CurrentUser,
) -> list[Connection]:
    """List connections belonging to a trunk."""
    trunk = await trunks.get(db, ixp_id, trunk_id)
    if user.role == UserRole.member:
        if user.member_id is None:
            raise ForbiddenError("Member user without assigned member cannot access trunks")
        if trunk.member_id != user.member_id:
            raise NotFoundError("Trunk", str(trunk_id))

    result = await db.execute(
        select(Connection).where(
            Connection.trunk_id == trunk.id,
            Connection.ixp_id == ixp_id,
        )
    )
    return list(result.scalars().all())


@trunks_router.post("/{trunk_id}/connections", response_model=ConnectionRead, status_code=201)
async def add_trunk_connection(
    trunk_id: uuid.UUID,
    body: ConnectionCreate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Connection:
    """Add a connection to a trunk."""
    return await trunks.add_connection(db, ixp_id, trunk_id, body)
