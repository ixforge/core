"""Location service: CRUD."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import ConflictError, NotFoundError
from ixforge.models.location import Location
from ixforge.models.switch import Switch
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.location import LocationCreate, LocationRead, LocationUpdate
from ixforge.services.base import paginate


async def create(session: AsyncSession, ixp_id: uuid.UUID, data: LocationCreate) -> Location:
    loc = Location(ixp_id=ixp_id, name=data.name, city=data.city, country=data.country)
    session.add(loc)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(f"Location '{data.name}' already exists in this IXP") from exc
    return loc


async def get(session: AsyncSession, ixp_id: uuid.UUID, location_id: uuid.UUID) -> Location:
    loc = await session.get(Location, location_id)
    if loc is None or loc.ixp_id != ixp_id:
        raise NotFoundError("Location", str(location_id))
    return loc


async def list_locations(
    session: AsyncSession, ixp_id: uuid.UUID, params: CursorParams
) -> CursorPage[LocationRead]:
    stmt = select(Location).where(Location.ixp_id == ixp_id)
    return await paginate(session, stmt, params, Location.created_at, Location.id, LocationRead)


async def update(session: AsyncSession, ixp_id: uuid.UUID, location_id: uuid.UUID, data: LocationUpdate) -> Location:
    loc = await get(session, ixp_id, location_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(loc, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("Location name already exists") from exc
    await session.refresh(loc)
    return loc


async def delete(session: AsyncSession, ixp_id: uuid.UUID, location_id: uuid.UUID) -> None:
    loc = await get(session, ixp_id, location_id)
    has_switch = await session.scalar(
        select(Switch.id).where(Switch.location_id == location_id).limit(1)
    )
    if has_switch is not None:
        raise ConflictError("Cannot delete location: switches are assigned to it")
    await session.delete(loc)
    await session.flush()
