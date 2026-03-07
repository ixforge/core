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
        ports_data = await api.get("/api/v1/ports", token, params={"switch_id": switch_id, "limit": 200})
    except APIError as e:
        if e.status_code == 404:
            add_flash(request, "Switch no encontrado", "error")
            return RedirectResponse("/admin/switches", status_code=302)
        raise

    return render(request, "switches/detail.html", {
        "switch": switch,
        "ports": ports_data.get("items", []),
        "page_title": switch.get("name", "Switch"),
    })


@require_auth
async def switch_new(request: Request) -> Response:
    if request.method == "GET":
        return render(request, "switches/form.html", {
            "switch": None,
            "errors": {},
            "page_title": "Nuevo Switch",
        })

    token = require_token(request)
    api: APIClient = request.app.state.api
    form = await request.form()

    payload: dict[str, Any] = {
        "name": str(form.get("name", "")),
        "hostname": str(form.get("hostname", "")),
        "vendor": str(form.get("vendor", "")),
        "model": str(form.get("model", "")),
        "management_ip": str(form.get("management_ip", "")),
        "is_active": form.get("is_active") == "on",
    }

    try:
        switch = await api.post("/api/v1/switches", token, json=payload)
    except APIError as e:
        if e.status_code == 422:
            return render(request, "switches/form.html", {
                "switch": payload,
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

    if request.method == "GET":
        switch = await api.get(f"/api/v1/switches/{switch_id}", token)
        return render(request, "switches/form.html", {
            "switch": switch,
            "errors": {},
            "page_title": f"Editar {switch.get('name', 'Switch')}",
        })

    form = await request.form()
    payload: dict[str, Any] = {}
    for field in ("name", "hostname", "vendor", "model", "management_ip"):
        val = form.get(field)
        if val is not None:
            payload[field] = str(val)
    payload["is_active"] = form.get("is_active") == "on"

    try:
        switch = await api.patch(f"/api/v1/switches/{switch_id}", token, json=payload)
    except APIError as e:
        if e.status_code == 422:
            return render(request, "switches/form.html", {
                "switch": {**payload, "id": switch_id},
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
