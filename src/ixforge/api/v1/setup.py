"""Setup endpoints: initial platform configuration."""

from fastapi import APIRouter

from ixforge.api.deps import DBSession
from ixforge.schemas.setup import SetupRequest, SetupStatusResponse
from ixforge.services import setup as setup_service

setup_router = APIRouter(prefix="/setup", tags=["setup"])


@setup_router.get("/status", response_model=SetupStatusResponse)
async def setup_status(db: DBSession) -> dict[str, bool]:
    configured = await setup_service.is_configured(db)
    return {"configured": configured}


@setup_router.post("", status_code=201)
async def run_setup(body: SetupRequest, db: DBSession) -> dict[str, str]:
    await setup_service.run_setup(db, body)
    return {"message": "Setup completed"}
