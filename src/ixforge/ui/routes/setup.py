"""Setup route: initial platform configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.responses import RedirectResponse, Response

from ixforge.ui.api_client import APIError
from ixforge.ui.session import add_flash
from ixforge.ui.templating import render

if TYPE_CHECKING:
    from starlette.requests import Request


async def setup_page(request: Request) -> Response:
    """GET /setup — show the setup form, or redirect to login if already configured."""
    api = request.app.state.api
    try:
        status = await api.get_public("/api/v1/setup/status")
        if status.get("configured"):
            return RedirectResponse("/login", status_code=302)
    except Exception:
        pass
    return render(request, "setup.html", {"errors": {}})


async def setup_submit(request: Request) -> Response:
    """POST /setup — submit setup form to the API."""
    form = await request.form()

    password = str(form.get("password", ""))
    password_confirm = str(form.get("password_confirm", ""))

    # Build safe form data (strip passwords for re-rendering on error)
    form_data = {k: v for k, v in form.items() if k not in ("password", "password_confirm")}

    if password != password_confirm:
        return render(request, "setup.html", {
            "errors": {"error": {"message": "Las contraseñas no coinciden"}},
            "form": form_data,
        })

    try:
        asn = int(form.get("asn", 0))
    except (ValueError, TypeError):
        asn = 0

    payload = {
        "ixp": {
            "name": str(form.get("name", "")),
            "short_name": str(form.get("short_name", "")),
            "asn": asn,
            "website": str(form.get("website", "")) or None,
            "country": str(form.get("country", "")),
            "city": str(form.get("city", "")),
        },
        "admin": {
            "full_name": str(form.get("full_name", "")),
            "email": str(form.get("email", "")),
            "password": password,
        },
    }

    api = request.app.state.api
    try:
        await api.post_public("/api/v1/setup", json=payload)
    except APIError as exc:
        if exc.status_code == 409:
            add_flash(request, "El sistema ya fue configurado", "info")
            return RedirectResponse("/login", status_code=302)
        return render(request, "setup.html", {
            "errors": exc.detail if isinstance(exc.detail, dict) else {"error": {"message": str(exc.detail)}},
            "form": form_data,
        })

    # Mark as configured in app state cache
    request.app.state.ixp_configured = True
    add_flash(request, "Instalacion completada", "success")
    return RedirectResponse("/login", status_code=302)
