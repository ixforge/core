# core/tests/ui/test_session.py
"""Tests for UI session helpers and auth deps."""

from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from ixforge.ui.deps import require_auth
from ixforge.ui.session import add_flash, clear_session, get_flash_messages, get_token, set_token


class TestSessionHelpers:
    def _make_app(self, handler):
        app = Starlette(routes=[Route("/test", handler)])
        app.add_middleware(SessionMiddleware, secret_key="test-secret")
        return app

    def test_get_token_empty_session(self):
        async def handler(request: Request):
            token = get_token(request)
            return JSONResponse({"token": token})
        client = TestClient(self._make_app(handler))
        resp = client.get("/test")
        assert resp.json()["token"] is None

    def test_set_and_get_token(self):
        async def handler(request: Request):
            set_token(request, "my-jwt-123")
            token = get_token(request)
            return JSONResponse({"token": token})
        client = TestClient(self._make_app(handler))
        resp = client.get("/test")
        assert resp.json()["token"] == "my-jwt-123"

    def test_clear_session(self):
        async def set_handler(request: Request):
            set_token(request, "my-jwt")
            return PlainTextResponse("ok")
        async def clear_handler(request: Request):
            clear_session(request)
            token = get_token(request)
            return JSONResponse({"token": token})
        app = Starlette(routes=[
            Route("/set", set_handler),
            Route("/clear", clear_handler),
        ])
        app.add_middleware(SessionMiddleware, secret_key="test-secret")
        client = TestClient(app)
        client.get("/set")
        resp = client.get("/clear")
        assert resp.json()["token"] is None

    def test_flash_messages(self):
        async def handler(request: Request):
            add_flash(request, "Success!", "success")
            add_flash(request, "Warning!", "warning")
            messages = get_flash_messages(request)
            remaining = get_flash_messages(request)
            return JSONResponse({"messages": messages, "remaining": remaining})
        client = TestClient(self._make_app(handler))
        resp = client.get("/test")
        data = resp.json()
        assert len(data["messages"]) == 2
        assert data["messages"][0] == {"message": "Success!", "category": "success"}
        assert data["remaining"] == []


class TestRequireAuth:
    def test_redirects_without_token(self):
        @require_auth
        async def handler(request: Request):
            return PlainTextResponse("ok")
        app = Starlette(routes=[Route("/test", handler)])
        app.add_middleware(SessionMiddleware, secret_key="test-secret")
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/test")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"

    def test_passes_with_token(self):
        @require_auth
        async def handler(request: Request):
            return PlainTextResponse("ok")
        async def login_handler(request: Request):
            set_token(request, "valid-jwt")
            return PlainTextResponse("logged in")
        app = Starlette(routes=[
            Route("/login-helper", login_handler),
            Route("/test", handler),
        ])
        app.add_middleware(SessionMiddleware, secret_key="test-secret")
        client = TestClient(app)
        client.get("/login-helper")
        resp = client.get("/test")
        assert resp.status_code == 200
        assert resp.text == "ok"
