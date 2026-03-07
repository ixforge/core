"""Tests for IP Pools UI routes."""

import uuid
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from ixforge.ui.api_client import APIError
from ixforge.ui.app import create_ui_app

FAKE_VLAN = {
    "id": str(uuid.uuid4()),
    "name": "Peering",
    "vid": 100,
    "type": "production",
    "description": "",
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-01-01T00:00:00",
}

FAKE_POOL = {
    "id": str(uuid.uuid4()),
    "vlan_id": FAKE_VLAN["id"],
    "network": "192.0.2.0/24",
    "af": 4,
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-01-01T00:00:00",
}

FAKE_ASSIGNMENT = {
    "id": str(uuid.uuid4()),
    "address": "192.0.2.10",
    "connection_id": str(uuid.uuid4()),
    "pool_id": FAKE_POOL["id"],
    "created_at": "2026-01-01T00:00:00",
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


class TestIpPoolList:
    def test_list_renders(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == "/api/v1/vlans":
                return {"items": [FAKE_VLAN]}
            if path == "/api/v1/ip-pools":
                return {"items": [FAKE_POOL]}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/ip-pools?vlan_id={FAKE_VLAN['id']}")
        assert resp.status_code == 200
        assert "192.0.2.0/24" in resp.text

    def test_list_requires_auth(self):
        app = create_ui_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/admin/ip-pools")
        assert resp.status_code == 302

    def test_list_no_vlan_shows_prompt(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_VLAN]})
        resp = authed_client.get("/admin/ip-pools")
        assert resp.status_code == 200
        assert "Selecciona una VLAN" in resp.text

    def test_list_empty_shows_empty_state(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == "/api/v1/vlans":
                return {"items": [FAKE_VLAN]}
            if path == "/api/v1/ip-pools":
                return {"items": []}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/ip-pools?vlan_id={FAKE_VLAN['id']}")
        assert resp.status_code == 200


class TestIpPoolDetail:
    def test_detail_renders(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == f"/api/v1/ip-pools/{FAKE_POOL['id']}":
                return FAKE_POOL
            if path == f"/api/v1/ip-pools/{FAKE_POOL['id']}/assignments":
                return {"items": [FAKE_ASSIGNMENT]}
            if path == "/api/v1/vlans":
                return {"items": [FAKE_VLAN]}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/ip-pools/{FAKE_POOL['id']}")
        assert resp.status_code == 200
        assert "192.0.2.0/24" in resp.text
        assert "192.0.2.10" in resp.text

    def test_detail_renders_no_assignments(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == f"/api/v1/ip-pools/{FAKE_POOL['id']}":
                return FAKE_POOL
            if path == f"/api/v1/ip-pools/{FAKE_POOL['id']}/assignments":
                return {"items": []}
            if path == "/api/v1/vlans":
                return {"items": [FAKE_VLAN]}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/ip-pools/{FAKE_POOL['id']}")
        assert resp.status_code == 200
        assert "No hay asignaciones" in resp.text

    def test_detail_404_redirects(self, authed_client, app):
        app.state.api.get = AsyncMock(side_effect=APIError(404))
        resp = authed_client.get(f"/admin/ip-pools/{uuid.uuid4()}", follow_redirects=False)
        assert resp.status_code == 302


class TestIpPoolForm:
    def test_new_form_renders(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_VLAN]})
        resp = authed_client.get("/admin/ip-pools/new")
        assert resp.status_code == 200
        assert "network" in resp.text.lower()
        assert "vlan_id" in resp.text.lower()

    def test_new_form_preselects_vlan(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_VLAN]})
        resp = authed_client.get(f"/admin/ip-pools/new?vlan_id={FAKE_VLAN['id']}")
        assert resp.status_code == 200
        assert "selected" in resp.text

    def test_create_redirects(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value={**FAKE_POOL})
        resp = authed_client.post(
            "/admin/ip-pools/new",
            data={
                "vlan_id": FAKE_VLAN["id"],
                "network": "192.0.2.0/24",
                "af": "4",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/admin/ip-pools" in resp.headers["location"]

    def test_create_validation_error_shows_form(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_VLAN]})
        app.state.api.post = AsyncMock(side_effect=APIError(422, {"detail": [{"msg": "field required"}]}))
        resp = authed_client.post(
            "/admin/ip-pools/new",
            data={"vlan_id": "", "network": "", "af": "4"},
        )
        assert resp.status_code == 200
        assert "Corrige los errores" in resp.text


class TestIpPoolDelete:
    def test_delete_redirects(self, authed_client, app):
        async def fake_get(path, token, params=None):
            return FAKE_POOL

        app.state.api.get = AsyncMock(side_effect=fake_get)
        app.state.api.delete = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/ip-pools/{FAKE_POOL['id']}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/admin/ip-pools" in resp.headers["location"]

    def test_delete_error_flashes(self, authed_client, app):
        async def fake_get(path, token, params=None):
            return FAKE_POOL

        app.state.api.get = AsyncMock(side_effect=fake_get)
        app.state.api.delete = AsyncMock(side_effect=APIError(409, "Pool en uso"))
        resp = authed_client.post(
            f"/admin/ip-pools/{FAKE_POOL['id']}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302
