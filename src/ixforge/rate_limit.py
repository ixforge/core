"""Shared rate limiter instance for SlowAPI and the general limit of the API routes"""

from limits import RateLimitItemPerMinute
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from ixforge.config import get_settings
from ixforge.exceptions import RateLimitedError


def _active_limiter(request: Request) -> Limiter | None:
    """The app limiter, or None when the app runs without rate limiting"""
    active: Limiter | None = getattr(request.app.state, "limiter", None)
    if active is None or not active.enabled:
        return None
    return active


async def enforce_default_rate_limit(request: Request) -> None:
    """General limit of the API routes: per client address and per concrete path

    It runs as a dependency and not as slowapi middleware: since FastAPI includes
    routers lazily, the middleware cannot find the handler of an /api/v1 route
    before routing and skips every one of them
    """
    active = _active_limiter(request)
    if active is None:
        return
    per_minute = get_settings().rate_limit_per_minute
    if not active.limiter.hit(
        RateLimitItemPerMinute(per_minute),
        "default",
        get_remote_address(request),
        request.url.path,
    ):
        raise RateLimitedError(f"Rate limit exceeded: {per_minute} per 1 minute")


# The key is the connection address: forwarding headers come from the client and
# would let anyone pick a fresh key per request. Behind a proxy, uvicorn rewrites
# the address from X-Forwarded-For only for proxies listed in FORWARDED_ALLOW_IPS.
# This instance holds the storage and serves the per route decorators (login,
# IX-F export, /metrics); the general limit is a dependency of the API routers
limiter = Limiter(key_func=get_remote_address)
