"""Tests for login/logout routes."""

from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from ixforge.ui.api_client import AuthenticationError
from ixforge.ui.app import create_ui_app


@pytest.fixture
def app():
    return create_ui_app()


@pytest.fixture
def client(app):
    # Use https so secure session cookies are sent back (https_only=True in production mode)
    return TestClient(app, base_url="https://testserver")


class TestLogin:
    def test_login_page_renders(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert "email" in resp.text.lower()

    def test_login_success_redirects_to_admin(self, client, app):
        app.state.api.login = AsyncMock(return_value="fake-jwt-token")
        app.state.api.get = AsyncMock(return_value={"id": "abc", "role": "admin", "member_id": None})
        resp = client.post(
            "/login",
            data={"email": "admin@test.com", "password": "pass123"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["location"] == "/admin"

    def test_login_failure_shows_error(self, client, app):
        app.state.api.login = AsyncMock(side_effect=AuthenticationError())
        resp = client.post(
            "/login",
            data={"email": "bad@test.com", "password": "wrong"},
        )
        assert resp.status_code == 200
        assert "incorrectos" in resp.text.lower()

    def test_login_empty_fields_shows_error(self, client):
        resp = client.post("/login", data={"email": "", "password": ""})
        assert resp.status_code == 200
        assert "requeridos" in resp.text.lower()

    def test_login_redirects_member_to_portal(self, client, app):
        app.state.api.login = AsyncMock(return_value="fake-jwt-token")
        app.state.api.get = AsyncMock(return_value={"id": "abc", "role": "member", "member_id": "some-uuid"})
        resp = client.post(
            "/login",
            data={"email": "member@test.com", "password": "pass123"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["location"] == "/portal/dashboard"

    def test_login_page_always_renders_form(self, client, app):
        """Login page always shows form even if session has token (prevents redirect loops)."""
        app.state.api.login = AsyncMock(return_value="fake-jwt")
        app.state.api.get = AsyncMock(return_value={"id": "abc", "role": "admin", "member_id": None})
        client.post("/login", data={"email": "a@b.com", "password": "p"}, follow_redirects=False)
        resp = client.get("/login", follow_redirects=False)
        assert resp.status_code == 200
        assert "email" in resp.text.lower()

    def test_login_clears_previous_session(self, client, app):
        """Re-login clears previous session data so old role/member_id don't persist."""
        # Login as member first
        app.state.api.login = AsyncMock(return_value="member-jwt")
        app.state.api.get = AsyncMock(return_value={"id": "u1", "role": "member", "member_id": "mid-1"})
        client.post("/login", data={"email": "m@b.com", "password": "p"}, follow_redirects=False)

        # Login as admin (different user)
        app.state.api.login = AsyncMock(return_value="admin-jwt")
        app.state.api.get = AsyncMock(return_value={"id": "u2", "role": "admin", "member_id": None})
        resp = client.post(
            "/login", data={"email": "a@b.com", "password": "p"}, follow_redirects=False
        )
        assert resp.status_code == 302
        assert resp.headers["location"] == "/admin"

        # Access admin area - should work, not redirect to portal
        app.state.api.get = AsyncMock(return_value={"items": []})
        resp = client.get("/admin", follow_redirects=False)
        assert resp.status_code != 302 or resp.headers.get("location") != "/portal/dashboard"

    def test_login_fails_if_role_missing_in_me_response(self, client, app):
        """If /users/me does not return role, login fails with error on login page."""
        app.state.api.login = AsyncMock(return_value="fake-jwt")
        app.state.api.get = AsyncMock(return_value={"id": "abc", "member_id": None})
        resp = client.post(
            "/login",
            data={"email": "user@test.com", "password": "pass123"},
            follow_redirects=False,
        )
        # Should render login page with error, not redirect
        assert resp.status_code == 200
        assert "error al obtener datos del usuario" in resp.text.lower()


class TestAdminAccessControl:
    def test_admin_route_with_unknown_role_redirects_to_login(self, app):
        """Session with unknown role (not admin/member) should redirect to login."""
        app.state.api.login = AsyncMock(return_value="fake-jwt")
        # Login with a valid role first, then tamper the session
        app.state.api.get = AsyncMock(return_value={"id": "abc", "role": "admin", "member_id": None})
        client = TestClient(app, base_url="https://testserver")
        client.post("/login", data={"email": "a@b.com", "password": "p"}, follow_redirects=False)

        # Tamper session: set an unknown role via a direct session manipulation
        # We need to go through the session middleware, so we inject via a login with mocked role
        app.state.api.login = AsyncMock(return_value="fake-jwt")
        app.state.api.get = AsyncMock(return_value={"id": "abc", "role": "superuser", "member_id": None})
        client.post("/login", data={"email": "a@b.com", "password": "p"}, follow_redirects=False)

        resp = client.get("/admin", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"


class TestLogout:
    def test_logout_redirects_to_login(self, client):
        resp = client.post("/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"

    def test_logout_clears_session(self, client, app):
        # Login first (don't follow redirect to /admin to avoid real API calls)
        app.state.api.login = AsyncMock(return_value="fake-jwt")
        app.state.api.get = AsyncMock(return_value={"id": "abc", "role": "admin", "member_id": None})
        client.post("/login", data={"email": "a@b.com", "password": "pass"}, follow_redirects=False)
        # Logout (don't follow redirect to /login)
        client.post("/logout", follow_redirects=False)
        # Try accessing admin — should redirect
        resp = client.get("/admin", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"
