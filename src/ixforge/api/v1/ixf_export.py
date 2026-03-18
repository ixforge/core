"""IX-F Member Export public endpoint with rate limiting and caching."""

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select

from ixforge.api.deps import DBSession
from ixforge.config import get_settings
from ixforge.database import tenant_context
from ixforge.models.ixp import IXP
from ixforge.rate_limit import limiter
from ixforge.services.ixf_export import generate_ixf_member_export

ixf_router = APIRouter(prefix="/ixf", tags=["ix-f"])

# In-memory cache protected by a lock to prevent thundering herd
_cache: tuple[dict[str, Any] | None, float] = (None, 0.0)
_cache_lock = asyncio.Lock()
_CACHE_TTL_SECONDS: int = 300


def _is_cache_valid() -> bool:
    """Check if the cache is still valid"""
    return _cache[0] is not None and time.monotonic() < _cache[1]


def _set_cache(data: dict[str, Any]) -> None:
    """Update the cache with new data"""
    global _cache
    _cache = (data, time.monotonic() + _CACHE_TTL_SECONDS)


def _get_cached() -> dict[str, Any] | None:
    """Return cached data if still valid, otherwise None"""
    if _is_cache_valid():
        return _cache[0]
    return None


@ixf_router.get("/member-export")
@limiter.limit(lambda: f"{get_settings().rate_limit_per_minute}/minute")
async def ixf_member_export(request: Request, db: DBSession) -> dict[str, Any]:
    """Public IX-F Member Export JSON endpoint (schema v1.0)

    Returns the IX-F Member Export JSON for PeeringDB consumption.
    This endpoint is public (no authentication required) and rate-limited.
    Results are cached in memory with a configurable TTL (default 5 minutes).
    """
    cached = _get_cached()
    if cached is not None:
        return cached

    async with _cache_lock:
        # Double-check after acquiring the lock
        cached = _get_cached()
        if cached is not None:
            return cached

        stmt = select(IXP).order_by(IXP.created_at).limit(1)
        result = await db.execute(stmt)
        ixp = result.scalar_one_or_none()

        if ixp is None:
            data: dict[str, Any] = {
                "version": "1.0",
                "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "ixp_list": [],
                "member_list": [],
            }
            _set_cache(data)
            return data

        tenant_context.set(ixp.id)
        data = await generate_ixf_member_export(db, ixp.id)
        _set_cache(data)
        return data
