"""Route Server UI routes: list, detail, create, edit, delete."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from starlette.responses import RedirectResponse, Response

from ixforge.ui.api_client import APIClient, APIError
from ixforge.ui.deps import require_auth
from ixforge.ui.session import add_flash, require_token, safe_detail
from ixforge.ui.templating import render

if TYPE_CHECKING:
    from starlette.requests import Request


@require_auth
async def route_server_list(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    is_active = request.query_params.get("is_active", "")

    data = await api.get("/api/v1/route-servers", token, params={"limit": 200})

    items = data.get("items", [])
    if is_active != "":
        active_bool = is_active == "true"
        items = [r for r in items if r.get("is_active") == active_bool]

    is_htmx = request.headers.get("hx-request") == "true"
    template = "route_servers/list_rows.html" if is_htmx else "route_servers/list.html"

    return render(request, template, {
        "route_servers": items,
        "filter_is_active": is_active,
        "page_title": "Route Servers",
    })


@require_auth
async def route_server_detail(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    rs_id = request.path_params["rs_id"]

    try:
        rs = await api.get(f"/api/v1/route-servers/{rs_id}", token)
    except APIError as e:
        if e.status_code == 404:
            add_flash(request, "Route Server no encontrado", "error")
            return RedirectResponse("/admin/route-servers", status_code=302)
        raise

    # Fetch BGP sessions for this RS
    bgp_sessions: list[Any] = []
    try:
        sessions_data = await api.get(
            "/api/v1/bgp-sessions", token,
            params={"route_server_id": rs_id, "limit": 200},
        )
        bgp_sessions = sessions_data.get("items", [])
    except APIError:
        pass

    # Fetch config status
    config_current = None
    with contextlib.suppress(APIError):
        config_current = await api.get(f"/api/v1/route-servers/{rs_id}/config/current", token)

    # Fetch RS VLANs and all available VLANs
    rs_vlans: list[Any] = []
    all_vlans: list[Any] = []
    with contextlib.suppress(APIError):
        rs_vlans_data = await api.get(f"/api/v1/route-servers/{rs_id}/vlans", token, params={"limit": 200})
        rs_vlans = rs_vlans_data.get("items", [])
    with contextlib.suppress(APIError):
        all_vlans_data = await api.get("/api/v1/vlans", token, params={"limit": 200})
        all_vlans = all_vlans_data.get("items", [])

    # Build set of already-associated vlan IDs to filter dropdown
    associated_vlan_ids = {v["vlan_id"] for v in rs_vlans}
    available_vlans = [v for v in all_vlans if v["id"] not in associated_vlan_ids]

    vlan_map = {v["id"]: v for v in all_vlans}
    rs_vlans_enriched = [
        {
            **rv,
            "vlan_name": vlan_map.get(rv["vlan_id"], {}).get("name", str(rv["vlan_id"])),
            "vlan_vid": vlan_map.get(rv["vlan_id"], {}).get("vid", ""),
        }
        for rv in rs_vlans
    ]

    # Fetch RS IP assignments
    rs_ips: list[Any] = []
    with contextlib.suppress(APIError):
        rs_ips = await api.get(f"/api/v1/route-servers/{rs_id}/ips", token)

    # Fetch all pools for dropdown (iterate over VLANs since ip-pools requires vlan_id)
    all_pools: list[Any] = []
    for vlan in all_vlans:
        with contextlib.suppress(APIError):
            pools_data = await api.get(
                "/api/v1/ip-pools", token,
                params={"vlan_id": vlan["id"], "limit": 200},
            )
            for pool in pools_data.get("items", []):
                pool["vlan_name"] = vlan.get("name", "")
                pool["vlan_vid"] = vlan.get("vid", "")
            all_pools.extend(pools_data.get("items", []))

    return render(request, "route_servers/detail.html", {
        "rs": rs,
        "bgp_sessions": bgp_sessions,
        "config_current": config_current,
        "rs_vlans": rs_vlans_enriched,
        "available_vlans": available_vlans,
        "rs_ips": rs_ips,
        "all_pools": all_pools,
        "page_title": rs.get("name", "Route Server"),
    })


@require_auth
async def route_server_new(request: Request) -> Response:
    if request.method == "GET":
        return render(request, "route_servers/form.html", {
            "rs": None,
            "errors": {},
            "page_title": "Nuevo Route Server",
        })

    token = require_token(request)
    api: APIClient = request.app.state.api
    form = await request.form()

    payload: dict[str, Any] = {
        "name": str(form.get("name", "")),
        "hostname": str(form.get("hostname", "")),
        "asn": int(str(form.get("asn", 0)) or 0),
        "software": str(form.get("software", "bird")),
        "is_active": form.get("is_active") == "on",
    }
    for field in ("ip_v4", "ip_v6"):
        val = str(form.get(field, "")).strip()
        if val:
            payload[field] = val

    try:
        rs = await api.post("/api/v1/route-servers", token, json=payload)
    except APIError as e:
        if e.status_code in (400, 409, 422):
            return render(request, "route_servers/form.html", {
                "rs": payload,
                "errors": e.detail,
                "page_title": "Nuevo Route Server",
            })
        raise

    add_flash(request, f"Route Server '{rs['name']}' creado", "success")
    return RedirectResponse(f"/admin/route-servers/{rs['id']}", status_code=302)


@require_auth
async def route_server_edit(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    rs_id = request.path_params["rs_id"]

    if request.method == "GET":
        rs = await api.get(f"/api/v1/route-servers/{rs_id}", token)
        return render(request, "route_servers/form.html", {
            "rs": rs,
            "errors": {},
            "page_title": f"Editar {rs.get('name', 'Route Server')}",
        })

    form = await request.form()
    payload: dict[str, Any] = {}
    for field in ("name", "hostname", "software", "ip_v4", "ip_v6"):
        val = form.get(field)
        if val is not None:
            payload[field] = str(val)
    asn_val = form.get("asn")
    if asn_val and str(asn_val).strip():
        payload["asn"] = int(str(asn_val))
    payload["is_active"] = form.get("is_active") == "on"

    try:
        rs = await api.patch(f"/api/v1/route-servers/{rs_id}", token, json=payload)
    except APIError as e:
        if e.status_code in (400, 409, 422):
            return render(request, "route_servers/form.html", {
                "rs": {**payload, "id": rs_id},
                "errors": e.detail,
                "page_title": "Editar Route Server",
            })
        raise

    add_flash(request, "Route Server actualizado", "success")
    return RedirectResponse(f"/admin/route-servers/{rs['id']}", status_code=302)


@require_auth
async def route_server_delete(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    rs_id = request.path_params["rs_id"]

    try:
        await api.delete(f"/api/v1/route-servers/{rs_id}", token)
        add_flash(request, "Route Server eliminado", "success")
    except APIError as e:
        add_flash(request, f"Error eliminando Route Server: {safe_detail(e)}", "error")

    return RedirectResponse("/admin/route-servers", status_code=302)


@require_auth
async def route_server_config_generate(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    rs_id = request.path_params["rs_id"]

    try:
        await api.post(f"/api/v1/route-servers/{rs_id}/config/generate", token)
        add_flash(request, "Configuracion generada", "success")
    except APIError as e:
        add_flash(request, f"Error generando configuracion: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/route-servers/{rs_id}", status_code=302)


@require_auth
async def route_server_config_history(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    rs_id = request.path_params["rs_id"]

    try:
        rs = await api.get(f"/api/v1/route-servers/{rs_id}", token)
        history = await api.get(f"/api/v1/route-servers/{rs_id}/config/history", token)
    except APIError as e:
        if e.status_code == 404:
            add_flash(request, "Route Server no encontrado", "error")
            return RedirectResponse("/admin/route-servers", status_code=302)
        raise

    items = history.get("items", []) if isinstance(history, dict) else history

    return render(request, "route_servers/config_history.html", {
        "rs": rs,
        "configs": items,
        "page_title": f"Config Historial - {rs.get('name', '')}",
    })


@require_auth
async def route_server_config_diff(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    rs_id = request.path_params["rs_id"]

    from_id = request.query_params.get("from", "")
    to_id = request.query_params.get("to", "")

    try:
        rs = await api.get(f"/api/v1/route-servers/{rs_id}", token)
        params: dict[str, Any] = {}
        if from_id:
            params["from"] = from_id
        if to_id:
            params["to"] = to_id
        diff = await api.get(f"/api/v1/route-servers/{rs_id}/config/diff", token, params=params)
    except APIError as e:
        if e.status_code == 404:
            add_flash(request, "Diff no disponible", "error")
            return RedirectResponse(f"/admin/route-servers/{rs_id}/config/history", status_code=302)
        raise

    return render(request, "route_servers/config_diff.html", {
        "rs": rs,
        "diff": diff,
        "page_title": f"Config Diff - {rs.get('name', '')}",
    })


@require_auth
async def rs_vlan_add(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    rs_id = request.path_params["rs_id"]
    form = await request.form()
    vlan_id = str(form.get("vlan_id", "")).strip()

    if not vlan_id:
        add_flash(request, "Debe seleccionar una VLAN", "error")
        return RedirectResponse(f"/admin/route-servers/{rs_id}", status_code=302)

    try:
        await api.post(f"/api/v1/route-servers/{rs_id}/vlans", token, json={"vlan_id": vlan_id})
        add_flash(request, "VLAN asociada al Route Server", "success")
    except APIError as e:
        add_flash(request, f"Error asociando VLAN: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/route-servers/{rs_id}", status_code=302)


@require_auth
async def rs_vlan_remove(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    rs_id = request.path_params["rs_id"]
    vlan_id = request.path_params["vlan_id"]

    try:
        await api.delete(f"/api/v1/route-servers/{rs_id}/vlans/{vlan_id}", token)
        add_flash(request, "VLAN desasociada del Route Server", "success")
    except APIError as e:
        add_flash(request, f"Error desasociando VLAN: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/route-servers/{rs_id}", status_code=302)


@require_auth
async def rs_ip_assign(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    rs_id = request.path_params["rs_id"]
    form = await request.form()

    pool_id = str(form.get("pool_id", "")).strip()
    if not pool_id:
        add_flash(request, "Debe seleccionar un pool", "error")
        return RedirectResponse(f"/admin/route-servers/{rs_id}", status_code=302)

    payload: dict[str, Any] = {"pool_id": pool_id}
    address = str(form.get("address", "")).strip()
    if address:
        payload["address"] = address

    try:
        await api.post(f"/api/v1/route-servers/{rs_id}/ips", token, json=payload)
        add_flash(request, "IP asignada al Route Server", "success")
    except APIError as e:
        add_flash(request, f"Error asignando IP: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/route-servers/{rs_id}", status_code=302)


@require_auth
async def rs_ip_release(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    rs_id = request.path_params["rs_id"]
    assignment_id = request.path_params["assignment_id"]

    try:
        await api.delete(f"/api/v1/route-servers/{rs_id}/ips/{assignment_id}", token)
        add_flash(request, "IP liberada", "success")
    except APIError as e:
        add_flash(request, f"Error liberando IP: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/route-servers/{rs_id}", status_code=302)
