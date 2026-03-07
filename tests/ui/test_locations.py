"""Tests for locations UI routes."""

import uuid
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from ixforge.ui.api_client import APIError
from ixforge.ui.app import create_ui_app

FAKE_LOCATION = {
    "id": str(uuid.uuid4()),
    "ixp_id": str(uuid.uuid4()),
    "name": "Datacenter Buenos Aires",
    "city": "Buenos Aires",
    "country": "AR",
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-01-01T00:00:00",
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


class TestLocationList:
    def test_list_renders(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_LOCATION]})
        resp = authed_client.get("/admin/locations")
        assert resp.status_code == 200
        assert "Datacenter Buenos Aires" in resp.text

    def test_list_requires_auth(self):
        app = create_ui_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/admin/locations")
        assert resp.status_code == 302

    def test_list_empty(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"items": []})
        resp = authed_client.get("/admin/locations")
        assert resp.status_code == 200


class TestLocationNew:
    def test_new_form_renders(self, authed_client):
        resp = authed_client.get("/admin/locations/new")
        assert resp.status_code == 200
        assert "name" in resp.text.lower()

    def test_create_redirects(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value={**FAKE_LOCATION})
        resp = authed_client.post(
            "/admin/locations/new",
            data={"name": "Datacenter Buenos Aires", "city": "Buenos Aires", "country": "AR"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/admin/locations" in resp.headers["location"]

    def test_create_validation_error_shows_form(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(422, {"detail": [{"msg": "required"}]}))
        resp = authed_client.post(
            "/admin/locations/new",
            data={"name": "", "city": "", "country": ""},
        )
        assert resp.status_code == 200

    def test_create_conflict_shows_form(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(409, "Nombre duplicado"))
        resp = authed_client.post(
            "/admin/locations/new",
            data={"name": "Duplicated", "city": "", "country": ""},
        )
        assert resp.status_code == 200


class TestLocationEdit:
    def test_edit_form_renders(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value=FAKE_LOCATION)
        resp = authed_client.get(f"/admin/locations/{FAKE_LOCATION['id']}/edit")
        assert resp.status_code == 200
        assert "Datacenter Buenos Aires" in resp.text

    def test_edit_submit_redirects(self, authed_client, app):
        app.state.api.patch = AsyncMock(return_value={**FAKE_LOCATION})
        resp = authed_client.post(
            f"/admin/locations/{FAKE_LOCATION['id']}/edit",
            data={"name": "Updated Location", "city": "Mendoza", "country": "AR"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/admin/locations" in resp.headers["location"]

    def test_edit_validation_error_shows_form(self, authed_client, app):
        app.state.api.patch = AsyncMock(side_effect=APIError(422, {"detail": [{"msg": "required"}]}))
        resp = authed_client.post(
            f"/admin/locations/{FAKE_LOCATION['id']}/edit",
            data={"name": ""},
        )
        assert resp.status_code == 200


class TestLocationDelete:
    def test_delete_redirects(self, authed_client, app):
        app.state.api.delete = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/locations/{FAKE_LOCATION['id']}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/admin/locations" in resp.headers["location"]

    def test_delete_error_flashes(self, authed_client, app):
        app.state.api.delete = AsyncMock(side_effect=APIError(409, "Location en uso"))
        resp = authed_client.post(
            f"/admin/locations/{FAKE_LOCATION['id']}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302
