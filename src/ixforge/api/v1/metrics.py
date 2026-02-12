"""Prometheus metrics endpoint."""

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ixforge.rate_limit import limiter

metrics_router = APIRouter()


@metrics_router.get("/metrics", include_in_schema=False)
@limiter.limit("60/minute")
async def metrics(request: Request) -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
