"""Tests para la configuracion de cookies de sesion del portal."""

from starlette.middleware.sessions import SessionMiddleware

from ixforge.config import get_settings
from ixforge.ui.app import create_ui_app


def _session_middleware_kwargs(app):
    mw = next(m for m in app.user_middleware if m.cls is SessionMiddleware)
    return mw.kwargs


def _build_app(monkeypatch, **env: str):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    try:
        return create_ui_app()
    finally:
        get_settings.cache_clear()


def test_cookies_seguras_por_defecto(monkeypatch):
    app = _build_app(monkeypatch, IXFORGE_DEBUG="false")
    assert _session_middleware_kwargs(app)["https_only"] is True


def test_cookies_no_seguras_si_se_deshabilita(monkeypatch):
    # Deployments internos sirven el portal por HTTP plano: la cookie Secure
    # haria imposible iniciar sesion
    app = _build_app(
        monkeypatch, IXFORGE_DEBUG="false", IXFORGE_UI_SECURE_COOKIES="false",
    )
    assert _session_middleware_kwargs(app)["https_only"] is False


def test_cookies_no_seguras_en_debug(monkeypatch):
    app = _build_app(monkeypatch, IXFORGE_DEBUG="true")
    assert _session_middleware_kwargs(app)["https_only"] is False
