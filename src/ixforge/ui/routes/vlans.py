"""VLAN UI routes: list, create, edit, delete."""

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
async def vlan_list(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    filter_type = request.query_params.get("type", "")

    data = await api.get("/api/v1/vlans", token, params={"limit": 200})

    items = data.get("items", [])
    if filter_type:
        items = [v for v in items if v.get("type") == filter_type]

    is_htmx = request.headers.get("hx-request") == "true"
    template = "vlans/list_rows.html" if is_htmx else "vlans/list.html"

    return render(request, template, {
        "vlans": items,
        "filter_type": filter_type,
        "page_title": "VLANs",
    })


@require_auth
async def vlan_new(request: Request) -> Response:
    if request.method == "GET":
        return render(request, "vlans/form.html", {
            "vlan": None,
            "errors": {},
            "page_title": "Nueva VLAN",
        })

    token = require_token(request)
    api: APIClient = request.app.state.api
    form = await request.form()

    payload = {
        "name": str(form.get("name", "")),
        "vid": int(str(form.get("vid", 0)) or "0"),
        "type": str(form.get("type", "production")),
        "description": str(form.get("description", "")),
    }

    try:
        vlan = await api.post("/api/v1/vlans", token, json=payload)
    except APIError as e:
        if e.status_code == 422:
            return render(request, "vlans/form.html", {
                "vlan": payload,
                "errors": e.detail,
                "page_title": "Nueva VLAN",
            })
        raise

    add_flash(request, f"VLAN '{vlan['name']}' creada", "success")
    return RedirectResponse("/admin/vlans", status_code=302)


@require_auth
async def vlan_edit(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    vlan_id = request.path_params["vlan_id"]

    if request.method == "GET":
        try:
            vlan = await api.get(f"/api/v1/vlans/{vlan_id}", token)
        except APIError as e:
            if e.status_code == 404:
                add_flash(request, "VLAN no encontrada", "error")
                return RedirectResponse("/admin/vlans", status_code=302)
            raise
        return render(request, "vlans/form.html", {
            "vlan": vlan,
            "errors": {},
            "page_title": f"Editar {vlan.get('name', 'VLAN')}",
        })

    form = await request.form()
    payload: dict[str, Any] = {}
    for field in ("name", "type", "description"):
        val = form.get(field)
        if val is not None:
            payload[field] = str(val)
    vid_val = form.get("vid")
    if vid_val:
        payload["vid"] = int(str(vid_val))

    try:
        vlan = await api.patch(f"/api/v1/vlans/{vlan_id}", token, json=payload)
    except APIError as e:
        if e.status_code == 422:
            return render(request, "vlans/form.html", {
                "vlan": {**payload, "id": vlan_id},
                "errors": e.detail,
                "page_title": "Editar VLAN",
            })
        raise

    add_flash(request, "VLAN actualizada", "success")
    return RedirectResponse("/admin/vlans", status_code=302)


@require_auth
async def vlan_delete(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    vlan_id = request.path_params["vlan_id"]

    try:
        await api.delete(f"/api/v1/vlans/{vlan_id}", token)
        add_flash(request, "VLAN eliminada", "success")
    except APIError as e:
        add_flash(request, f"Error eliminando VLAN: {e.detail}", "error")

    return RedirectResponse("/admin/vlans", status_code=302)
