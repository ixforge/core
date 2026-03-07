"""Location endpoints (admin only)."""

import uuid

from fastapi import APIRouter, Query, Response

from ixforge.api.deps import AdminUser, DBSession, IXPId
from ixforge.models.location import Location
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.location import LocationCreate, LocationRead, LocationUpdate
from ixforge.services import locations as loc_svc

locations_router = APIRouter(prefix="/locations", tags=["locations"])


@locations_router.get("", response_model=CursorPage[LocationRead])
async def list_locations(
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CursorPage[LocationRead]:
    return await loc_svc.list_locations(db, ixp_id, CursorParams(cursor=cursor, limit=limit))


@locations_router.post("", response_model=LocationRead, status_code=201)
async def create_location(
    body: LocationCreate, db: DBSession, ixp_id: IXPId, _admin: AdminUser
) -> Location:
    return await loc_svc.create(db, ixp_id, body)


@locations_router.get("/{location_id}", response_model=LocationRead)
async def get_location(
    location_id: uuid.UUID, db: DBSession, _admin: AdminUser, ixp_id: IXPId
) -> Location:
    return await loc_svc.get(db, ixp_id, location_id)


@locations_router.patch("/{location_id}", response_model=LocationRead)
async def update_location(
    location_id: uuid.UUID, body: LocationUpdate, db: DBSession, _admin: AdminUser, ixp_id: IXPId
) -> Location:
    return await loc_svc.update(db, ixp_id, location_id, body)


@locations_router.delete("/{location_id}", status_code=204)
async def delete_location(
    location_id: uuid.UUID, db: DBSession, _admin: AdminUser, ixp_id: IXPId
) -> Response:
    await loc_svc.delete(db, ixp_id, location_id)
    return Response(status_code=204)
