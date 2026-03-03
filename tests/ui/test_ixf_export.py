"""Tests for IX-F export UI routes."""

from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from ixforge.ui.app import create_ui_app

FAKE_IXF_DATA = {
    "version": "1.0",
    "timestamp": "2026-01-15T10:00:00Z",
    "ixp_list": [{"shortname": "PIXAR", "name": "PatagoniaIX"}],
    "member_list": [],
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


class TestIXFExport:
    def test_view_renders_with_json(self, authed_client, app):
        app.state.api.get = AsyncMock(return_value=FAKE_IXF_DATA)
        resp = authed_client.get("/admin/ixf-export")
        assert resp.status_code == 200
        assert "IX-F Member Export" in resp.text
        assert "PatagoniaIX" in resp.text
        assert "Descargar JSON" in resp.text

    def test_view_requires_auth(self):
        app = create_ui_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/admin/ixf-export")
        assert resp.status_code == 302
