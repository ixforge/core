"""Shared rate limiter instance for SlowAPI."""

from slowapi import Limiter
from slowapi.util import get_ipaddr

from ixforge.config import get_settings


def _dynamic_limit() -> str:
    settings = get_settings()
    return f"{settings.rate_limit_per_minute}/minute"


limiter = Limiter(key_func=get_ipaddr, default_limits=[_dynamic_limit])
