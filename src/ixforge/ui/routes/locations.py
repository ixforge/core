"""Location UI routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.responses import RedirectResponse, Response

from ixforge.ui.api_client import APIClient, APIError
from ixforge.ui.deps import require_auth
from ixforge.ui.session import add_flash, require_token, safe_detail
from ixforge.ui.templating import render

if TYPE_CHECKING:
    from starlette.requests import Request


@require_auth
async def location_list(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    data = await api.get("/api/v1/locations", token, params={"limit": 200})
    return render(request, "locations/list.html", {
        "locations": data.get("items", []),
        "page_title": "Locations",
    })


@require_auth
async def location_new(request: Request) -> Response:
    if request.method == "GET":
        return render(request, "locations/form.html", {
            "location": None, "errors": {}, "page_title": "Nueva Location",
        })
    token = require_token(request)
    api: APIClient = request.app.state.api
    form = await request.form()
    payload: dict[str, Any] = {
        "name": str(form.get("name", "")),
        "city": str(form.get("city", "")) or None,
        "country": str(form.get("country", "")) or None,
    }
    try:
        loc = await api.post("/api/v1/locations", token, json=payload)
    except APIError as e:
        if e.status_code in (409, 422):
            return render(request, "locations/form.html", {
                "location": payload, "errors": e.detail, "page_title": "Nueva Location",
            })
        raise
    add_flash(request, f"Location '{loc['name']}' creada", "success")
    return RedirectResponse("/admin/locations", status_code=302)


@require_auth
async def location_edit(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    location_id = request.path_params["location_id"]
    if request.method == "GET":
        loc = await api.get(f"/api/v1/locations/{location_id}", token)
        return render(request, "locations/form.html", {
            "location": loc, "errors": {}, "page_title": f"Editar {loc.get('name', 'Location')}",
        })
    form = await request.form()
    payload: dict[str, Any] = {}
    for field in ("name", "city", "country"):
        val = form.get(field)
        if val is not None:
            payload[field] = str(val) or None
    try:
        loc = await api.patch(f"/api/v1/locations/{location_id}", token, json=payload)
    except APIError as e:
        if e.status_code in (409, 422):
            return render(request, "locations/form.html", {
                "location": {**payload, "id": location_id}, "errors": e.detail,
                "page_title": "Editar Location",
            })
        raise
    add_flash(request, "Location actualizada", "success")
    return RedirectResponse("/admin/locations", status_code=302)


@require_auth
async def location_delete(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    location_id = request.path_params["location_id"]
    try:
        await api.delete(f"/api/v1/locations/{location_id}", token)
        add_flash(request, "Location eliminada", "success")
    except APIError as e:
        add_flash(request, f"Error: {safe_detail(e)}", "error")
    return RedirectResponse("/admin/locations", status_code=302)
