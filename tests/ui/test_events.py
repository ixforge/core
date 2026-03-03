"""Tests for events UI routes."""

from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from ixforge.ui.app import create_ui_app

FAKE_EVENT = {
    "id": "evt-001",
    "type": "member.created",
    "resource_type": "member",
    "resource_id": "mem-001",
    "actor_id": "usr-001",
    "data": {"name": "Acme Networks"},
    "created_at": "2026-01-15T10:00:00",
}


@pytest.fixture
def app():
    app = create_ui_app()
    app.state.api.login = AsyncMock(return_value="test-jwt")
    return app


@pytest.fixture
def authed_client(app):
    client = TestClient(app, base_url="https://testserver")
    client.post("/login", data={"email": "a@b.com", "password": "p"}, follow_redirects=False)
    return client


class TestEventList:
    def test_list_renders(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={
            "items": [FAKE_EVENT], "next_cursor": None, "has_more": False,
        })
        resp = authed_client.get("/admin/events")
        assert resp.status_code == 200
        assert "Eventos" in resp.text
        assert "member.created" in resp.text

    def test_list_requires_auth(self):
        app = create_ui_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/admin/events")
        assert resp.status_code == 302

    def test_list_filter_by_resource_type(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={
            "items": [FAKE_EVENT], "next_cursor": None, "has_more": False,
        })
        resp = authed_client.get("/admin/events?resource_type=member")
        assert resp.status_code == 200
        # Verify the API was called with the filter
        call_args = app.state.api.get.call_args
        assert call_args[1].get("params", call_args[0][2] if len(call_args[0]) > 2 else {}).get("resource_type") == "member"

    def test_list_htmx_returns_partial(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={
            "items": [FAKE_EVENT], "next_cursor": None, "has_more": False,
        })
        resp = authed_client.get("/admin/events", headers={"hx-request": "true"})
        assert resp.status_code == 200
        assert "<!DOCTYPE html>" not in resp.text
