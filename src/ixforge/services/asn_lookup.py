"""ASN lookup service: member local → DB cache (7-day TTL) → PeeringDB API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import httpx
import structlog
from sqlalchemy import select

from ixforge.models.asn_cache import ASNCache
from ixforge.models.member import Member

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

TTL_HOURS = 7 * 24
_PEERINGDB_URL = "https://www.peeringdb.com/api/network"
_log = structlog.get_logger()


async def lookup(session: AsyncSession, asn: int) -> str | None:
    """Return ASN name. Best-effort: returns None on failure."""
    # 1. Local members (tenant-agnostic: search across all IXPs)
    local = await session.scalar(select(Member.name).where(Member.asn == asn).limit(1))
    if local is not None:
        return local

    # 2. Cache
    cached = await session.get(ASNCache, asn)
    if cached is not None:
        # Handle both timezone-aware and naive datetimes from DB
        fetched_at = cached.fetched_at
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=UTC)
        age = datetime.now(tz=UTC) - fetched_at
        if age < timedelta(hours=TTL_HOURS):
            return cached.name

    # 3. PeeringDB
    name: str | None = None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(_PEERINGDB_URL, params={"asn": asn})
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if data:
                name = data[0].get("name") or None
    except Exception as exc:
        _log.warning("asn_lookup.peeringdb_failed", asn=asn, error=str(exc))
        return None

    if name is None:
        if cached is not None:
            cached.fetched_at = datetime.now(tz=UTC)
            await session.flush()
        return None

    # Update cache
    now = datetime.now(tz=UTC)
    if cached is not None:
        cached.name = name
        cached.fetched_at = now
    else:
        session.add(ASNCache(asn=asn, name=name, fetched_at=now))
    await session.flush()

    return name
