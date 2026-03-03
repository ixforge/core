"""Tests for VLANs UI routes."""

import uuid
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from ixforge.ui.api_client import APIError
from ixforge.ui.app import create_ui_app

FAKE_VLAN = {
    "id": str(uuid.uuid4()),
    "ixp_id": str(uuid.uuid4()),
    "name": "Production Peering",
    "vid": 100,
    "type": "production",
    "description": "Main peering VLAN",
    "extra_data": None,
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-01-01T00:00:00",
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


class TestVlanList:
    def test_list_renders(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_VLAN]})
        resp = authed_client.get("/admin/vlans")
        assert resp.status_code == 200
        assert "Production Peering" in resp.text

    def test_list_requires_auth(self):
        app = create_ui_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/admin/vlans")
        assert resp.status_code == 302

    def test_list_empty_shows_empty_state(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"items": []})
        resp = authed_client.get("/admin/vlans")
        assert resp.status_code == 200

    def test_list_filter_by_type(self, authed_client, app):
        mgmt_vlan = {**FAKE_VLAN, "id": str(uuid.uuid4()), "name": "Mgmt VLAN", "type": "management"}
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_VLAN, mgmt_vlan]})
        resp = authed_client.get("/admin/vlans?type=production")
        assert resp.status_code == 200
        assert "Production Peering" in resp.text
        assert "Mgmt VLAN" not in resp.text


class TestVlanForm:
    def test_new_form_renders(self, authed_client):
        resp = authed_client.get("/admin/vlans/new")
        assert resp.status_code == 200
        assert "name" in resp.text.lower()
        assert "vid" in resp.text.lower()

    def test_create_redirects(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value={**FAKE_VLAN})
        resp = authed_client.post(
            "/admin/vlans/new",
            data={
                "name": "Production Peering",
                "vid": "100",
                "type": "production",
                "description": "Main peering VLAN",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/admin/vlans" in resp.headers["location"]

    def test_create_validation_error_shows_form(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(422, {"detail": [{"msg": "field required"}]}))
        resp = authed_client.post(
            "/admin/vlans/new",
            data={"name": "", "vid": "0", "type": "production", "description": ""},
        )
        assert resp.status_code == 200
        assert "Corrige los errores" in resp.text

    def test_edit_form_renders(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value=FAKE_VLAN)
        resp = authed_client.get(f"/admin/vlans/{FAKE_VLAN['id']}/edit")
        assert resp.status_code == 200
        assert "Production Peering" in resp.text

    def test_edit_submit_redirects(self, authed_client, app):
        app.state.api.patch = AsyncMock(return_value={**FAKE_VLAN})
        resp = authed_client.post(
            f"/admin/vlans/{FAKE_VLAN['id']}/edit",
            data={"name": "Production Peering Updated", "vid": "100", "type": "production", "description": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/admin/vlans" in resp.headers["location"]


class TestVlanDelete:
    def test_delete_redirects(self, authed_client, app):
        app.state.api.delete = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/vlans/{FAKE_VLAN['id']}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/admin/vlans" in resp.headers["location"]

    def test_delete_error_flashes(self, authed_client, app):
        app.state.api.delete = AsyncMock(side_effect=APIError(409, "VLAN en uso"))
        resp = authed_client.post(
            f"/admin/vlans/{FAKE_VLAN['id']}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302
