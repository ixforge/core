"""Settings UI routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.responses import RedirectResponse, Response

from ixforge.ui.api_client import APIClient, APIError
from ixforge.ui.deps import require_auth
from ixforge.ui.session import add_flash, require_token
from ixforge.ui.templating import render

if TYPE_CHECKING:
    from starlette.requests import Request


@require_auth
async def settings_edit(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    if request.method == "GET":
        ixp = await api.get("/api/v1/ixp", token)
        return render(request, "settings/edit.html", {
            "ixp": ixp, "errors": {}, "page_title": "Configuración IXP",
        })

    form = await request.form()
    payload: dict[str, Any] = {}
    for field in ("name", "website", "country", "city", "peeringdb_id"):
        val = form.get(field)
        if val is not None:
            payload[field] = str(val) or None
    if payload.get("peeringdb_id"):
        try:
            payload["peeringdb_id"] = int(payload["peeringdb_id"])
        except ValueError:
            payload.pop("peeringdb_id")

    try:
        await api.patch("/api/v1/ixp", token, json=payload)
    except APIError as e:
        if e.status_code in (400, 409, 422):
            ixp = await api.get("/api/v1/ixp", token)
            return render(request, "settings/edit.html", {
                "ixp": {**ixp, **payload}, "errors": e.detail, "page_title": "Configuración IXP",
            })
        raise

    add_flash(request, "Configuración guardada", "success")
    return RedirectResponse("/admin/settings", status_code=302)
