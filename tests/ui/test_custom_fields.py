"""Tests for custom fields UI routes."""

import uuid
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from ixforge.ui.api_client import APIError
from ixforge.ui.app import create_ui_app

FAKE_FIELD = {
    "id": str(uuid.uuid4()),
    "entity_type": "member",
    "field_name": "circuit_id",
    "field_type": "string",
    "is_required": False,
    "default_value": None,
    "display_order": 0,
    "description": "ID del circuito",
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


class TestCustomFieldList:
    def test_list_renders(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_FIELD]})
        resp = authed_client.get("/admin/custom-fields")
        assert resp.status_code == 200
        assert "circuit_id" in resp.text

    def test_list_requires_auth(self):
        app = create_ui_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/admin/custom-fields")
        assert resp.status_code == 302

    def test_list_grouped_by_entity_type(self, authed_client, app):
        conn_field = {**FAKE_FIELD, "id": str(uuid.uuid4()), "entity_type": "connection", "field_name": "sla_level"}
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_FIELD, conn_field]})
        resp = authed_client.get("/admin/custom-fields")
        assert resp.status_code == 200
        assert "circuit_id" in resp.text
        assert "sla_level" in resp.text


class TestCustomFieldForm:
    def test_new_form_renders(self, authed_client):
        resp = authed_client.get("/admin/custom-fields/new")
        assert resp.status_code == 200
        assert "entity_type" in resp.text

    def test_create_redirects(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value={**FAKE_FIELD})
        resp = authed_client.post(
            "/admin/custom-fields/new",
            data={
                "entity_type": "member",
                "field_name": "circuit_id",
                "field_type": "string",
                "description": "ID del circuito",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/admin/custom-fields" in resp.headers["location"]

    def test_create_validation_error_shows_form(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(422, {"error": {"code": "VALIDATION_ERROR", "message": "Validation error", "details": [{"msg": "field required"}]}}))
        resp = authed_client.post(
            "/admin/custom-fields/new",
            data={"entity_type": "", "field_name": "", "field_type": "string"},
        )
        assert resp.status_code == 200
        assert "Validation error" in resp.text


class TestCustomFieldEdit:
    def test_edit_redirects(self, authed_client, app):
        app.state.api.patch = AsyncMock(return_value={**FAKE_FIELD})
        resp = authed_client.post(
            f"/admin/custom-fields/{FAKE_FIELD['id']}/edit",
            data={"field_name": "updated_field", "field_type": "integer", "description": "Updated"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/admin/custom-fields" in resp.headers["location"]


class TestCustomFieldDelete:
    def test_delete_redirects(self, authed_client, app):
        app.state.api.delete = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/custom-fields/{FAKE_FIELD['id']}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/admin/custom-fields" in resp.headers["location"]

    def test_delete_error_flashes(self, authed_client, app):
        app.state.api.delete = AsyncMock(side_effect=APIError(409, "Field in use"))
        resp = authed_client.post(
            f"/admin/custom-fields/{FAKE_FIELD['id']}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302
