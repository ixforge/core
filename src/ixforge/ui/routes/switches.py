"""Switch UI routes: list, detail, create, edit, delete."""

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
async def switch_list(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    is_active = request.query_params.get("is_active", "")

    data = await api.get("/api/v1/switches", token, params={"limit": 200})

    items = data.get("items", [])
    if is_active != "":
        active_bool = is_active == "true"
        items = [s for s in items if s.get("is_active") == active_bool]

    is_htmx = request.headers.get("hx-request") == "true"
    template = "switches/list_rows.html" if is_htmx else "switches/list.html"

    return render(request, template, {
        "switches": items,
        "filter_is_active": is_active,
        "page_title": "Switches",
    })


@require_auth
async def switch_detail(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    switch_id = request.path_params["switch_id"]

    try:
        switch = await api.get(f"/api/v1/switches/{switch_id}", token)
        connections_data = await api.get("/api/v1/connections", token, params={"switch_id": switch_id, "limit": 200})
    except APIError as e:
        if e.status_code == 404:
            add_flash(request, "Switch no encontrado", "error")
            return RedirectResponse("/admin/switches", status_code=302)
        raise

    # Resolve trunk names for each connection
    conn_items = connections_data.get("items", [])
    trunk_cache: dict[str, Any] = {}
    for c in conn_items:
        tid = c.get("trunk_id", "")
        if tid and tid not in trunk_cache:
            try:
                trunk_cache[tid] = await api.get(f"/api/v1/trunks/{tid}", token)
            except APIError:
                trunk_cache[tid] = {}
        trunk = trunk_cache.get(tid, {})
        c["trunk_name"] = trunk.get("name", "")
        c["member_name"] = trunk.get("member_name", "")
        c["member_id"] = trunk.get("member_id", "")

    return render(request, "switches/detail.html", {
        "switch": switch,
        "connections": conn_items,
        "page_title": switch.get("name", "Switch"),
    })


@require_auth
async def switch_new(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    locations_data = await api.get("/api/v1/locations", token, params={"limit": 200})
    locations = locations_data.get("items", [])

    if request.method == "GET":
        return render(request, "switches/form.html", {
            "switch": None,
            "locations": locations,
            "errors": {},
            "page_title": "Nuevo Switch",
        })

    form = await request.form()

    payload: dict[str, Any] = {
        "name": str(form.get("name", "")),
        "vendor": str(form.get("vendor", "")),
        "model": str(form.get("model", "")),
        "management_ip": str(form.get("management_ip", "")),
        "is_active": form.get("is_active") == "on",
    }
    location_id = str(form.get("location_id", "")).strip()
    if location_id:
        payload["location_id"] = location_id

    try:
        switch = await api.post("/api/v1/switches", token, json=payload)
    except APIError as e:
        if e.status_code in (400, 409, 422):
            return render(request, "switches/form.html", {
                "switch": payload,
                "locations": locations,
                "errors": e.detail,
                "page_title": "Nuevo Switch",
            })
        raise

    add_flash(request, f"Switch '{switch['name']}' creado", "success")
    return RedirectResponse(f"/admin/switches/{switch['id']}", status_code=302)


@require_auth
async def switch_edit(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    switch_id = request.path_params["switch_id"]
    locations_data = await api.get("/api/v1/locations", token, params={"limit": 200})
    locations = locations_data.get("items", [])

    if request.method == "GET":
        switch = await api.get(f"/api/v1/switches/{switch_id}", token)
        return render(request, "switches/form.html", {
            "switch": switch,
            "locations": locations,
            "errors": {},
            "page_title": f"Editar {switch.get('name', 'Switch')}",
        })

    form = await request.form()
    payload: dict[str, Any] = {}
    for field in ("name", "vendor", "model", "management_ip"):
        val = form.get(field)
        if val is not None:
            payload[field] = str(val)
    payload["is_active"] = form.get("is_active") == "on"
    location_id = str(form.get("location_id", "")).strip()
    payload["location_id"] = location_id if location_id else None

    try:
        switch = await api.patch(f"/api/v1/switches/{switch_id}", token, json=payload)
    except APIError as e:
        if e.status_code in (400, 409, 422):
            return render(request, "switches/form.html", {
                "switch": {**payload, "id": switch_id},
                "locations": locations,
                "errors": e.detail,
                "page_title": "Editar Switch",
            })
        raise

    add_flash(request, "Switch actualizado", "success")
    return RedirectResponse(f"/admin/switches/{switch['id']}", status_code=302)


@require_auth
async def switch_delete(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    switch_id = request.path_params["switch_id"]

    try:
        await api.delete(f"/api/v1/switches/{switch_id}", token)
        add_flash(request, "Switch eliminado", "success")
    except APIError as e:
        add_flash(request, f"Error eliminando switch: {safe_detail(e)}", "error")

    return RedirectResponse("/admin/switches", status_code=302)
