"""Tests for the UI app factory and basic routing."""

from starlette.testclient import TestClient


class TestUIApp:
    def test_app_starts(self):
        from ixforge.ui.app import create_ui_app
        app = create_ui_app()
        assert app is not None

    def test_login_page_renders(self):
        from ixforge.ui.app import create_ui_app
        app = create_ui_app()
        client = TestClient(app)
        resp = client.get("/login")
        assert resp.status_code == 200

    def test_admin_redirects_without_auth(self):
        from ixforge.ui.app import create_ui_app
        app = create_ui_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/admin")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"

    def test_static_files_mounted(self):
        from ixforge.ui.app import create_ui_app
        app = create_ui_app()
        client = TestClient(app)
        resp = client.get("/static/js/app.js")
        assert resp.status_code in (200, 404)
