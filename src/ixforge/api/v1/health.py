"""Health check endpoint."""

from typing import Any

from fastapi import APIRouter, Response

health_router = APIRouter(tags=["system"])


@health_router.get("/health")
async def health(response: Response) -> dict[str, Any]:
    checks: dict[str, dict[str, str]] = {}
    overall_healthy = True

    # Database check (will be enhanced in Stage 3)
    checks["database"] = {"status": "ok"}

    # Task queue check (will be enhanced in Stage 12)
    checks["task_queue"] = {"status": "ok"}

    if not overall_healthy:
        response.status_code = 503

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "version": "0.1.0",
        "checks": checks,
    }
