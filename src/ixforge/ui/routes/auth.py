"""Auth routes: login and logout."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from starlette.responses import RedirectResponse, Response

from ixforge.ui.api_client import APIError, AuthenticationError
from ixforge.ui.session import (
    add_flash,
    clear_session,
    get_role,
    set_role,
    set_session_member_id,
    set_token,
)
from ixforge.ui.templating import render

_log = structlog.get_logger()

if TYPE_CHECKING:
    from starlette.requests import Request


async def login_page(request: Request) -> Response:
    return render(request, "auth/login.html", {"error": None})


async def login_submit(request: Request) -> Response:
    form = await request.form()
    email = form.get("email", "")
    password = form.get("password", "")

    if not email or not password:
        return render(request, "auth/login.html", {"error": "Email y password son requeridos"})

    try:
        api = request.app.state.api
        token = await api.login(str(email), str(password))
    except AuthenticationError:
        return render(request, "auth/login.html", {"error": "Email o password incorrectos"})
    except APIError as exc:
        if exc.status_code >= 500:
            return render(request, "auth/login.html", {"error": "Error del servidor, intenta de nuevo mas tarde"})
        return render(request, "auth/login.html", {"error": "Error de validacion, verifica tus datos"})

    request.session.clear()
    set_token(request, token)
    # Fetch user info to store role in session
    try:
        me = await api.get("/api/v1/users/me", token)
        role = me.get("role")
        if role is None:
            clear_session(request)
            return render(request, "auth/login.html", {"error": "Error al obtener datos del usuario"})
        set_role(request, role)
        set_session_member_id(request, me.get("member_id"))
    except Exception:
        _log.warning("login.get_me_failed", exc_info=True)
        clear_session(request)
        return render(request, "auth/login.html", {"error": "Error al obtener datos del usuario, intenta de nuevo"})

    add_flash(request, "Sesion iniciada", "success")
    redirect_url = "/portal/dashboard" if get_role(request) == "member" else "/admin"
    return RedirectResponse(redirect_url, status_code=302)


async def logout(request: Request) -> Response:
    clear_session(request)
    add_flash(request, "Sesion cerrada", "info")
    return RedirectResponse("/login", status_code=302)
