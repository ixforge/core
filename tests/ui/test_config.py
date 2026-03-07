"""Tests for route server config management UI routes."""

import uuid
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from ixforge.ui.api_client import APIError
from ixforge.ui.app import create_ui_app

FAKE_RS = {
    "id": str(uuid.uuid4()),
    "name": "rs1.example.net",
}

FAKE_CONFIG_VERSION = {
    "id": str(uuid.uuid4()),
    "hash": "abc123def",
    "generated_at": "2026-01-15T10:00:00",
    "applied_at": "2026-01-15T10:05:00",
    "generated_by": "admin@example.com",
}


@pytest.fixture
def app():
    app = create_ui_app()
    app.state.api.login = AsyncMock(return_value="test-jwt")
    app.state.api.get = AsyncMock(return_value={"id": "abc", "role": "admin", "member_id": None})
    return app


@pytest.fixture
def authed_client(app):
    client = TestClient(app, base_url="https://testserver")
    client.post("/login", data={"email": "a@b.com", "password": "p"}, follow_redirects=False)
    return client


class TestConfigGenerate:
    def test_generate_redirects(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/route-servers/{FAKE_RS['id']}/config/generate",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"/admin/route-servers/{FAKE_RS['id']}" in resp.headers["location"]

    def test_generate_error_flashes(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(500, "Template error"))
        resp = authed_client.post(
            f"/admin/route-servers/{FAKE_RS['id']}/config/generate",
            follow_redirects=False,
        )
        assert resp.status_code == 302


class TestConfigHistory:
    def test_history_renders(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == f"/api/v1/route-servers/{FAKE_RS['id']}":
                return FAKE_RS
            if path.endswith("/config/history"):
                return {"items": [FAKE_CONFIG_VERSION]}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/route-servers/{FAKE_RS['id']}/config/history")
        assert resp.status_code == 200
        assert "abc123def" in resp.text

    def test_history_404_redirects(self, authed_client, app):
        app.state.api.get = AsyncMock(side_effect=APIError(404))
        resp = authed_client.get(f"/admin/route-servers/{FAKE_RS['id']}/config/history", follow_redirects=False)
        assert resp.status_code == 302


class TestConfigDiff:
    def test_diff_renders(self, authed_client, app):
        from_id = str(uuid.uuid4())
        to_id = str(uuid.uuid4())

        async def fake_get(path, token, params=None):
            if path == f"/api/v1/route-servers/{FAKE_RS['id']}":
                return FAKE_RS
            if path.endswith("/config/diff"):
                return {"diff": "+added line\n-removed line", "from": from_id, "to": to_id}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(
            f"/admin/route-servers/{FAKE_RS['id']}/config/diff?from={from_id}&to={to_id}"
        )
        assert resp.status_code == 200
        assert "Diff" in resp.text
