"""Tests for trunk UI routes (replaces old connection UI tests)."""

import uuid
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from ixforge.ui.api_client import APIError
from ixforge.ui.app import create_ui_app

FAKE_MEMBER = {
    "id": str(uuid.uuid4()),
    "ixp_id": str(uuid.uuid4()),
    "name": "Acme Networks",
    "short_name": "ACME",
    "asn": 64512,
    "state": "active",
    "peering_policy": "open",
    "peering_policy_details": None,
    "website": None,
    "peeringdb_id": None,
    "extra_data": None,
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-01-01T00:00:00",
}

FAKE_TRUNK = {
    "id": str(uuid.uuid4()),
    "ixp_id": str(uuid.uuid4()),
    "member_id": FAKE_MEMBER["id"],
    "member_name": "Acme Networks",
    "name": "ae0",
    "state": "draft",
    "mac_address": "00:11:22:33:44:55",
    "notes": None,
    "extra_data": None,
    "created_at": "2026-01-15T00:00:00",
    "updated_at": "2026-01-15T00:00:00",
}

FAKE_VLAN = {
    "id": str(uuid.uuid4()),
    "name": "Peering",
    "vid": 100,
}

FAKE_TRUNK_VLAN = {
    "id": str(uuid.uuid4()),
    "trunk_id": FAKE_TRUNK["id"],
    "vlan_id": FAKE_VLAN["id"],
    "vlan_name": "Peering",
    "vid": 100,
    "created_at": "2026-01-15T00:00:00",
    "updated_at": "2026-01-15T00:00:00",
}

FAKE_IP_POOL = {
    "id": str(uuid.uuid4()),
    "name": "v4-pool",
    "network": "10.0.0.0/24",
    "vlan_id": FAKE_VLAN["id"],
}

FAKE_SWITCH = {
    "id": str(uuid.uuid4()),
    "name": "sw-core-01",
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


class TestTrunkList:
    def test_list_renders(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == "/api/v1/members":
                return {"items": [FAKE_MEMBER], "next_cursor": None, "has_more": False}
            if path == "/api/v1/trunks":
                return {"items": [FAKE_TRUNK], "next_cursor": None, "has_more": False}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get("/admin/trunks")
        assert resp.status_code == 200
        assert "Acme Networks" in resp.text
        assert "ae0" in resp.text

    def test_list_requires_auth(self):
        app = create_ui_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/admin/trunks")
        assert resp.status_code == 302

    def test_list_filters_by_state(self, authed_client, app):
        active_trunk = {**FAKE_TRUNK, "state": "active"}
        draft_trunk = {**FAKE_TRUNK, "id": str(uuid.uuid4()), "state": "draft"}

        async def fake_get(path, token, params=None):
            if path == "/api/v1/members":
                return {"items": [FAKE_MEMBER], "next_cursor": None, "has_more": False}
            if path == "/api/v1/trunks":
                return {"items": [active_trunk, draft_trunk], "next_cursor": None, "has_more": False}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get("/admin/trunks?state=active")
        assert resp.status_code == 200
        assert "Activo" in resp.text


class TestTrunkDetail:
    def test_detail_renders(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == f"/api/v1/trunks/{FAKE_TRUNK['id']}/vlans":
                return [FAKE_TRUNK_VLAN]
            if path == f"/api/v1/trunks/{FAKE_TRUNK['id']}/connections":
                return []
            if path.startswith(f"/api/v1/trunks/{FAKE_TRUNK['id']}/vlans/") and path.endswith("/ips"):
                return []
            if path == f"/api/v1/trunks/{FAKE_TRUNK['id']}":
                return FAKE_TRUNK
            if path.startswith("/api/v1/members/"):
                return FAKE_MEMBER
            if path == "/api/v1/vlans":
                return {"items": [FAKE_VLAN], "next_cursor": None, "has_more": False}
            if path == "/api/v1/ip-pools":
                return {"items": [FAKE_IP_POOL], "next_cursor": None, "has_more": False}
            if path == "/api/v1/route-servers":
                return {"items": [], "next_cursor": None, "has_more": False}
            if path == "/api/v1/switches":
                return {"items": [FAKE_SWITCH], "next_cursor": None, "has_more": False}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/trunks/{FAKE_TRUNK['id']}")
        assert resp.status_code == 200
        assert "Acme Networks" in resp.text
        assert "ae0" in resp.text

    def test_detail_404_redirects(self, authed_client, app):
        app.state.api.get = AsyncMock(side_effect=APIError(404))
        resp = authed_client.get(f"/admin/trunks/{uuid.uuid4()}", follow_redirects=False)
        assert resp.status_code == 302

    def _render_with_connection(self, app, authed_client, conn_state):
        conn = {
            "id": str(uuid.uuid4()),
            "name": "Et27/1",
            "type": "physical",
            "speed": 10000,
            "switch_id": FAKE_SWITCH["id"],
            "state": conn_state,
        }

        async def fake_get(path, token, params=None):
            if path == f"/api/v1/trunks/{FAKE_TRUNK['id']}/vlans":
                return [FAKE_TRUNK_VLAN]
            if path == f"/api/v1/trunks/{FAKE_TRUNK['id']}/connections":
                return [conn]
            if path.startswith(f"/api/v1/trunks/{FAKE_TRUNK['id']}/vlans/") and path.endswith("/ips"):
                return []
            if path == f"/api/v1/trunks/{FAKE_TRUNK['id']}":
                return FAKE_TRUNK
            if path.startswith("/api/v1/members/"):
                return FAKE_MEMBER
            if path == "/api/v1/vlans":
                return {"items": [FAKE_VLAN], "next_cursor": None, "has_more": False}
            if path == "/api/v1/ip-pools":
                return {"items": [FAKE_IP_POOL], "next_cursor": None, "has_more": False}
            if path == "/api/v1/route-servers":
                return {"items": [], "next_cursor": None, "has_more": False}
            if path == "/api/v1/switches":
                return {"items": [FAKE_SWITCH], "next_cursor": None, "has_more": False}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/trunks/{FAKE_TRUNK['id']}")
        assert resp.status_code == 200
        return conn, resp.text

    def test_disabled_connection_shows_decommission_and_reactivate(self, authed_client, app):
        conn, html = self._render_with_connection(app, authed_client, "disabled")
        transition_url = (
            f"/admin/trunks/{FAKE_TRUNK['id']}/connections/{conn['id']}/transition"
        )
        assert transition_url in html
        assert "Decomisionar" in html
        assert "Reactivar" in html

    def test_decommissioned_connection_shows_delete(self, authed_client, app):
        conn, html = self._render_with_connection(app, authed_client, "decommissioned")
        delete_url = f"/admin/trunks/{FAKE_TRUNK['id']}/connections/{conn['id']}/delete"
        assert delete_url in html
        assert "Eliminar" in html

    def test_active_connection_still_shows_disable(self, authed_client, app):
        _conn, html = self._render_with_connection(app, authed_client, "active")
        assert "Deshabilitar" in html


class TestTrunkForm:
    def test_new_form_renders(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == "/api/v1/members":
                return {"items": [FAKE_MEMBER], "next_cursor": None, "has_more": False}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get("/admin/trunks/new")
        assert resp.status_code == 200
        assert "Acme Networks" in resp.text
        assert "member_id" in resp.text

    def test_create_redirects(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == "/api/v1/members":
                return {"items": [FAKE_MEMBER], "next_cursor": None, "has_more": False}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        app.state.api.post = AsyncMock(return_value={**FAKE_TRUNK})
        resp = authed_client.post(
            "/admin/trunks/new",
            data={
                "member_id": FAKE_MEMBER["id"],
                "name": "ae0",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"/admin/trunks/{FAKE_TRUNK['id']}" in resp.headers["location"]

    def test_create_validation_error_shows_form(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == "/api/v1/members":
                return {"items": [FAKE_MEMBER], "next_cursor": None, "has_more": False}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        app.state.api.post = AsyncMock(side_effect=APIError(422, {"error": {"code": "VALIDATION_ERROR", "message": "Validation error", "details": [{"msg": "required"}]}}))
        resp = authed_client.post(
            "/admin/trunks/new",
            data={"member_id": "", "name": ""},
        )
        assert resp.status_code == 200
        assert "Validation error" in resp.text

    def test_edit_form_renders(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path.startswith("/api/v1/trunks/"):
                return FAKE_TRUNK
            if path == "/api/v1/members":
                return {"items": [FAKE_MEMBER], "next_cursor": None, "has_more": False}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/trunks/{FAKE_TRUNK['id']}/edit")
        assert resp.status_code == 200
        assert "ae0" in resp.text

    def test_edit_submit_redirects(self, authed_client, app):
        app.state.api.patch = AsyncMock(return_value={**FAKE_TRUNK})
        resp = authed_client.post(
            f"/admin/trunks/{FAKE_TRUNK['id']}/edit",
            data={"name": "ae1", "mac_address": "AA:BB:CC:DD:EE:FF"},
            follow_redirects=False,
        )
        assert resp.status_code == 302


class TestTrunkActions:
    def test_transition(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/trunks/{FAKE_TRUNK['id']}/transition",
            data={"state": "provisioning"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        app.state.api.post.assert_called_once_with(
            f"/api/v1/trunks/{FAKE_TRUNK['id']}/transition",
            "test-jwt",
            json={"state": "provisioning"},
        )

    def test_assign_vlan(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/trunks/{FAKE_TRUNK['id']}/vlans",
            data={"vlan_id": FAKE_VLAN["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        app.state.api.post.assert_called_once_with(
            f"/api/v1/trunks/{FAKE_TRUNK['id']}/vlans",
            "test-jwt",
            json={"vlan_id": FAKE_VLAN["id"]},
        )

    def test_unassign_vlan(self, authed_client, app):
        app.state.api.delete = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/trunks/{FAKE_TRUNK['id']}/vlans/{FAKE_TRUNK_VLAN['id']}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        app.state.api.delete.assert_called_once_with(
            f"/api/v1/trunks/{FAKE_TRUNK['id']}/vlans/{FAKE_TRUNK_VLAN['id']}",
            "test-jwt",
        )

    def test_assign_ip(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/trunks/{FAKE_TRUNK['id']}/vlans/{FAKE_TRUNK_VLAN['id']}/ips",
            data={"pool_id": FAKE_IP_POOL["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        app.state.api.post.assert_called_once_with(
            f"/api/v1/trunks/{FAKE_TRUNK['id']}/vlans/{FAKE_TRUNK_VLAN['id']}/ips",
            "test-jwt",
            json={"pool_id": FAKE_IP_POOL["id"]},
        )

    def test_assign_ip_with_address(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/trunks/{FAKE_TRUNK['id']}/vlans/{FAKE_TRUNK_VLAN['id']}/ips",
            data={"pool_id": FAKE_IP_POOL["id"], "address": "10.0.0.5"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        app.state.api.post.assert_called_once_with(
            f"/api/v1/trunks/{FAKE_TRUNK['id']}/vlans/{FAKE_TRUNK_VLAN['id']}/ips",
            "test-jwt",
            json={"pool_id": FAKE_IP_POOL["id"], "address": "10.0.0.5"},
        )

    def test_release_ip(self, authed_client, app):
        assignment_id = str(uuid.uuid4())
        app.state.api.delete = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/trunks/{FAKE_TRUNK['id']}/vlans/{FAKE_TRUNK_VLAN['id']}/ips/{assignment_id}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        app.state.api.delete.assert_called_once_with(
            f"/api/v1/trunks/{FAKE_TRUNK['id']}/vlans/{FAKE_TRUNK_VLAN['id']}/ips/{assignment_id}",
            "test-jwt",
        )

    def test_assign_vlan_error_flashes(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(400, "VLAN already assigned"))
        resp = authed_client.post(
            f"/admin/trunks/{FAKE_TRUNK['id']}/vlans",
            data={"vlan_id": FAKE_VLAN["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_assign_ip_error_flashes(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(400, "Pool exhausted"))
        resp = authed_client.post(
            f"/admin/trunks/{FAKE_TRUNK['id']}/vlans/{FAKE_TRUNK_VLAN['id']}/ips",
            data={"pool_id": FAKE_IP_POOL["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_add_connection(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/trunks/{FAKE_TRUNK['id']}/connections",
            data={
                "switch_id": FAKE_SWITCH["id"],
                "name": "Ethernet1",
                "type": "physical",
                "speed": "10000",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_delete_connection(self, authed_client, app):
        cid = str(uuid.uuid4())
        app.state.api.delete = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/trunks/{FAKE_TRUNK['id']}/connections/{cid}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"/admin/trunks/{FAKE_TRUNK['id']}" in resp.headers["location"]
        app.state.api.delete.assert_awaited_once_with(
            f"/api/v1/connections/{cid}", "test-jwt"
        )

    def test_delete_connection_error_flashes(self, authed_client, app):
        cid = str(uuid.uuid4())
        app.state.api.delete = AsyncMock(side_effect=APIError(422, "not decommissioned"))
        resp = authed_client.post(
            f"/admin/trunks/{FAKE_TRUNK['id']}/connections/{cid}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302
