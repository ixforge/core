"""IX-F Member Export public endpoint with rate limiting and caching."""

import time
from typing import Any, cast

from fastapi import APIRouter, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select

from ixforge.api.deps import DBSession
from ixforge.config import get_settings
from ixforge.models.ixp import IXP
from ixforge.services.ixf_export import generate_ixf_member_export

ixf_router = APIRouter(prefix="/ixf", tags=["ix-f"])

limiter = Limiter(key_func=get_remote_address)

# Simple in-memory cache.
_cache: dict[str, Any] = {
    "data": None,
    "expires_at": 0.0,
}

# Cache TTL in seconds (default 5 minutes, configurable).
_CACHE_TTL_SECONDS: int = 300


def _get_cache_ttl() -> int:
    """Return the cache TTL in seconds.

    Reads from settings rate_limit_per_minute as a proxy to keep it simple,
    but defaults to 300 seconds (5 minutes).
    """
    return _CACHE_TTL_SECONDS


def _is_cache_valid() -> bool:
    """Check if the cache is still valid."""
    return _cache["data"] is not None and time.monotonic() < cast("float", _cache["expires_at"])


def _set_cache(data: dict[str, Any]) -> None:
    """Update the cache with new data."""
    _cache["data"] = data
    _cache["expires_at"] = time.monotonic() + _get_cache_ttl()


def _get_cached() -> dict[str, Any] | None:
    """Return cached data if still valid, otherwise None."""
    if _is_cache_valid():
        return cast("dict[str, Any]", _cache["data"])
    return None


@ixf_router.get("/member-export")
@limiter.limit(lambda: f"{get_settings().rate_limit_per_minute}/minute")
async def ixf_member_export(request: Request, db: DBSession) -> dict[str, Any]:
    """Public IX-F Member Export JSON endpoint (schema v1.0).

    Returns the IX-F Member Export JSON for PeeringDB consumption.
    This endpoint is public (no authentication required) and rate-limited.
    Results are cached in memory with a configurable TTL (default 5 minutes).
    """
    # Return cached response if available.
    cached = _get_cached()
    if cached is not None:
        return cached

    # Fetch the first IXP (single-tenant mode).
    stmt = select(IXP).order_by(IXP.created_at).limit(1)
    result = await db.execute(stmt)
    ixp = result.scalar_one_or_none()

    if ixp is None:
        data: dict[str, Any] = {
            "version": "1.0",
            "timestamp": "",
            "ixp_list": [],
        }
        _set_cache(data)
        return data

    data = await generate_ixf_member_export(db, ixp.id)
    _set_cache(data)
    return data
