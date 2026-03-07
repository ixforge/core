"""Tests for BGP sessions UI routes."""

import uuid
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from ixforge.ui.api_client import APIError
from ixforge.ui.app import create_ui_app

FAKE_RS = {
    "id": str(uuid.uuid4()),
    "name": "rs1.example.net",
}

FAKE_SESSION = {
    "id": str(uuid.uuid4()),
    "route_server_id": FAKE_RS["id"],
    "connection_id": str(uuid.uuid4()),
    "peer_ip": "10.0.0.10",
    "peer_asn": 64512,
    "admin_state": "up",
    "oper_state": "established",
    "address_family": "ipv4",
    "max_prefixes_v4": 100,
    "max_prefixes_v6": 50,
    "created_at": "2026-01-15T10:00:00",
    "updated_at": "2026-01-15T10:00:00",
}

FAKE_MEMBER = {
    "id": str(uuid.uuid4()),
    "name": "Acme Networks",
}

FAKE_CONNECTION = {
    "id": FAKE_SESSION["connection_id"],
    "member_id": FAKE_MEMBER["id"],
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


class TestBGPSessionList:
    def test_list_renders_with_rs_filter(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == "/api/v1/route-servers":
                return {"items": [FAKE_RS]}
            if path == "/api/v1/bgp-sessions":
                return {"items": [FAKE_SESSION]}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/bgp-sessions?route_server_id={FAKE_RS['id']}")
        assert resp.status_code == 200
        assert "10.0.0.10" in resp.text

    def test_list_no_rs_shows_empty(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_RS]})
        resp = authed_client.get("/admin/bgp-sessions")
        assert resp.status_code == 200
        assert "BGP Sessions" in resp.text

    def test_list_requires_auth(self):
        app = create_ui_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/admin/bgp-sessions")
        assert resp.status_code == 302


class TestBGPSessionDetail:
    def test_detail_renders(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == f"/api/v1/bgp-sessions/{FAKE_SESSION['id']}":
                return FAKE_SESSION
            if path == f"/api/v1/route-servers/{FAKE_RS['id']}":
                return FAKE_RS
            if path == f"/api/v1/connections/{FAKE_SESSION['connection_id']}":
                return FAKE_CONNECTION
            if path == f"/api/v1/members/{FAKE_MEMBER['id']}":
                return FAKE_MEMBER
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/bgp-sessions/{FAKE_SESSION['id']}")
        assert resp.status_code == 200
        assert "10.0.0.10" in resp.text
        assert "rs1.example.net" in resp.text

    def test_detail_404_redirects(self, authed_client, app):
        app.state.api.get = AsyncMock(side_effect=APIError(404))
        resp = authed_client.get(f"/admin/bgp-sessions/{uuid.uuid4()}", follow_redirects=False)
        assert resp.status_code == 302


class TestBGPSessionToggle:
    def test_toggle_changes_admin_state(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value=FAKE_SESSION)
        app.state.api.patch = AsyncMock(return_value={**FAKE_SESSION, "admin_state": "down"})
        resp = authed_client.post(
            f"/admin/bgp-sessions/{FAKE_SESSION['id']}/toggle",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        # Should toggle from "up" to "down"
        app.state.api.patch.assert_called_once_with(
            f"/api/v1/bgp-sessions/{FAKE_SESSION['id']}",
            "test-jwt",
            json={"admin_state": "down"},
        )

    def test_toggle_error_flashes(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value=FAKE_SESSION)
        app.state.api.patch = AsyncMock(side_effect=APIError(400, "Cannot toggle"))
        resp = authed_client.post(
            f"/admin/bgp-sessions/{FAKE_SESSION['id']}/toggle",
            follow_redirects=False,
        )
        assert resp.status_code == 302
