"""Tests for contacts UI routes (nested in members)."""

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

FAKE_CONTACT = {
    "id": str(uuid.uuid4()),
    "member_id": FAKE_MEMBER["id"],
    "name": "John Doe",
    "email": "john@acme.example.net",
    "phone": "+1234567890",
    "role": "noc",
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


class TestContactsInMemberDetail:
    def test_member_detail_shows_contacts(self, authed_client, app):
        async def fake_get(path, token, params=None):
            if path == f"/api/v1/members/{FAKE_MEMBER['id']}":
                return FAKE_MEMBER
            if path == "/api/v1/connections":
                return {"items": []}
            if path.endswith("/contacts"):
                return {"items": [FAKE_CONTACT]}
            return {}

        app.state.api.get = AsyncMock(side_effect=fake_get)
        resp = authed_client.get(f"/admin/members/{FAKE_MEMBER['id']}")
        assert resp.status_code == 200
        assert "John Doe" in resp.text
        assert "john@acme.example.net" in resp.text


class TestContactCreate:
    def test_create_contact_redirects(self, authed_client, app):
        app.state.api.post = AsyncMock(return_value={**FAKE_CONTACT})
        resp = authed_client.post(
            f"/admin/members/{FAKE_MEMBER['id']}/contacts/new",
            data={"name": "John Doe", "email": "john@acme.example.net", "phone": "+1234567890", "role": "noc"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"/admin/members/{FAKE_MEMBER['id']}" in resp.headers["location"]
        app.state.api.post.assert_called_once_with(
            f"/api/v1/members/{FAKE_MEMBER['id']}/contacts",
            "test-jwt",
            json={"name": "John Doe", "email": "john@acme.example.net", "phone": "+1234567890", "role": "noc"},
        )

    def test_create_contact_error_flashes(self, authed_client, app):
        app.state.api.post = AsyncMock(side_effect=APIError(422, "Invalid email"))
        resp = authed_client.post(
            f"/admin/members/{FAKE_MEMBER['id']}/contacts/new",
            data={"name": "", "email": "", "phone": "", "role": "noc"},
            follow_redirects=False,
        )
        assert resp.status_code == 302


class TestContactEdit:
    def test_edit_contact_redirects(self, authed_client, app):
        app.state.api.patch = AsyncMock(return_value={**FAKE_CONTACT})
        resp = authed_client.post(
            f"/admin/contacts/{FAKE_CONTACT['id']}/edit",
            data={"name": "Jane Doe", "email": "jane@acme.example.net", "member_id": FAKE_MEMBER["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"/admin/members/{FAKE_MEMBER['id']}" in resp.headers["location"]


class TestContactDelete:
    def test_delete_contact_redirects(self, authed_client, app):
        app.state.api.delete = AsyncMock(return_value=None)
        resp = authed_client.post(
            f"/admin/contacts/{FAKE_CONTACT['id']}/delete",
            data={"member_id": FAKE_MEMBER["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"/admin/members/{FAKE_MEMBER['id']}" in resp.headers["location"]
        app.state.api.delete.assert_called_once_with(
            f"/api/v1/contacts/{FAKE_CONTACT['id']}",
            "test-jwt",
        )

    def test_delete_contact_error_flashes(self, authed_client, app):
        app.state.api.delete = AsyncMock(side_effect=APIError(404, "Not found"))
        resp = authed_client.post(
            f"/admin/contacts/{FAKE_CONTACT['id']}/delete",
            data={"member_id": FAKE_MEMBER["id"]},
            follow_redirects=False,
        )
        assert resp.status_code == 302
