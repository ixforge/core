"""Monitoring endpoints: targets for the Collector agent."""

from fastapi import APIRouter

from ixforge.api.deps import DBSession, MonitoringIXPId
from ixforge.schemas.monitoring import MonitoringTargets
from ixforge.services import monitoring as monitoring_svc

monitoring_router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@monitoring_router.get("/targets", response_model=MonitoringTargets)
async def get_monitoring_targets(
    db: DBSession,
    ixp_id: MonitoringIXPId,
) -> MonitoringTargets:
    """Return monitoring targets (switches, ports, member IPs).

    Requires an API key with the ``monitoring:read`` scope.
    """
    return await monitoring_svc.build_targets(db, ixp_id)
