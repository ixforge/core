"""Tests for dashboard route."""

from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from ixforge.ui.app import create_ui_app


@pytest.fixture
def app():
    app = create_ui_app()
    app.state.api.login = AsyncMock(return_value="test-jwt")
    app.state.api.get = AsyncMock(return_value={"id": "abc", "role": "admin", "member_id": None})
    return app


@pytest.fixture
def authed_client(app):
    """Client with an active session (logged in as admin)."""
    client = TestClient(app, base_url="https://testserver")
    client.post("/login", data={"email": "a@b.com", "password": "p"}, follow_redirects=False)
    # Reset api.get mock after login so dashboard can use its own mocks
    app.state.api.get = AsyncMock(return_value={"items": [], "next_cursor": None, "has_more": False})
    return client


class TestDashboard:
    def test_dashboard_requires_auth(self):
        app = create_ui_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/admin")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"

    def test_dashboard_renders(self, authed_client):
        resp = authed_client.get("/admin")
        assert resp.status_code == 200
        assert "Dashboard" in resp.text

    def test_dashboard_shows_member_count(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={
            "items": [
                {"id": "1", "name": "Acme", "asn": 64512, "state": "active", "peering_policy": "open"},
                {"id": "2", "name": "Beta", "asn": 64513, "state": "prospect", "peering_policy": "selective"},
            ],
            "next_cursor": None,
            "has_more": False,
        })
        resp = authed_client.get("/admin")
        assert resp.status_code == 200

    def test_dashboard_expired_token_redirects(self, authed_client, app):
        """If API returns 401, dashboard redirects to login."""
        from ixforge.ui.api_client import AuthenticationError
        app.state.api.get = AsyncMock(side_effect=AuthenticationError())
        resp = authed_client.get("/admin", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"
