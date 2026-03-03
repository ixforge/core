"""Port UI routes: list, create, edit, delete, assign, release."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.responses import HTMLResponse, RedirectResponse, Response

from ixforge.ui.api_client import APIClient, APIError
from ixforge.ui.deps import require_auth
from ixforge.ui.session import add_flash, require_token
from ixforge.ui.templating import render

if TYPE_CHECKING:
    from starlette.requests import Request


@require_auth
async def port_options(request: Request) -> Response:
    """Return <option> elements for ports of a given switch (HTMX partial)."""
    import html as html_mod

    token = require_token(request)
    api: APIClient = request.app.state.api
    switch_id = request.query_params.get("switch_id", "")

    parts = ['<option value="">Sin puerto</option>']

    if switch_id:
        try:
            data = await api.get(
                "/api/v1/ports", token,
                params={"switch_id": switch_id, "limit": 200},
            )
            for p in data.get("items", []):
                pid = html_mod.escape(str(p["id"]))
                name = html_mod.escape(str(p["name"]))
                parts.append(f'<option value="{pid}">{name}</option>')
        except APIError:
            pass

    return HTMLResponse("".join(parts))


@require_auth
async def port_list(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    switch_id = request.query_params.get("switch_id", "")

    switches_data = await api.get("/api/v1/switches", token, params={"limit": 200})

    switches = switches_data.get("items", [])
    ports: list[Any] = []
    switch: dict[str, Any] | None = None

    if switch_id:
        try:
            switch = await api.get(f"/api/v1/switches/{switch_id}", token)
            ports_data = await api.get(
                "/api/v1/ports", token,
                params={"switch_id": switch_id, "limit": 200},
            )
            ports = ports_data.get("items", [])
        except APIError as e:
            if e.status_code == 404:
                add_flash(request, "Switch no encontrado", "error")
                return RedirectResponse("/admin/ports", status_code=302)
            raise

    # Fetch members for assign dropdown
    members_data = await api.get("/api/v1/members", token, params={"limit": 200})
    members = members_data.get("items", [])

    member_map = {m["id"]: m for m in members}

    return render(request, "ports/list.html", {
        "ports": ports,
        "switches": switches,
        "switch": switch,
        "members": members,
        "member_map": member_map,
        "filter_switch_id": switch_id,
        "page_title": "Puertos",
    })


@require_auth
async def port_new(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    if request.method == "GET":
        switch_id = request.query_params.get("switch_id", "")
        switches_data = await api.get("/api/v1/switches", token, params={"limit": 200})
        return render(request, "ports/form.html", {
            "port": None,
            "switches": switches_data.get("items", []),
            "preselected_switch_id": switch_id,
            "errors": {},
            "page_title": "Nuevo Puerto",
        })

    form = await request.form()
    payload = {
        "switch_id": str(form.get("switch_id", "")),
        "name": str(form.get("name", "")),
        "speed": int(str(form.get("speed", 0)) or 0),
        "type": str(form.get("type", "unused")),
    }

    try:
        port = await api.post("/api/v1/ports", token, json=payload)
    except APIError as e:
        if e.status_code == 422:
            switches_data = await api.get("/api/v1/switches", token, params={"limit": 200})
            return render(request, "ports/form.html", {
                "port": payload,
                "switches": switches_data.get("items", []),
                "preselected_switch_id": payload["switch_id"],
                "errors": e.detail,
                "page_title": "Nuevo Puerto",
            })
        raise

    add_flash(request, f"Puerto '{port['name']}' creado", "success")
    return RedirectResponse(f"/admin/ports?switch_id={port['switch_id']}", status_code=302)


@require_auth
async def port_edit(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    port_id = request.path_params["port_id"]

    if request.method == "GET":
        try:
            port = await api.get(f"/api/v1/ports/{port_id}", token)
            switches_data = await api.get("/api/v1/switches", token, params={"limit": 200})
        except APIError as e:
            if e.status_code == 404:
                add_flash(request, "Puerto no encontrado", "error")
                return RedirectResponse("/admin/ports", status_code=302)
            raise
        return render(request, "ports/form.html", {
            "port": port,
            "switches": switches_data.get("items", []),
            "preselected_switch_id": port.get("switch_id", ""),
            "errors": {},
            "page_title": f"Editar {port.get('name', 'Puerto')}",
        })

    form = await request.form()
    payload: dict[str, Any] = {}
    for field in ("name", "type"):
        val = form.get(field)
        if val is not None:
            payload[field] = str(val)
    speed_val = form.get("speed")
    if speed_val is not None and speed_val != "":
        payload["speed"] = int(str(speed_val))

    try:
        port = await api.patch(f"/api/v1/ports/{port_id}", token, json=payload)
    except APIError as e:
        if e.status_code == 422:
            switches_data = await api.get("/api/v1/switches", token, params={"limit": 200})
            return render(request, "ports/form.html", {
                "port": {**payload, "id": port_id},
                "switches": switches_data.get("items", []),
                "preselected_switch_id": "",
                "errors": e.detail,
                "page_title": "Editar Puerto",
            })
        raise

    add_flash(request, "Puerto actualizado", "success")
    return RedirectResponse(f"/admin/ports?switch_id={port['switch_id']}", status_code=302)


@require_auth
async def port_delete(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    port_id = request.path_params["port_id"]

    # Read switch_id from form to redirect back to switch
    form = await request.form()
    switch_id = str(form.get("switch_id", ""))

    try:
        await api.delete(f"/api/v1/ports/{port_id}", token)
        add_flash(request, "Puerto eliminado", "success")
    except APIError as e:
        add_flash(request, f"Error eliminando puerto: {e.detail}", "error")

    redirect_url = f"/admin/ports?switch_id={switch_id}" if switch_id else "/admin/ports"
    return RedirectResponse(redirect_url, status_code=302)


@require_auth
async def port_assign(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    port_id = request.path_params["port_id"]
    form = await request.form()
    member_id = str(form.get("member_id", ""))
    switch_id = str(form.get("switch_id", ""))

    try:
        await api.post(f"/api/v1/ports/{port_id}/assign", token, json={"member_id": member_id})
        add_flash(request, "Puerto asignado", "success")
    except APIError as e:
        add_flash(request, f"Error asignando puerto: {e.detail}", "error")

    redirect_url = f"/admin/ports?switch_id={switch_id}" if switch_id else "/admin/ports"
    return RedirectResponse(redirect_url, status_code=302)


@require_auth
async def port_release(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    port_id = request.path_params["port_id"]
    form = await request.form()
    switch_id = str(form.get("switch_id", ""))

    try:
        await api.post(f"/api/v1/ports/{port_id}/release", token)
        add_flash(request, "Puerto liberado", "success")
    except APIError as e:
        add_flash(request, f"Error liberando puerto: {e.detail}", "error")

    redirect_url = f"/admin/ports?switch_id={switch_id}" if switch_id else "/admin/ports"
    return RedirectResponse(redirect_url, status_code=302)
