"""Tests for member portal UI routes."""

import uuid
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from ixforge.ui.app import create_ui_app

FAKE_MEMBER = {
    "id": str(uuid.uuid4()),
    "name": "Acme Networks",
    "short_name": "ACME",
    "asn": 64512,
    "state": "active",
    "peering_policy": "open",
}

MEMBER_ID = str(uuid.uuid4())


@pytest.fixture
def app():
    return create_ui_app()


@pytest.fixture
def member_client(app):
    """Client authenticated as a member user."""
    app.state.api.login = AsyncMock(return_value="member-jwt")
    app.state.api.get = AsyncMock(return_value={"id": "u1", "role": "member", "member_id": MEMBER_ID})
    client = TestClient(app, base_url="https://testserver")
    client.post("/login", data={"email": "m@b.com", "password": "p"}, follow_redirects=False)
    return client


@pytest.fixture
def admin_client(app):
    """Client authenticated as an admin user."""
    app.state.api.login = AsyncMock(return_value="admin-jwt")
    app.state.api.get = AsyncMock(return_value={"id": "u2", "role": "admin", "member_id": None})
    client = TestClient(app, base_url="https://testserver")
    client.post("/login", data={"email": "a@b.com", "password": "p"}, follow_redirects=False)
    return client


@pytest.fixture
def member_no_link_client(app):
    """Client authenticated as member but with member_id=None (not linked)."""
    app.state.api.login = AsyncMock(return_value="member-jwt")
    app.state.api.get = AsyncMock(return_value={"id": "u3", "role": "member", "member_id": None})
    client = TestClient(app, base_url="https://testserver")
    client.post("/login", data={"email": "n@b.com", "password": "p"}, follow_redirects=False)
    return client


class TestPortalDashboard:
    def test_no_auth_redirects_to_login(self, app):
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/portal/dashboard")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"

    def test_admin_redirects_to_admin(self, admin_client):
        resp = admin_client.get("/portal/dashboard", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/admin"

    def test_member_renders_dashboard(self, member_client, app):
        app.state.api.get = AsyncMock(side_effect=[
            FAKE_MEMBER,
            {"items": []},  # connections
            {"items": []},  # bgp-sessions
        ])
        resp = member_client.get("/portal/dashboard")
        assert resp.status_code == 200
        assert "Dashboard" in resp.text

    def test_member_not_linked_shows_not_linked(self, member_no_link_client):
        resp = member_no_link_client.get("/portal/dashboard")
        assert resp.status_code == 200
        assert "no vinculada" in resp.text.lower() or "not_linked" in resp.text.lower()


class TestPortalProfile:
    def test_member_renders_profile(self, member_client, app):
        app.state.api.get = AsyncMock(return_value=FAKE_MEMBER)
        resp = member_client.get("/portal/profile")
        assert resp.status_code == 200

    def test_member_not_linked_shows_not_linked(self, member_no_link_client):
        resp = member_no_link_client.get("/portal/profile")
        assert resp.status_code == 200


class TestPortalConnections:
    def test_member_renders_connections(self, member_client, app):
        app.state.api.get = AsyncMock(return_value={"items": []})
        resp = member_client.get("/portal/connections")
        assert resp.status_code == 200

    def test_no_auth_redirects(self, app):
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/portal/connections")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"


class TestPortalBGPSessions:
    def test_member_renders_bgp_sessions(self, member_client, app):
        app.state.api.get = AsyncMock(return_value={"items": []})
        resp = member_client.get("/portal/bgp-sessions")
        assert resp.status_code == 200


class TestPortalContacts:
    def test_member_renders_contacts(self, member_client, app):
        app.state.api.get = AsyncMock(return_value={"items": []})
        resp = member_client.get("/portal/contacts")
        assert resp.status_code == 200


class TestPortalAccessControl:
    def test_portal_route_with_unknown_role_redirects_to_login(self, app):
        """Session with unknown role (not admin/member) should redirect to login."""
        app.state.api.login = AsyncMock(return_value="fake-jwt")
        app.state.api.get = AsyncMock(return_value={"id": "abc", "role": "superuser", "member_id": None})
        client = TestClient(app, base_url="https://testserver")
        client.post("/login", data={"email": "a@b.com", "password": "p"}, follow_redirects=False)

        resp = client.get("/portal/dashboard", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"

    @pytest.mark.parametrize("path", [
        "/portal/profile",
        "/portal/connections",
        "/portal/bgp-sessions",
        "/portal/contacts",
    ])
    def test_admin_redirected_from_portal_route(self, admin_client, path):
        """Admin accessing any portal route is redirected to /admin."""
        resp = admin_client.get(path, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/admin"


class TestLogoutFromPortal:
    def test_logout_redirects_to_login(self, member_client):
        resp = member_client.post("/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"

    def test_portal_logout_clears_session(self, member_client):
        """After logout, accessing portal route redirects to login."""
        member_client.post("/logout", follow_redirects=False)
        resp = member_client.get("/portal/dashboard", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"].endswith("/login")
