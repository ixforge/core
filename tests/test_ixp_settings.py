"""Tests for IXP settings endpoints."""

import pytest
from httpx import AsyncClient

from ixforge.models.ixp import IXP


class TestIXPSettingsAPI:
    async def test_get_ixp(self, client: AsyncClient, ixp: IXP, auth_headers: dict) -> None:
        resp = await client.get("/api/v1/ixp", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["short_name"] == ixp.short_name
        assert data["asn"] == ixp.asn

    async def test_patch_ixp_updates_name(self, client: AsyncClient, ixp: IXP, auth_headers: dict) -> None:
        resp = await client.patch("/api/v1/ixp", json={"name": "Updated IXP"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated IXP"

    async def test_patch_ixp_cannot_change_short_name(self, client: AsyncClient, ixp: IXP, auth_headers: dict) -> None:
        # short_name is not in IXPUpdate so it is silently ignored
        resp = await client.patch("/api/v1/ixp", json={"short_name": "CHANGED"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["short_name"] == ixp.short_name

    async def test_patch_ixp_requires_admin(self, client: AsyncClient, ixp: IXP, member_auth_headers: dict) -> None:
        resp = await client.patch("/api/v1/ixp", json={"name": "X"}, headers=member_auth_headers)
        assert resp.status_code == 403
