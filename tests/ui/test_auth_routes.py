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

    def test_login_page_always_renders_form(self, client, app):
        """Login page always shows form even if session has token (prevents redirect loops)."""
        app.state.api.login = AsyncMock(return_value="fake-jwt")
        client.post("/login", data={"email": "a@b.com", "password": "p"}, follow_redirects=False)
        resp = client.get("/login", follow_redirects=False)
        assert resp.status_code == 200
        assert "email" in resp.text.lower()


class TestLogout:
    def test_logout_redirects_to_login(self, client):
        resp = client.post("/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"

    def test_logout_clears_session(self, client, app):
        # Login first (don't follow redirect to /admin to avoid real API calls)
        app.state.api.login = AsyncMock(return_value="fake-jwt")
        client.post("/login", data={"email": "a@b.com", "password": "pass"}, follow_redirects=False)
        # Logout (don't follow redirect to /login)
        client.post("/logout", follow_redirects=False)
        # Try accessing admin — should redirect
        resp = client.get("/admin", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"
