"""IXP settings endpoints."""

from fastapi import APIRouter

from ixforge.api.deps import AdminUser, CurrentUser, DBSession, IXPId
from ixforge.exceptions import NotFoundError
from ixforge.models.ixp import IXP
from ixforge.schemas.ixp import IXPRead, IXPUpdate

ixp_router = APIRouter(prefix="/ixp", tags=["ixp"])


@ixp_router.get("", response_model=IXPRead)
async def get_ixp(db: DBSession, ixp_id: IXPId, _user: CurrentUser) -> IXP:
    ixp = await db.get(IXP, ixp_id)
    if ixp is None:
        raise NotFoundError("IXP", str(ixp_id))
    return ixp


@ixp_router.patch("", response_model=IXPRead)
async def update_ixp(body: IXPUpdate, db: DBSession, ixp_id: IXPId, _admin: AdminUser) -> IXP:
    ixp = await db.get(IXP, ixp_id)
    if ixp is None:
        raise NotFoundError("IXP", str(ixp_id))
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(ixp, field, value)
    await db.flush()
    await db.refresh(ixp)
    return ixp
