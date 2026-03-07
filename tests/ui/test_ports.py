"""Tests for ports UI routes."""

import uuid
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from ixforge.ui.api_client import APIError
from ixforge.ui.app import create_ui_app

FAKE_SWITCH = {
    "id": str(uuid.uuid4()),
    "name": "sw-core-01",
    "hostname": "sw-core-01.demo.net",
    "vendor": "Arista",
    "model": "DCS-7280SR",
    "management_ip": "10.0.0.1",
    "is_active": True,
    "extra_data": None,
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-01-01T00:00:00",
}

FAKE_MEMBER = {
    "id": str(uuid.uuid4()),
    "name": "Acme Networks",
    "short_name": "ACME",
    "asn": 64512,
    "state": "active",
}

FAKE_PORT = {
    "id": str(uuid.uuid4()),
    "switch_id": FAKE_SWITCH["id"],
    "name": "Ethernet1",
    "speed": 10000,
    "type": "member",
    "member_id": None,
    "is_active": True,
    "extra_data": None,
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


class TestPortOptions:
    def test_options_returns_html_options(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == "/api/v1/ports":
                return {"items": [FAKE_PORT]}
            return {"items": []}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/ports/options?switch_id={FAKE_SWITCH['id']}")
        assert resp.status_code == 200
        assert "Sin puerto" in resp.text
        assert FAKE_PORT["id"] in resp.text
        assert "Ethernet1" in resp.text

    def test_options_no_switch_returns_default(self, authed_client, app):
        resp = authed_client.get("/admin/ports/options")
        assert resp.status_code == 200
        assert "Sin puerto" in resp.text
        assert "<option" in resp.text

    def test_options_requires_auth(self):
        app = create_ui_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/admin/ports/options")
        assert resp.status_code == 302


class TestPortList:
    def test_list_renders(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == "/api/v1/switches":
                return {"items": [FAKE_SWITCH]}
            if path == f"/api/v1/switches/{FAKE_SWITCH['id']}":
                return FAKE_SWITCH
            if path == "/api/v1/ports":
                return {"items": [FAKE_PORT]}
            if path == "/api/v1/members":
                return {"items": [FAKE_MEMBER]}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/ports?switch_id={FAKE_SWITCH['id']}")
        assert resp.status_code == 200
        assert "Ethernet1" in resp.text

    def test_list_requires_auth(self):
        app = create_ui_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/admin/ports")
        assert resp.status_code == 302

    def test_list_no_switch_shows_prompt(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_SWITCH]})

        async def fake_get(path, token, params=None):
            if path == "/api/v1/switches":
                return {"items": [FAKE_SWITCH]}
            if path == "/api/v1/members":
                return {"items": [FAKE_MEMBER]}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get("/admin/ports")
        assert resp.status_code == 200
        assert "Selecciona un switch" in resp.text

    def test_list_empty_shows_empty_state(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == "/api/v1/switches":
                return {"items": [FAKE_SWITCH]}
            if path == f"/api/v1/switches/{FAKE_SWITCH['id']}":
                return FAKE_SWITCH
            if path == "/api/v1/ports":
                return {"items": []}
            if path == "/api/v1/members":
                return {"items": []}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/ports?switch_id={FAKE_SWITCH['id']}")
        assert resp.status_code == 200


class TestPortForm:
    def test_new_form_renders(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_SWITCH]})
        resp = authed_client.get("/admin/ports/new")
        assert resp.status_code == 200
        assert "name" in resp.text.lower()
        assert "speed" in resp.text.lower()

    def test_new_form_preselects_switch(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_SWITCH]})
        resp = authed_client.get(f"/admin/ports/new?switch_id={FAKE_SWITCH['id']}")
        assert resp.status_code == 200
        assert FAKE_SWITCH["id"] in resp.text

    def test_create_redirects(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_SWITCH]})
        app.state.api.post = AsyncMock(return_value={**FAKE_PORT})
        resp = authed_client.post(
            "/admin/ports/new",
            data={
                "switch_id": FAKE_SWITCH["id"],
                "name": "Ethernet1",
                "speed": "10000",
                "type": "member",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "switch_id" in resp.headers["location"]

    def test_create_validation_error_shows_form(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_SWITCH]})
        app.state.api.post = AsyncMock(side_effect=APIError(422, {"detail": [{"msg": "field required"}]}))
        resp = authed_client.post(
            "/admin/ports/new",
            data={"switch_id": "", "name": "", "speed": "0", "type": "unused"},
        )
        assert resp.status_code == 200
        assert "Corrige los errores" in resp.text

    def test_edit_form_renders(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path.startswith("/api/v1/ports/"):
                return FAKE_PORT
            if path == "/api/v1/switches":
                return {"items": [FAKE_SWITCH]}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/ports/{FAKE_PORT['id']}/edit")
        assert resp.status_code == 200
        assert "Ethernet1" in resp.text

    def test_edit_submit_redirects(self, authed_client, app):
        app.state.api.patch = AsyncMock(return_value={**FAKE_PORT})
        resp = authed_client.post(
            f"/admin/ports/{FAKE_PORT['id']}/edit",
            data={"name": "Ethernet1-updated", "speed": "10000", "type": "infra"},
            follow_redirects=False,
        )
        assert resp.status_code == 302


class TestPortDelete:
    def test_delete_redirects(self, authed_client, app):
        app.state.api.delete = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/ports/{FAKE_PORT['id']}/delete",
            data={"switch_id": FAKE_SWITCH["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"switch_id={FAKE_SWITCH['id']}" in resp.headers["location"]

    def test_delete_error_flashes(self, authed_client, app):
        app.state.api.delete = AsyncMock(side_effect=APIError(409, "Puerto en uso"))
        resp = authed_client.post(
            f"/admin/ports/{FAKE_PORT['id']}/delete",
            data={"switch_id": FAKE_SWITCH["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 302


class TestPortAssignRelease:
    def test_assign_works(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/ports/{FAKE_PORT['id']}/assign",
            data={"member_id": FAKE_MEMBER["id"], "switch_id": FAKE_SWITCH["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        app.state.api.post.assert_called_once_with(
            f"/api/v1/ports/{FAKE_PORT['id']}/assign",
            "test-jwt",
            json={"member_id": FAKE_MEMBER["id"]},
        )

    def test_assign_error_flashes(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(400, "Puerto ya asignado"))
        resp = authed_client.post(
            f"/admin/ports/{FAKE_PORT['id']}/assign",
            data={"member_id": FAKE_MEMBER["id"], "switch_id": FAKE_SWITCH["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_release_works(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/ports/{FAKE_PORT['id']}/release",
            data={"switch_id": FAKE_SWITCH["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        app.state.api.post.assert_called_once_with(
            f"/api/v1/ports/{FAKE_PORT['id']}/release",
            "test-jwt",
        )

    def test_release_error_flashes(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(400, "Puerto no asignado"))
        resp = authed_client.post(
            f"/admin/ports/{FAKE_PORT['id']}/release",
            data={"switch_id": FAKE_SWITCH["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 302
