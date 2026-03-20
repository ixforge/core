"""Connection UI routes: list, create, and standalone operations."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from starlette.responses import RedirectResponse

from ixforge.ui.api_client import APIClient, APIError
from ixforge.ui.deps import require_auth
from ixforge.ui.session import add_flash, require_token, safe_detail
from ixforge.ui.templating import render

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response


@require_auth
async def connection_list(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    state_filter = request.query_params.get("state", "")

    data = await api.get("/api/v1/connections", token, params={"limit": 200})
    items: list[dict[str, Any]] = data.get("items", [])

    # Resolve switch and trunk names
    switch_cache: dict[str, dict[str, Any]] = {}
    trunk_cache: dict[str, dict[str, Any]] = {}
    for c in items:
        sid = c.get("switch_id", "")
        if sid and sid not in switch_cache:
            try:
                switch_cache[sid] = await api.get(f"/api/v1/switches/{sid}", token)
            except APIError:
                switch_cache[sid] = {}
        switch = switch_cache.get(sid, {})
        c["switch_name"] = switch.get("name", "")

        tid = c.get("trunk_id", "")
        if tid and tid not in trunk_cache:
            try:
                trunk_cache[tid] = await api.get(f"/api/v1/trunks/{tid}", token)
            except APIError:
                trunk_cache[tid] = {}
        trunk = trunk_cache.get(tid, {})
        c["trunk_name"] = trunk.get("name", "")
        c["member_name"] = trunk.get("member_name", "")

    if state_filter:
        items = [c for c in items if c.get("state") == state_filter]

    is_htmx = request.headers.get("hx-request") == "true"
    template = "connections/list_rows.html" if is_htmx else "connections/list.html"

    return render(request, template, {
        "connections": items,
        "filter_state": state_filter,
        "page_title": "Conexiones",
    })


async def _load_form_data(
    api: APIClient, token: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Load members, trunks and switches for the connection form."""
    members_data = await api.get("/api/v1/members", token, params={"limit": 200})
    members = members_data.get("items", [])
    trunks_data = await api.get("/api/v1/trunks", token, params={"limit": 200})
    trunks = trunks_data.get("items", [])
    switches_data = await api.get("/api/v1/switches", token, params={"limit": 200})
    switches = switches_data.get("items", [])
    return members, trunks, switches


def _trunks_json(trunks: list[dict[str, Any]]) -> str:
    """Serialize trunks to JSON for Alpine.js (only id, name, member_id)."""
    return json.dumps([
        {"id": t["id"], "name": t.get("name", ""), "member_id": t.get("member_id", "")}
        for t in trunks
    ])


@require_auth
async def connection_new(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    members, trunks, switches = await _load_form_data(api, token)

    if request.method == "GET":
        preselect_trunk_id = request.query_params.get("trunk_id", "")
        preselect_member_id = request.query_params.get("member_id", "")
        return render(request, "connections/form.html", {
            "connection": None,
            "members": members,
            "trunks": trunks,
            "trunks_json": _trunks_json(trunks),
            "switches": switches,
            "preselect_trunk_id": preselect_trunk_id,
            "preselect_member_id": preselect_member_id,
            "errors": {},
            "page_title": "Nueva Conexion",
        })

    form = await request.form()
    trunk_id = str(form.get("trunk_id", ""))
    payload: dict[str, Any] = {
        "switch_id": str(form.get("switch_id", "")),
        "name": str(form.get("puerto", "")),
        "type": str(form.get("type", "physical")),
        "speed": int(form.get("speed", 0) or 0),
    }
    notes = str(form.get("notes", "")).strip()
    if notes:
        payload["notes"] = notes

    try:
        await api.post(
            f"/api/v1/trunks/{trunk_id}/connections", token, json=payload,
        )
        add_flash(request, "Conexion creada", "success")
        return RedirectResponse("/admin/connections", status_code=302)
    except APIError as e:
        if e.status_code in (400, 409, 422):
            return render(request, "connections/form.html", {
                "connection": {**payload, "trunk_id": trunk_id, "member_id": str(form.get("member_id", ""))},
                "members": members,
                "trunks": trunks,
                "trunks_json": _trunks_json(trunks),
                "switches": switches,
                "preselect_trunk_id": "",
                "preselect_member_id": "",
                "errors": e.detail,
                "page_title": "Nueva Conexion",
            })
        raise


@require_auth
async def connection_transition(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    connection_id = request.path_params["connection_id"]
    form = await request.form()
    new_state = str(form.get("state", ""))

    try:
        await api.post(
            f"/api/v1/connections/{connection_id}/transition",
            token,
            json={"state": new_state},
        )
        add_flash(request, f"Estado cambiado a {new_state}", "success")
    except APIError as e:
        add_flash(request, f"Error en transicion: {safe_detail(e)}", "error")

    # Redirect back to the trunk detail if the form provides the origin
    trunk_id = str(form.get("trunk_id", ""))
    if trunk_id:
        return RedirectResponse(f"/admin/trunks/{trunk_id}", status_code=302)
    return RedirectResponse("/admin/connections", status_code=302)
