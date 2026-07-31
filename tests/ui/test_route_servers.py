"""Tests for route servers UI routes."""

import uuid
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from ixforge.ui.api_client import APIError
from ixforge.ui.app import create_ui_app

FAKE_RS = {
    "id": str(uuid.uuid4()),
    "ixp_id": str(uuid.uuid4()),
    "name": "RS-01",
    "ip_v4": "10.0.0.1",
    "ip_v6": "2001:db8::1",
    "is_active": True,
    "notes": "Test notes",
    "agent_version": "0.1.0",
    "last_heartbeat": "2026-01-15T10:00:00",
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-01-01T00:00:00",
}

FAKE_BGP_SESSION = {
    "id": str(uuid.uuid4()),
    "route_server_id": FAKE_RS["id"],
    "connection_id": str(uuid.uuid4()),
    "peer_ip": "10.0.0.10",
    "peer_asn": 64512,
    "admin_state": "up",
    "oper_state": "established",
    "address_family": "ipv4",
}

FAKE_CONFIG = {
    "id": str(uuid.uuid4()),
    "hash": "abc123",
    "generated_at": "2026-01-15T10:00:00",
    "applied_at": None,
}

FAKE_VLAN = {
    "id": str(uuid.uuid4()),
    "name": "Production",
    "vid": 100,
    "type": "production",
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


class TestRouteServerList:
    def test_list_renders(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_RS]})
        resp = authed_client.get("/admin/route-servers")
        assert resp.status_code == 200
        assert "RS-01" in resp.text

    def test_list_requires_auth(self):
        app = create_ui_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/admin/route-servers")
        assert resp.status_code == 302

    def test_list_filter_by_is_active(self, authed_client, app):
        inactive_rs = {**FAKE_RS, "id": str(uuid.uuid4()), "name": "rs2-inactive", "is_active": False}
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_RS, inactive_rs]})
        resp = authed_client.get("/admin/route-servers?is_active=true")
        assert resp.status_code == 200
        assert "RS-01" in resp.text
        assert "rs2-inactive" not in resp.text

    def test_list_htmx_returns_partial(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"items": [FAKE_RS]})
        resp = authed_client.get("/admin/route-servers", headers={"hx-request": "true"})
        assert resp.status_code == 200
        assert "<!DOCTYPE html>" not in resp.text
        assert "RS-01" in resp.text


class TestRouteServerDetail:
    def test_detail_renders(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == f"/api/v1/route-servers/{FAKE_RS['id']}":
                return FAKE_RS
            if path == "/api/v1/bgp-sessions":
                return {"items": [FAKE_BGP_SESSION]}
            if path.endswith("/config/current"):
                return FAKE_CONFIG
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/route-servers/{FAKE_RS['id']}")
        assert resp.status_code == 200
        assert "RS-01" in resp.text
        assert "10.0.0.10" in resp.text  # BGP session peer_ip

    def test_detail_404_redirects(self, authed_client, app):
        app.state.api.get = AsyncMock(side_effect=APIError(404))
        resp = authed_client.get(f"/admin/route-servers/{uuid.uuid4()}", follow_redirects=False)
        assert resp.status_code == 302

    def test_pending_config_shows_warning(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == f"/api/v1/route-servers/{FAKE_RS['id']}":
                return FAKE_RS
            if path == "/api/v1/bgp-sessions":
                return {"items": []}
            if path.endswith("/config/current"):
                return {**FAKE_CONFIG, "applied_at": None}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/route-servers/{FAKE_RS['id']}")
        assert resp.status_code == 200
        assert "Config pendiente de aplicar" in resp.text
        assert "journalctl -u ixforge-agent" in resp.text

    def test_applied_config_no_warning(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == f"/api/v1/route-servers/{FAKE_RS['id']}":
                return FAKE_RS
            if path == "/api/v1/bgp-sessions":
                return {"items": []}
            if path.endswith("/config/current"):
                return {**FAKE_CONFIG, "applied_at": "2026-01-15T10:05:00"}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/route-servers/{FAKE_RS['id']}")
        assert resp.status_code == 200
        assert "Config pendiente de aplicar" not in resp.text


class TestRouteServerForm:
    def test_new_form_renders(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == "/api/v1/vlans":
                return {"items": [FAKE_VLAN]}
            return {"id": "abc", "role": "admin", "member_id": None}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get("/admin/route-servers/new")
        assert resp.status_code == 200
        assert "name" in resp.text.lower()
        assert "Production" in resp.text

    def test_create_redirects(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == "/api/v1/vlans":
                return {"items": [FAKE_VLAN]}
            return {"id": "abc", "role": "admin", "member_id": None}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        app.state.api.post = AsyncMock(return_value={**FAKE_RS})
        resp = authed_client.post(
            "/admin/route-servers/new",
            data={
                "name": "RS-01",
                "is_active": "on",
                "notes": "Test",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"/admin/route-servers/{FAKE_RS['id']}" in resp.headers["location"]

    def test_create_with_vlan_and_ip(self, authed_client, app):
        pool_id = str(uuid.uuid4())

        async def fake_get(path, token, params=None):
            if path == "/api/v1/vlans":
                return {"items": [FAKE_VLAN]}
            return {"id": "abc", "role": "admin", "member_id": None}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        app.state.api.post = AsyncMock(return_value={**FAKE_RS})
        resp = authed_client.post(
            "/admin/route-servers/new",
            data={
                "name": "RS-01",
                "is_active": "on",
                "vlan_id": FAKE_VLAN["id"],
                "ipv4": "10.0.0.1",
                "ipv4_pool_id": pool_id,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        # Should have called post 3 times: create RS, add VLAN, assign IP
        assert app.state.api.post.call_count == 3

    def test_create_validation_error_shows_form(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == "/api/v1/vlans":
                return {"items": [FAKE_VLAN]}
            return {"id": "abc", "role": "admin", "member_id": None}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        app.state.api.post = AsyncMock(side_effect=APIError(422, {"error": {"code": "VALIDATION_ERROR", "message": "Validation error", "details": [{"msg": "required"}]}}))
        resp = authed_client.post(
            "/admin/route-servers/new",
            data={"name": ""},
        )
        assert resp.status_code == 200
        assert "Validation error" in resp.text

    def test_edit_form_renders(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value=FAKE_RS)
        resp = authed_client.get(f"/admin/route-servers/{FAKE_RS['id']}/edit")
        assert resp.status_code == 200
        assert "RS-01" in resp.text

    def test_edit_submit_redirects(self, authed_client, app):
        app.state.api.patch = AsyncMock(return_value={**FAKE_RS})
        resp = authed_client.post(
            f"/admin/route-servers/{FAKE_RS['id']}/edit",
            data={"name": "rs1-updated", "notes": "Updated notes"},
            follow_redirects=False,
        )
        assert resp.status_code == 302


class TestRouteServerVlanPools:
    def test_vlan_pools_returns_fragment(self, authed_client, app):
        fake_pools = [
            {"id": str(uuid.uuid4()), "network": "10.0.0.0/24", "af": 4, "total_hosts": 254, "used_count": 5, "next_available": "10.0.0.6"},
        ]

        async def fake_get(path, token, params=None):
            if path == "/api/v1/ip-pools/available":
                return fake_pools
            return {"id": "abc", "role": "admin", "member_id": None}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/route-servers/vlan-pools?vlan_id={uuid.uuid4()}")
        assert resp.status_code == 200
        assert "10.0.0.0/24" in resp.text
        assert "10.0.0.6" in resp.text

    def test_vlan_pools_empty_vlan_id(self, authed_client, app):
        resp = authed_client.get("/admin/route-servers/vlan-pools?vlan_id=")
        assert resp.status_code == 200


class TestRouteServerVlans:
    def test_vlan_add_redirects(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/route-servers/{FAKE_RS['id']}/vlans/add",
            data={"vlan_id": str(uuid.uuid4())},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"/admin/route-servers/{FAKE_RS['id']}" in resp.headers["location"]

    def test_vlan_add_empty_vlan_flashes_error(self, authed_client, app):
        resp = authed_client.post(
            f"/admin/route-servers/{FAKE_RS['id']}/vlans/add",
            data={"vlan_id": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_vlan_add_api_error_flashes(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(409, "Ya asociada"))
        resp = authed_client.post(
            f"/admin/route-servers/{FAKE_RS['id']}/vlans/add",
            data={"vlan_id": str(uuid.uuid4())},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_vlan_remove_redirects(self, authed_client, app):
        vlan_id = str(uuid.uuid4())
        app.state.api.delete = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/route-servers/{FAKE_RS['id']}/vlans/{vlan_id}/remove",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"/admin/route-servers/{FAKE_RS['id']}" in resp.headers["location"]
        app.state.api.delete.assert_called_once_with(
            f"/api/v1/route-servers/{FAKE_RS['id']}/vlans/{vlan_id}",
            "test-jwt",
        )

    def test_vlan_remove_api_error_flashes(self, authed_client, app):
        app.state.api.delete = AsyncMock(side_effect=APIError(404, "No encontrada"))
        resp = authed_client.post(
            f"/admin/route-servers/{FAKE_RS['id']}/vlans/{uuid.uuid4()}/remove",
            follow_redirects=False,
        )
        assert resp.status_code == 302


class TestRouteServerIps:
    def test_ip_assign_redirects(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/route-servers/{FAKE_RS['id']}/ips/assign",
            data={"pool_id": str(uuid.uuid4())},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"/admin/route-servers/{FAKE_RS['id']}" in resp.headers["location"]

    def test_ip_assign_with_address(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value=None)
        pool_id = str(uuid.uuid4())
        resp = authed_client.post(
            f"/admin/route-servers/{FAKE_RS['id']}/ips/assign",
            data={"pool_id": pool_id, "address": "10.0.0.5"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        app.state.api.post.assert_called_once_with(
            f"/api/v1/route-servers/{FAKE_RS['id']}/ips",
            "test-jwt",
            json={"pool_id": pool_id, "address": "10.0.0.5"},
        )

    def test_ip_assign_empty_pool_flashes_error(self, authed_client, app):
        resp = authed_client.post(
            f"/admin/route-servers/{FAKE_RS['id']}/ips/assign",
            data={"pool_id": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_ip_assign_api_error_flashes(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(400, "Pool agotado"))
        resp = authed_client.post(
            f"/admin/route-servers/{FAKE_RS['id']}/ips/assign",
            data={"pool_id": str(uuid.uuid4())},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_ip_release_redirects(self, authed_client, app):
        assignment_id = str(uuid.uuid4())
        app.state.api.delete = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/route-servers/{FAKE_RS['id']}/ips/{assignment_id}/release",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"/admin/route-servers/{FAKE_RS['id']}" in resp.headers["location"]
        app.state.api.delete.assert_called_once_with(
            f"/api/v1/route-servers/{FAKE_RS['id']}/ips/{assignment_id}",
            "test-jwt",
        )

    def test_ip_release_api_error_flashes(self, authed_client, app):
        app.state.api.delete = AsyncMock(side_effect=APIError(404, "No encontrada"))
        resp = authed_client.post(
            f"/admin/route-servers/{FAKE_RS['id']}/ips/{uuid.uuid4()}/release",
            follow_redirects=False,
        )
        assert resp.status_code == 302


class TestRouteServerDelete:
    def test_delete_redirects(self, authed_client, app):
        app.state.api.delete = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/route-servers/{FAKE_RS['id']}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/admin/route-servers" in resp.headers["location"]

    def test_delete_error_flashes(self, authed_client, app):
        app.state.api.delete = AsyncMock(side_effect=APIError(409, "RS en uso"))
        resp = authed_client.post(
            f"/admin/route-servers/{FAKE_RS['id']}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302
