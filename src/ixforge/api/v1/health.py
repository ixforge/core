"""Health check endpoint."""

from typing import Any

from fastapi import APIRouter, Response
from sqlalchemy import text

from ixforge.api.deps import DBSession

health_router = APIRouter(tags=["system"])


@health_router.get("/health")
async def health(response: Response, db: DBSession) -> dict[str, Any]:
    checks: dict[str, dict[str, str]] = {}
    overall_healthy = True

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as exc:
        checks["database"] = {"status": "error", "detail": str(exc)}
        overall_healthy = False

    # Task queue check (will be enhanced in Stage 12)
    checks["task_queue"] = {"status": "ok"}

    if not overall_healthy:
        response.status_code = 503

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "version": "0.1.0",
        "checks": checks,
    }
