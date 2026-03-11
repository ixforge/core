"""Tests for switches UI routes."""

import uuid
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from ixforge.ui.api_client import APIError
from ixforge.ui.app import create_ui_app

FAKE_SWITCH = {
    "id": str(uuid.uuid4()),
    "ixp_id": str(uuid.uuid4()),
    "name": "switch-01",
    "vendor": "Arista",
    "model": "DCS-7280SR",
    "management_ip": "10.0.0.1",
    "is_active": True,
    "extra_data": None,
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-01-01T00:00:00",
}

FAKE_PORT = {
    "id": str(uuid.uuid4()),
    "switch_id": FAKE_SWITCH["id"],
    "name": "eth1",
    "speed": 10000,
    "type": "access",
    "is_active": True,
    "connection_id": None,
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


class TestSwitchesList:
    def test_list_renders(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={
            "items": [FAKE_SWITCH],
        })
        resp = authed_client.get("/admin/switches")
        assert resp.status_code == 200
        assert "switch-01" in resp.text

    def test_list_requires_auth(self):
        app = create_ui_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/admin/switches")
        assert resp.status_code == 302

    def test_list_empty_shows_empty_state(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"items": []})
        resp = authed_client.get("/admin/switches")
        assert resp.status_code == 200

    def test_list_filter_by_is_active(self, authed_client, app):
        inactive = {**FAKE_SWITCH, "id": str(uuid.uuid4()), "name": "sw-inactive", "is_active": False}
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_SWITCH, inactive]})
        resp = authed_client.get("/admin/switches?is_active=true")
        assert resp.status_code == 200
        assert "switch-01" in resp.text
        assert "sw-inactive" not in resp.text


class TestSwitchDetail:
    def test_detail_renders(self, authed_client, app):
        app.state.api.get = AsyncMock(side_effect=[
            FAKE_SWITCH,
            {"items": [FAKE_PORT]},
        ])
        resp = authed_client.get(f"/admin/switches/{FAKE_SWITCH['id']}")
        assert resp.status_code == 200
        assert "switch-01" in resp.text
        assert "Arista" in resp.text
        assert "DCS-7280SR" in resp.text
        assert "eth1" in resp.text

    def test_detail_renders_empty_ports(self, authed_client, app):
        app.state.api.get = AsyncMock(side_effect=[
            FAKE_SWITCH,
            {"items": []},
        ])
        resp = authed_client.get(f"/admin/switches/{FAKE_SWITCH['id']}")
        assert resp.status_code == 200
        assert "switch-01" in resp.text

    def test_detail_404_redirects(self, authed_client, app):
        app.state.api.get = AsyncMock(side_effect=APIError(404))
        resp = authed_client.get(f"/admin/switches/{uuid.uuid4()}", follow_redirects=False)
        assert resp.status_code == 302


class TestSwitchForm:
    def test_new_form_renders(self, authed_client):
        resp = authed_client.get("/admin/switches/new")
        assert resp.status_code == 200
        assert "name" in resp.text.lower()

    def test_create_redirects(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value={**FAKE_SWITCH})
        resp = authed_client.post(
            "/admin/switches/new",
            data={
                "name": "switch-01",
                "vendor": "Arista",
                "model": "DCS-7280SR",
                "management_ip": "10.0.0.1",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"/admin/switches/{FAKE_SWITCH['id']}" in resp.headers["location"]

    def test_create_validation_error_shows_form(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(422, {"detail": [{"msg": "field required"}]}))
        resp = authed_client.post(
            "/admin/switches/new",
            data={"name": "", "vendor": "", "model": "", "management_ip": ""},
        )
        assert resp.status_code == 200
        assert "Corrige los errores" in resp.text

    def test_edit_form_renders(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value=FAKE_SWITCH)
        resp = authed_client.get(f"/admin/switches/{FAKE_SWITCH['id']}/edit")
        assert resp.status_code == 200
        assert "switch-01" in resp.text
        assert "Arista" in resp.text

    def test_edit_submit_redirects(self, authed_client, app):
        app.state.api.patch = AsyncMock(return_value={**FAKE_SWITCH})
        resp = authed_client.post(
            f"/admin/switches/{FAKE_SWITCH['id']}/edit",
            data={"name": "switch-01-updated", "vendor": "Cisco"},
            follow_redirects=False,
        )
        assert resp.status_code == 302


class TestSwitchDelete:
    def test_delete_redirects(self, authed_client, app):
        app.state.api.delete = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/switches/{FAKE_SWITCH['id']}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/admin/switches" in resp.headers["location"]

    def test_delete_error_flashes(self, authed_client, app):
        app.state.api.delete = AsyncMock(side_effect=APIError(409, "Switch in use"))
        resp = authed_client.post(
            f"/admin/switches/{FAKE_SWITCH['id']}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302
