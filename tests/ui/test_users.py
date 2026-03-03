"""Tests for users UI routes."""

import uuid
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from ixforge.ui.api_client import APIError
from ixforge.ui.app import create_ui_app

FAKE_USER = {
    "id": str(uuid.uuid4()),
    "email": "admin@example.com",
    "role": "admin",
    "is_active": True,
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-01-01T00:00:00",
}

FAKE_API_KEY = {
    "id": str(uuid.uuid4()),
    "prefix": "ixf_abc",
    "name": "ci-deploy",
    "scopes": ["read", "write"],
    "last_used": None,
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


class TestUserList:
    def test_list_renders(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_USER]})
        resp = authed_client.get("/admin/users")
        assert resp.status_code == 200
        assert "admin@example.com" in resp.text

    def test_list_requires_auth(self):
        app = create_ui_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/admin/users")
        assert resp.status_code == 302


class TestUserDetail:
    def test_detail_renders(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == f"/api/v1/users/{FAKE_USER['id']}":
                return FAKE_USER
            if path == f"/api/v1/users/{FAKE_USER['id']}/api-keys":
                return {"items": [FAKE_API_KEY]}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/users/{FAKE_USER['id']}")
        assert resp.status_code == 200
        assert "admin@example.com" in resp.text
        assert "ci-deploy" in resp.text

    def test_detail_404_redirects(self, authed_client, app):
        app.state.api.get = AsyncMock(side_effect=APIError(404))
        resp = authed_client.get(f"/admin/users/{uuid.uuid4()}", follow_redirects=False)
        assert resp.status_code == 302


class TestUserForm:
    def test_new_form_renders(self, authed_client):
        resp = authed_client.get("/admin/users/new")
        assert resp.status_code == 200
        assert "email" in resp.text.lower()

    def test_new_form_has_full_name_field(self, authed_client):
        resp = authed_client.get("/admin/users/new")
        assert resp.status_code == 200
        assert 'name="full_name"' in resp.text

    def test_new_form_has_correct_roles(self, authed_client):
        resp = authed_client.get("/admin/users/new")
        assert 'value="member"' in resp.text
        assert 'value="admin"' in resp.text
        assert 'value="operator"' not in resp.text
        assert 'value="viewer"' not in resp.text

    def test_create_redirects(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value={**FAKE_USER})
        resp = authed_client.post(
            "/admin/users/new",
            data={
                "full_name": "Test User",
                "email": "new@example.com",
                "password": "secret123",
                "role": "admin",
                "is_active": "on",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"/admin/users/{FAKE_USER['id']}" in resp.headers["location"]

    def test_create_validation_error_shows_form(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(422, {"detail": [{"msg": "invalid email"}]}))
        resp = authed_client.post(
            "/admin/users/new",
            data={"email": "", "password": "", "role": "admin"},
        )
        assert resp.status_code == 200
        assert "Corrige los errores" in resp.text


class TestUserEdit:
    def test_edit_redirects(self, authed_client, app):
        app.state.api.patch = AsyncMock(return_value={**FAKE_USER})
        resp = authed_client.post(
            f"/admin/users/{FAKE_USER['id']}/edit",
            data={"role": "member", "is_active": "on"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        app.state.api.patch.assert_called_once_with(
            f"/api/v1/users/{FAKE_USER['id']}",
            "test-jwt",
            json={"role": "member", "is_active": True},
        )


class TestUserAPIKeys:
    def test_create_api_key_redirects(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value={"raw_key": "ixf_secret_key_123", **FAKE_API_KEY})
        resp = authed_client.post(
            f"/admin/users/{FAKE_USER['id']}/api-keys",
            data={"name": "ci-deploy"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"/admin/users/{FAKE_USER['id']}" in resp.headers["location"]
        # Key should NOT be in URL (security)
        assert "ixf_secret_key_123" not in resp.headers["location"]

    def test_create_api_key_error_flashes(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(400, "Too many keys"))
        resp = authed_client.post(
            f"/admin/users/{FAKE_USER['id']}/api-keys",
            data={"name": "test"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
