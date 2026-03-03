"""Auth routes: login and logout."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.responses import RedirectResponse, Response

from ixforge.ui.api_client import APIError, AuthenticationError
from ixforge.ui.session import add_flash, clear_session, set_token
from ixforge.ui.templating import render

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
    except APIError:
        return render(request, "auth/login.html", {"error": "Error de validacion, verifica tus datos"})

    set_token(request, token)
    add_flash(request, "Sesion iniciada", "success")
    return RedirectResponse("/admin", status_code=302)


async def logout(request: Request) -> Response:
    clear_session(request)
    add_flash(request, "Sesion cerrada", "info")
    return RedirectResponse("/login", status_code=302)
