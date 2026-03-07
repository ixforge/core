"""Tests for connections UI routes."""

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

FAKE_CONNECTION = {
    "id": str(uuid.uuid4()),
    "ixp_id": str(uuid.uuid4()),
    "member_id": FAKE_MEMBER["id"],
    "port_id": str(uuid.uuid4()),
    "port_name": "eth0",
    "type": "physical",
    "state": "draft",
    "speed": 10000,
    "mac_address": "00:11:22:33:44:55",
    "vlans": [],
    "ips": [],
    "created_at": "2026-01-15T00:00:00",
    "updated_at": "2026-01-15T00:00:00",
}

FAKE_VLAN = {
    "id": str(uuid.uuid4()),
    "name": "Peering",
    "vid": 100,
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


class TestConnectionsList:
    def test_list_renders_with_member(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == "/api/v1/members":
                return {"items": [FAKE_MEMBER], "next_cursor": None, "has_more": False}
            if path == "/api/v1/connections":
                return {"items": [FAKE_CONNECTION], "next_cursor": None, "has_more": False}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/connections?member_id={FAKE_MEMBER['id']}")
        assert resp.status_code == 200
        assert "Acme Networks" in resp.text
        assert "00:11:22:33:44:55" in resp.text

    def test_list_no_member_shows_all(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == "/api/v1/members":
                return {"items": [FAKE_MEMBER], "next_cursor": None, "has_more": False}
            if path == "/api/v1/connections":
                return {"items": [FAKE_CONNECTION], "next_cursor": None, "has_more": False}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get("/admin/connections")
        assert resp.status_code == 200
        assert "Conexiones" in resp.text
        assert "00:11:22:33:44:55" in resp.text

    def test_list_requires_auth(self):
        app = create_ui_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/admin/connections")
        assert resp.status_code == 302

    def test_list_filters_by_state(self, authed_client, app):
        active_conn = {**FAKE_CONNECTION, "state": "active"}
        draft_conn = {**FAKE_CONNECTION, "id": str(uuid.uuid4()), "state": "draft"}

        async def fake_get(path, token, params=None):
            if path == "/api/v1/members":
                return {"items": [FAKE_MEMBER], "next_cursor": None, "has_more": False}
            if path == "/api/v1/connections":
                return {"items": [active_conn, draft_conn], "next_cursor": None, "has_more": False}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/connections?member_id={FAKE_MEMBER['id']}&state=active")
        assert resp.status_code == 200
        # Should only show the active connection badge, not draft
        assert "Activo" in resp.text


class TestConnectionDetail:
    def test_detail_renders(self, authed_client, app):
        conn_with_vlans = {
            **FAKE_CONNECTION,
            "vlans": [{"vlan_id": FAKE_VLAN["id"], "vlan_name": "Peering", "vid": 100, "tagged": False}],
            "ips": [{"id": str(uuid.uuid4()), "address": "10.0.0.1", "pool_network": "10.0.0.0/24"}],
        }

        async def fake_get(path, token, params=None):
            if path.startswith("/api/v1/connections/"):
                return conn_with_vlans
            if path.startswith("/api/v1/members/"):
                return FAKE_MEMBER
            if path == "/api/v1/vlans":
                return {"items": [FAKE_VLAN], "next_cursor": None, "has_more": False}
            if path == "/api/v1/ip-pools":
                return {"items": [FAKE_IP_POOL], "next_cursor": None, "has_more": False}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/connections/{FAKE_CONNECTION['id']}")
        assert resp.status_code == 200
        assert "Acme Networks" in resp.text
        assert "00:11:22:33:44:55" in resp.text
        assert "Peering" in resp.text
        assert "10.0.0.1" in resp.text

    def test_detail_404_redirects(self, authed_client, app):
        app.state.api.get = AsyncMock(side_effect=APIError(404))
        resp = authed_client.get(f"/admin/connections/{uuid.uuid4()}", follow_redirects=False)
        assert resp.status_code == 302


class TestConnectionForm:
    def test_new_form_renders(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == "/api/v1/members":
                return {"items": [FAKE_MEMBER], "next_cursor": None, "has_more": False}
            if path == "/api/v1/switches":
                return {"items": [FAKE_SWITCH], "next_cursor": None, "has_more": False}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get("/admin/connections/new")
        assert resp.status_code == 200
        assert "Acme Networks" in resp.text
        assert "member_id" in resp.text

    def test_create_redirects(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == "/api/v1/members":
                return {"items": [FAKE_MEMBER], "next_cursor": None, "has_more": False}
            if path == "/api/v1/switches":
                return {"items": [FAKE_SWITCH], "next_cursor": None, "has_more": False}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        app.state.api.post = AsyncMock(return_value={**FAKE_CONNECTION})
        resp = authed_client.post(
            "/admin/connections/new",
            data={
                "member_id": FAKE_MEMBER["id"],
                "type": "physical",
                "speed": "10000",
                "mac_address": "00:11:22:33:44:55",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"/admin/connections/{FAKE_CONNECTION['id']}" in resp.headers["location"]

    def test_create_validation_error_shows_form(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == "/api/v1/members":
                return {"items": [FAKE_MEMBER], "next_cursor": None, "has_more": False}
            if path == "/api/v1/switches":
                return {"items": [FAKE_SWITCH], "next_cursor": None, "has_more": False}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        app.state.api.post = AsyncMock(side_effect=APIError(422, {"detail": [{"msg": "required"}]}))
        resp = authed_client.post(
            "/admin/connections/new",
            data={"member_id": "", "type": "physical", "speed": "0", "mac_address": ""},
        )
        assert resp.status_code == 200
        assert "Corrige los errores" in resp.text

    def test_edit_form_renders(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path.startswith("/api/v1/connections/"):
                return FAKE_CONNECTION
            if path == "/api/v1/members":
                return {"items": [FAKE_MEMBER], "next_cursor": None, "has_more": False}
            if path == "/api/v1/switches":
                return {"items": [FAKE_SWITCH], "next_cursor": None, "has_more": False}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/connections/{FAKE_CONNECTION['id']}/edit")
        assert resp.status_code == 200
        assert "00:11:22:33:44:55" in resp.text

    def test_edit_submit_redirects(self, authed_client, app):
        app.state.api.patch = AsyncMock(return_value={**FAKE_CONNECTION})
        resp = authed_client.post(
            f"/admin/connections/{FAKE_CONNECTION['id']}/edit",
            data={"type": "physical", "speed": "10000", "mac_address": "AA:BB:CC:DD:EE:FF"},
            follow_redirects=False,
        )
        assert resp.status_code == 302


class TestConnectionActions:
    def test_transition(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/connections/{FAKE_CONNECTION['id']}/transition",
            data={"state": "provisioning"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        app.state.api.post.assert_called_once_with(
            f"/api/v1/connections/{FAKE_CONNECTION['id']}/transition",
            "test-jwt",
            json={"state": "provisioning"},
        )

    def test_transition_error_flashes(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(409, "Invalid transition"))
        resp = authed_client.post(
            f"/admin/connections/{FAKE_CONNECTION['id']}/transition",
            data={"state": "active"},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_assign_vlan(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/connections/{FAKE_CONNECTION['id']}/vlans",
            data={"vlan_id": FAKE_VLAN["id"], "tagged": "on"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        app.state.api.post.assert_called_once_with(
            f"/api/v1/connections/{FAKE_CONNECTION['id']}/vlans",
            "test-jwt",
            json={"vlan_id": FAKE_VLAN["id"], "tagged": True},
        )

    def test_assign_vlan_untagged(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/connections/{FAKE_CONNECTION['id']}/vlans",
            data={"vlan_id": FAKE_VLAN["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        # tagged should be False when checkbox not checked
        app.state.api.post.assert_called_once_with(
            f"/api/v1/connections/{FAKE_CONNECTION['id']}/vlans",
            "test-jwt",
            json={"vlan_id": FAKE_VLAN["id"], "tagged": False},
        )

    def test_unassign_vlan(self, authed_client, app):
        app.state.api.delete = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/connections/{FAKE_CONNECTION['id']}/vlans/{FAKE_VLAN['id']}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        app.state.api.delete.assert_called_once_with(
            f"/api/v1/connections/{FAKE_CONNECTION['id']}/vlans/{FAKE_VLAN['id']}",
            "test-jwt",
        )

    def test_assign_ip(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/connections/{FAKE_CONNECTION['id']}/ips",
            data={"pool_id": FAKE_IP_POOL["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        app.state.api.post.assert_called_once_with(
            f"/api/v1/connections/{FAKE_CONNECTION['id']}/ips",
            "test-jwt",
            json={"pool_id": FAKE_IP_POOL["id"]},
        )

    def test_assign_ip_with_address(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/connections/{FAKE_CONNECTION['id']}/ips",
            data={"pool_id": FAKE_IP_POOL["id"], "address": "10.0.0.5"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        app.state.api.post.assert_called_once_with(
            f"/api/v1/connections/{FAKE_CONNECTION['id']}/ips",
            "test-jwt",
            json={"pool_id": FAKE_IP_POOL["id"], "address": "10.0.0.5"},
        )

    def test_release_ip(self, authed_client, app):
        assignment_id = str(uuid.uuid4())
        app.state.api.delete = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/connections/{FAKE_CONNECTION['id']}/ips/{assignment_id}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        app.state.api.delete.assert_called_once_with(
            f"/api/v1/connections/{FAKE_CONNECTION['id']}/ips/{assignment_id}",
            "test-jwt",
        )

    def test_assign_vlan_error_flashes(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(400, "VLAN already assigned"))
        resp = authed_client.post(
            f"/admin/connections/{FAKE_CONNECTION['id']}/vlans",
            data={"vlan_id": FAKE_VLAN["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_assign_ip_error_flashes(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(400, "Pool exhausted"))
        resp = authed_client.post(
            f"/admin/connections/{FAKE_CONNECTION['id']}/ips",
            data={"pool_id": FAKE_IP_POOL["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 302
