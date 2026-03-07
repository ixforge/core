"""Tests for ASN lookup service."""

import httpx
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from ixforge.enums import MemberState
from ixforge.models.asn_cache import ASNCache
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.services.asn_lookup import lookup


class TestASNLookup:
    async def test_lookup_from_local_member(self, db_session, ixp: IXP) -> None:
        m = Member(ixp_id=ixp.id, name="Local ISP", short_name="L", asn=65300, state=MemberState.active)
        db_session.add(m)
        await db_session.flush()
        name = await lookup(db_session, 65300)
        assert name == "Local ISP"

    async def test_lookup_from_cache(self, db_session) -> None:
        cache_entry = ASNCache(asn=64512, name="Cached AS", fetched_at=datetime.now(tz=timezone.utc))
        db_session.add(cache_entry)
        await db_session.flush()
        name = await lookup(db_session, 64512)
        assert name == "Cached AS"

    async def test_lookup_expired_cache_hits_peeringdb(self, db_session) -> None:
        old_time = datetime.now(tz=timezone.utc) - timedelta(days=8)
        cache_entry = ASNCache(asn=64513, name="Old Name", fetched_at=old_time)
        db_session.add(cache_entry)
        await db_session.flush()

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"data": [{"name": "Fresh Name"}]}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            name = await lookup(db_session, 64513)
        assert name == "Fresh Name"
        await db_session.refresh(cache_entry)
        assert cache_entry.name == "Fresh Name"
        assert cache_entry.fetched_at > old_time

    async def test_lookup_peeringdb_failure_returns_none(self, db_session) -> None:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.TimeoutException("timeout")):
            name = await lookup(db_session, 99999)
        assert name is None

    async def test_lookup_no_local_no_cache_no_peeringdb_returns_none(self, db_session) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"data": []}
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            name = await lookup(db_session, 11111)
        assert name is None

    async def test_lookup_expired_cache_no_peeringdb_result_resets_fetched_at(self, db_session) -> None:
        """Stale cache entry with no PeeringDB data must have fetched_at reset to avoid hammering the API."""
        old_time = datetime.now(tz=timezone.utc) - timedelta(days=8)
        cache_entry = ASNCache(asn=64520, name="Old Name", fetched_at=old_time)
        db_session.add(cache_entry)
        await db_session.flush()

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"data": []}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            name = await lookup(db_session, 64520)

        assert name is None
        await db_session.refresh(cache_entry)
        assert cache_entry.fetched_at > old_time
