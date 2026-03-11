"""Tests for members UI routes."""

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
    "website": "https://acme.example.net",
    "peeringdb_id": None,
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


class TestMembersList:
    def test_list_renders(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={
            "items": [FAKE_MEMBER], "next_cursor": None, "has_more": False,
        })
        resp = authed_client.get("/admin/members")
        assert resp.status_code == 200
        assert "Acme Networks" in resp.text

    def test_list_requires_auth(self):
        app = create_ui_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/admin/members")
        assert resp.status_code == 302

    def test_list_empty_shows_empty_state(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={
            "items": [], "next_cursor": None, "has_more": False,
        })
        resp = authed_client.get("/admin/members")
        assert resp.status_code == 200


class TestMemberDetail:
    def test_detail_renders(self, authed_client, app):
        app.state.api.get = AsyncMock(side_effect=[
            FAKE_MEMBER,
            {"items": [], "next_cursor": None, "has_more": False},
            {"items": []},  # contacts
        ])
        resp = authed_client.get(f"/admin/members/{FAKE_MEMBER['id']}")
        assert resp.status_code == 200
        assert "Acme Networks" in resp.text
        assert "AS64512" in resp.text

    def test_detail_404_redirects(self, authed_client, app):
        app.state.api.get = AsyncMock(side_effect=APIError(404))
        resp = authed_client.get(f"/admin/members/{uuid.uuid4()}", follow_redirects=False)
        assert resp.status_code == 302


class TestMemberForm:
    def test_new_form_renders(self, authed_client, app):
        resp = authed_client.get("/admin/members/new")
        assert resp.status_code == 200
        assert "name" in resp.text.lower()

    def test_create_member_redirects(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value={**FAKE_MEMBER})
        resp = authed_client.post(
            "/admin/members/new",
            data={"name": "Test", "short_name": "TST", "asn": "64500", "peering_policy": "open"},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_create_validation_error_shows_form(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(422, {"error": {"code": "VALIDATION_ERROR", "message": "Validation error", "details": [{"msg": "required"}]}}))
        resp = authed_client.post(
            "/admin/members/new",
            data={"name": "", "short_name": "", "asn": "0", "peering_policy": "open"},
        )
        assert resp.status_code == 200

    def test_edit_form_renders(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value=FAKE_MEMBER)
        resp = authed_client.get(f"/admin/members/{FAKE_MEMBER['id']}/edit")
        assert resp.status_code == 200
        assert "Acme Networks" in resp.text

    def test_edit_submit_redirects(self, authed_client, app):
        app.state.api.patch = AsyncMock(return_value={**FAKE_MEMBER})
        resp = authed_client.post(
            f"/admin/members/{FAKE_MEMBER['id']}/edit",
            data={"name": "Acme Updated", "short_name": "ACME", "peering_policy": "selective"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert FAKE_MEMBER["id"] in resp.headers["location"]


class TestAsnNameFragment:
    def test_valid_asn_returns_name(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={"asn": 64512, "name": "Acme Networks"})
        resp = authed_client.get("/admin/asn-name?asn=64512")
        assert resp.status_code == 200
        assert "AS64512" in resp.text
        assert "Acme Networks" in resp.text

    def test_invalid_asn_returns_fallback(self, authed_client, app):
        resp = authed_client.get("/admin/asn-name?asn=abc")
        assert resp.status_code == 200
        assert "ASabc" in resp.text

    def test_empty_asn_returns_question_mark(self, authed_client, app):
        resp = authed_client.get("/admin/asn-name?asn=")
        assert resp.status_code == 200
        assert "AS?" in resp.text

    def test_xss_in_asn_is_escaped(self, authed_client, app):
        resp = authed_client.get("/admin/asn-name?asn=<script>alert(1)</script>")
        assert resp.status_code == 200
        assert "<script>" not in resp.text
        assert "&lt;script&gt;" in resp.text

    def test_xss_in_api_name_is_escaped(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value={
            "asn": 64512, "name": '<img src=x onerror="alert(1)">',
        })
        resp = authed_client.get("/admin/asn-name?asn=64512")
        assert resp.status_code == 200
        assert "<img" not in resp.text
        assert "&lt;img" in resp.text

    def test_api_error_returns_fallback(self, authed_client, app):
        app.state.api.get = AsyncMock(side_effect=APIError(500))
        resp = authed_client.get("/admin/asn-name?asn=64512")
        assert resp.status_code == 200
        assert "AS64512" in resp.text


class TestMemberAsnName:
    def test_returns_asn_name(self, authed_client, app):
        member_id = FAKE_MEMBER["id"]
        app.state.api.get = AsyncMock(return_value={"asn": 64512, "name": "Acme Networks"})
        resp = authed_client.get(f"/admin/members/{member_id}/asn-name")
        assert resp.status_code == 200
        assert "AS64512" in resp.text
        assert "Acme Networks" in resp.text

    def test_api_error_returns_fallback(self, authed_client, app):
        member_id = FAKE_MEMBER["id"]
        app.state.api.get = AsyncMock(side_effect=APIError(404))
        resp = authed_client.get(f"/admin/members/{member_id}/asn-name")
        assert resp.status_code == 200
        assert "AS?" in resp.text

    def test_xss_in_api_response_is_escaped(self, authed_client, app):
        member_id = FAKE_MEMBER["id"]
        app.state.api.get = AsyncMock(return_value={
            "asn": "<script>alert(1)</script>",
            "name": '<img src=x onerror="alert(1)">',
        })
        resp = authed_client.get(f"/admin/members/{member_id}/asn-name")
        assert resp.status_code == 200
        assert "<script>" not in resp.text
        assert "<img" not in resp.text


class TestMemberTransition:
    def test_transition_redirects(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/members/{FAKE_MEMBER['id']}/transition",
            data={"state": "suspended"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert FAKE_MEMBER["id"] in resp.headers["location"]
        app.state.api.post.assert_called_once_with(
            f"/api/v1/members/{FAKE_MEMBER['id']}/transition",
            "test-jwt",
            json={"state": "suspended"},
        )

    def test_transition_error_flashes(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(400, "Transicion invalida"))
        resp = authed_client.post(
            f"/admin/members/{FAKE_MEMBER['id']}/transition",
            data={"state": "invalid"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
