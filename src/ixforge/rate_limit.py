"""Shared rate limiter instance for SlowAPI."""

from slowapi import Limiter
from slowapi.util import get_remote_address

from ixforge.config import get_settings


def _dynamic_limit() -> str:
    settings = get_settings()
    return f"{settings.rate_limit_per_minute}/minute"


# The key is the connection address: forwarding headers come from the client and
# would let anyone pick a fresh key per request. Behind a proxy, uvicorn rewrites
# the address from X-Forwarded-For only for proxies listed in FORWARDED_ALLOW_IPS
limiter = Limiter(key_func=get_remote_address, default_limits=[_dynamic_limit])
