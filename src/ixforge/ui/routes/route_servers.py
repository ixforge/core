"""Route Server UI routes: list, detail, create, edit, delete."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from starlette.responses import RedirectResponse, Response

from ixforge.ui.api_client import APIClient, APIError
from ixforge.ui.deps import require_auth
from ixforge.ui.session import add_flash, require_token, safe_detail
from ixforge.ui.templating import render

if TYPE_CHECKING:
    from starlette.requests import Request


async def _load_vlans(api: APIClient, token: str) -> list[dict[str, Any]]:
    """Load all VLANs for the form."""
    try:
        data = await api.get("/api/v1/vlans", token, params={"limit": 200})
        items: list[dict[str, Any]] = data.get("items", [])
        return items
    except APIError as e:
        if e.status_code is not None and e.status_code < 500:
            return []
        raise


async def _load_pools_for_vlan(api: APIClient, token: str, vlan_id: str) -> list[dict[str, Any]]:
    """Load pools with availability info for a specific VLAN."""
    try:
        pools: list[dict[str, Any]] = await api.get(
            "/api/v1/ip-pools/available", token,
            params={"vlan_id": vlan_id},
        )
        return pools
    except APIError as e:
        if e.status_code is not None and e.status_code < 500:
            return []
        raise


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

    # Una config sin applied_at quedo pendiente; si ademas el agent sigue con
    # heartbeat reciente, es que la rechazo (tipicamente bird -p), no que este caido
    config_pending = config_current is not None and not config_current.get("applied_at")
    agent_alive = False
    heartbeat = rs.get("last_heartbeat_at")
    if heartbeat:
        with contextlib.suppress(ValueError, AttributeError):
            hb_dt = datetime.fromisoformat(heartbeat.replace("Z", "+00:00"))
            agent_alive = datetime.now(UTC) - hb_dt < timedelta(minutes=3)

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

    # Fetch trunk VLANs for inline BGP session form
    trunks_data = await api.get("/api/v1/trunks", token, params={"limit": 200})
    trunk_vlans: list[Any] = []
    for t in trunks_data.get("items", []):
        try:
            tvs = await api.get(f"/api/v1/trunks/{t['id']}/vlans", token)
            for tv in tvs:
                tv["trunk_name"] = t.get("name", "")
                tv["member_name"] = t.get("member_name", "")
                trunk_vlans.append(tv)
        except APIError:
            pass

    return render(request, "route_servers/detail.html", {
        "rs": rs,
        "bgp_sessions": bgp_sessions,
        "config_current": config_current,
        "config_pending": config_pending,
        "agent_alive": agent_alive,
        "rs_vlans": rs_vlans_enriched,
        "available_vlans": available_vlans,
        "rs_ips": rs_ips,
        "all_pools": all_pools,
        "trunk_vlans": trunk_vlans,
        "page_title": rs.get("name", "Route Server"),
    })


@require_auth
async def route_server_new(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    if request.method == "GET":
        vlans = await _load_vlans(api, token)
        return render(request, "route_servers/form.html", {
            "rs": None,
            "errors": {},
            "vlans": vlans,
            "pools": [],
            "selected_vlan_id": "",
            "page_title": "Nuevo Route Server",
        })

    form = await request.form()

    payload: dict[str, Any] = {
        "name": str(form.get("name", "")),
        "is_active": form.get("is_active") == "on",
    }
    notes = str(form.get("notes", "")).strip()
    if notes:
        payload["notes"] = notes

    # Extract VLAN and IP data from form (not sent to RS create)
    vlan_id = str(form.get("vlan_id", "")).strip()
    ipv4 = str(form.get("ipv4", "")).strip()
    ipv6 = str(form.get("ipv6", "")).strip()
    ipv4_pool_id = str(form.get("ipv4_pool_id", "")).strip()
    ipv6_pool_id = str(form.get("ipv6_pool_id", "")).strip()

    try:
        rs = await api.post("/api/v1/route-servers", token, json=payload)
    except APIError as e:
        if e.status_code in (400, 409, 422):
            vlans = await _load_vlans(api, token)
            pools = []
            if vlan_id:
                pools = await _load_pools_for_vlan(api, token, vlan_id)
            return render(request, "route_servers/form.html", {
                "rs": payload,
                "errors": e.detail,
                "vlans": vlans,
                "pools": pools,
                "selected_vlan_id": vlan_id,
                "page_title": "Nuevo Route Server",
            })
        raise

    rs_id = rs["id"]
    warnings: list[str] = []

    # Associate VLAN
    if vlan_id:
        try:
            await api.post(f"/api/v1/route-servers/{rs_id}/vlans", token, json={"vlan_id": vlan_id})
        except APIError as e:
            warnings.append(f"VLAN: {safe_detail(e)}")

    # Assign IPs from pools
    if ipv4_pool_id:
        try:
            payload_ip: dict[str, str] = {"pool_id": ipv4_pool_id}
            if ipv4:
                payload_ip["address"] = ipv4
            await api.post(f"/api/v1/route-servers/{rs_id}/ips", token, json=payload_ip)
        except APIError as e:
            warnings.append(f"IPv4: {safe_detail(e)}")

    if ipv6_pool_id:
        try:
            payload_ip6: dict[str, str] = {"pool_id": ipv6_pool_id}
            if ipv6:
                payload_ip6["address"] = ipv6
            await api.post(f"/api/v1/route-servers/{rs_id}/ips", token, json=payload_ip6)
        except APIError as e:
            warnings.append(f"IPv6: {safe_detail(e)}")

    add_flash(request, f"Route Server '{rs['name']}' creado", "success")
    for w in warnings:
        add_flash(request, f"Advertencia: {w}", "warning")
    return RedirectResponse(f"/admin/route-servers/{rs_id}", status_code=302)


@require_auth
async def route_server_edit(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    rs_id = request.path_params["rs_id"]

    if request.method == "GET":
        rs = await api.get(f"/api/v1/route-servers/{rs_id}", token)
        return render(request, "route_servers/edit_form.html", {
            "rs": rs,
            "errors": {},
            "page_title": f"Editar {rs.get('name', 'Route Server')}",
        })

    form = await request.form()
    payload: dict[str, Any] = {}
    name_val = form.get("name")
    if name_val is not None:
        payload["name"] = str(name_val)
    notes_val = form.get("notes")
    if notes_val is not None:
        payload["notes"] = str(notes_val).strip() or None
    payload["is_active"] = form.get("is_active") == "on"

    try:
        rs = await api.patch(f"/api/v1/route-servers/{rs_id}", token, json=payload)
    except APIError as e:
        if e.status_code in (400, 409, 422):
            return render(request, "route_servers/edit_form.html", {
                "rs": {**payload, "id": rs_id},
                "errors": e.detail,
                "page_title": "Editar Route Server",
            })
        raise

    add_flash(request, "Route Server actualizado", "success")
    return RedirectResponse(f"/admin/route-servers/{rs['id']}", status_code=302)


@require_auth
async def route_server_vlan_pools(request: Request) -> Response:
    """HTMX endpoint: return IP pool info for a selected VLAN."""
    token = require_token(request)
    api: APIClient = request.app.state.api
    vlan_id = request.query_params.get("vlan_id", "").strip()

    if not vlan_id:
        return render(request, "route_servers/_ip_pools_fragment.html", {"pools": []})

    pools = await _load_pools_for_vlan(api, token, vlan_id)
    return render(request, "route_servers/_ip_pools_fragment.html", {"pools": pools})


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
async def route_server_add_bgp_session(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    rs_id = request.path_params["route_server_id"]
    form = await request.form()

    try:
        af = int(str(form.get("af", 4)))
    except (ValueError, TypeError):
        af = 4

    payload: dict[str, Any] = {
        "route_server_id": rs_id,
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
    except APIError as e:
        add_flash(request, f"Error creando sesion BGP: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/route-servers/{rs_id}", status_code=302)


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
