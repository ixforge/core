"""BGP Session UI routes: list, detail, toggle admin state."""

from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING, Any

from starlette.responses import RedirectResponse, Response

from ixforge.ui.api_client import APIClient, APIError
from ixforge.ui.deps import require_auth
from ixforge.ui.session import add_flash, require_token, safe_detail
from ixforge.ui.templating import render

if TYPE_CHECKING:
    from starlette.requests import Request


@require_auth
async def bgp_session_new(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    rs_data = await api.get("/api/v1/route-servers", token, params={"limit": 200})
    route_servers = rs_data.get("items", [])
    members_data = await api.get("/api/v1/members", token, params={"limit": 200})
    members = members_data.get("items", [])
    trunks_data = await api.get("/api/v1/trunks", token, params={"limit": 200})
    trunks = trunks_data.get("items", [])

    # Build trunk_vlans list with names for the form
    trunk_vlans = []
    for t in trunks:
        try:
            tvs = await api.get(f"/api/v1/trunks/{t['id']}/vlans", token)
            for tv in tvs:
                tv["trunk_name"] = t.get("name", "")
                tv["member_id"] = t.get("member_id", "")
                trunk_vlans.append(tv)
        except APIError:
            pass

    trunk_vlans_json = json.dumps([
        {
            "id": tv["id"],
            "trunk_name": tv.get("trunk_name", ""),
            "member_id": tv.get("member_id", ""),
            "vlan_name": tv.get("vlan_name", tv.get("name", "")),
            "vid": tv.get("vid", ""),
        }
        for tv in trunk_vlans
    ])

    if request.method == "GET":
        preselect_rs_id = request.query_params.get("route_server_id", "")
        return render(request, "bgp_sessions/form.html", {
            "bgp_session": None,
            "route_servers": route_servers,
            "members": members,
            "trunk_vlans_json": trunk_vlans_json,
            "preselect_rs_id": preselect_rs_id,
            "errors": {},
            "page_title": "Nueva Sesion BGP",
        })

    form = await request.form()
    try:
        af = int(str(form.get("af", 4)))
    except (ValueError, TypeError):
        af = 4

    payload: dict[str, Any] = {
        "route_server_id": str(form.get("route_server_id", "")),
        "trunk_vlan_id": str(form.get("trunk_vlan_id", "")),
        "af": af,
    }
    max_prefixes = str(form.get("max_prefixes", "")).strip()
    if max_prefixes:
        with contextlib.suppress(ValueError, TypeError):
            payload["max_prefixes"] = int(max_prefixes)

    try:
        await api.post("/api/v1/bgp-sessions", token, json=payload)
        add_flash(request, "Sesion BGP creada", "success")
        return RedirectResponse("/admin/bgp-sessions", status_code=302)
    except APIError as e:
        if e.status_code in (400, 409, 422):
            return render(request, "bgp_sessions/form.html", {
                "bgp_session": payload,
                "route_servers": route_servers,
                "members": members,
                "trunk_vlans_json": trunk_vlans_json,
                "preselect_rs_id": "",
                "errors": e.detail,
                "page_title": "Nueva Sesion BGP",
            })
        raise


@require_auth
async def bgp_session_list(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    route_server_id = request.query_params.get("route_server_id", "")

    # Fetch route servers for the selector
    rs_data = await api.get("/api/v1/route-servers", token, params={"limit": 200})

    route_servers = rs_data.get("items", [])
    sessions: list[Any] = []

    if route_server_id:
        try:
            data = await api.get(
                "/api/v1/bgp-sessions", token,
                params={"route_server_id": route_server_id, "limit": 200},
            )
            sessions = data.get("items", [])
        except APIError:
            pass

    return render(request, "bgp_sessions/list.html", {
        "sessions": sessions,
        "route_servers": route_servers,
        "filter_route_server_id": route_server_id,
        "page_title": "BGP Sessions",
    })


@require_auth
async def bgp_session_detail(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    session_id = request.path_params["session_id"]

    try:
        session = await api.get(f"/api/v1/bgp-sessions/{session_id}", token)
    except APIError as e:
        if e.status_code == 404:
            add_flash(request, "BGP Session no encontrada", "error")
            return RedirectResponse("/admin/bgp-sessions", status_code=302)
        raise

    # Resolve route server name
    rs_name = ""
    if session.get("route_server_id"):
        try:
            rs = await api.get(f"/api/v1/route-servers/{session['route_server_id']}", token)
            rs_name = rs.get("name", "")
        except APIError:
            pass

    # Resolve trunk+VLAN info from trunk_vlan_id
    trunk_label = ""
    trunk_id = ""
    if session.get("trunk_vlan_id"):
        # Find the trunk that owns this trunk_vlan
        try:
            trunks_data = await api.get("/api/v1/trunks", token, params={"limit": 200})
            for t in trunks_data.get("items", []):
                try:
                    tvs = await api.get(f"/api/v1/trunks/{t['id']}/vlans", token)
                    for tv in tvs:
                        if tv.get("id") == session["trunk_vlan_id"]:
                            trunk_id = t["id"]
                            member_name = t.get("member_name", "")
                            trunk_label = f"{member_name} / {t.get('name', '')}"
                            break
                except APIError:
                    pass
                if trunk_id:
                    break
        except APIError:
            pass

    return render(request, "bgp_sessions/detail.html", {
        "session": session,
        "rs_name": rs_name,
        "trunk_label": trunk_label,
        "trunk_id": trunk_id,
        "page_title": f"BGP Session - {session.get('peer_ip', '')}",
    })


@require_auth
async def bgp_session_toggle(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    session_id = request.path_params["session_id"]

    try:
        session = await api.get(f"/api/v1/bgp-sessions/{session_id}", token)
        new_state = "down" if session.get("admin_state") == "up" else "up"
        await api.patch(
            f"/api/v1/bgp-sessions/{session_id}", token,
            json={"admin_state": new_state},
        )
        add_flash(request, f"Admin state cambiado a {new_state}", "success")
    except APIError as e:
        add_flash(request, f"Error cambiando admin state: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/bgp-sessions/{session_id}", status_code=302)


@require_auth
async def bgp_session_delete(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    session_id = request.path_params["session_id"]

    try:
        await api.delete(f"/api/v1/bgp-sessions/{session_id}", token)
        add_flash(request, "BGP Session eliminada", "success")
    except APIError as e:
        add_flash(request, f"Error eliminando BGP session: {safe_detail(e)}", "error")
        return RedirectResponse(f"/admin/bgp-sessions/{session_id}", status_code=302)

    return RedirectResponse("/admin/bgp-sessions", status_code=302)
