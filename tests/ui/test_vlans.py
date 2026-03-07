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
    app.state.api.get = AsyncMock(return_value={"id": "abc", "role": "admin", "member_id": None})
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


class TestVlanDetail:
    def test_detail_renders(self, authed_client, app):
        vlan = {**FAKE_VLAN, "type": "private"}

        async def fake_get(path, token, params=None):
            if path == f"/api/v1/vlans/{FAKE_VLAN['id']}":
                return vlan
            if path == f"/api/v1/vlans/{FAKE_VLAN['id']}/members":
                return {"items": []}
            if path == "/api/v1/members":
                return {"items": []}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/vlans/{FAKE_VLAN['id']}")
        assert resp.status_code == 200
        assert "Production Peering" in resp.text

    def test_detail_404_redirects(self, authed_client, app):
        app.state.api.get = AsyncMock(side_effect=APIError(404))
        resp = authed_client.get(f"/admin/vlans/{uuid.uuid4()}", follow_redirects=False)
        assert resp.status_code == 302

    def test_detail_production_vlan_skips_members(self, authed_client, app):
        """Production VLANs don't fetch vlan_members (only private ones do)."""
        vlan = {**FAKE_VLAN, "type": "production"}
        app.state.api.get = AsyncMock(return_value=vlan)
        resp = authed_client.get(f"/admin/vlans/{FAKE_VLAN['id']}")
        assert resp.status_code == 200


class TestVlanMemberAdd:
    def test_member_add_redirects(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value=None)
        member_id = str(uuid.uuid4())
        resp = authed_client.post(
            f"/admin/vlans/{FAKE_VLAN['id']}/members/add",
            data={"member_id": member_id},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"/admin/vlans/{FAKE_VLAN['id']}" in resp.headers["location"]
        app.state.api.post.assert_called_once_with(
            f"/api/v1/vlans/{FAKE_VLAN['id']}/members",
            "test-jwt",
            json={"member_id": member_id},
        )

    def test_member_add_empty_flashes_error(self, authed_client, app):
        resp = authed_client.post(
            f"/admin/vlans/{FAKE_VLAN['id']}/members/add",
            data={"member_id": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_member_add_api_error_flashes(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(409, "Ya asociado"))
        resp = authed_client.post(
            f"/admin/vlans/{FAKE_VLAN['id']}/members/add",
            data={"member_id": str(uuid.uuid4())},
            follow_redirects=False,
        )
        assert resp.status_code == 302


class TestVlanMemberRemove:
    def test_member_remove_redirects(self, authed_client, app):
        member_id = str(uuid.uuid4())
        app.state.api.delete = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/vlans/{FAKE_VLAN['id']}/members/{member_id}/remove",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"/admin/vlans/{FAKE_VLAN['id']}" in resp.headers["location"]
        app.state.api.delete.assert_called_once_with(
            f"/api/v1/vlans/{FAKE_VLAN['id']}/members/{member_id}",
            "test-jwt",
        )

    def test_member_remove_api_error_flashes(self, authed_client, app):
        app.state.api.delete = AsyncMock(side_effect=APIError(404, "No encontrado"))
        resp = authed_client.post(
            f"/admin/vlans/{FAKE_VLAN['id']}/members/{uuid.uuid4()}/remove",
            follow_redirects=False,
        )
        assert resp.status_code == 302


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
