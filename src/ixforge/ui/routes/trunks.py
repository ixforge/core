"""Trunk UI routes: list, detail, create, edit, transitions, VLAN/IP/connection management."""

from __future__ import annotations

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
async def trunk_list(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    member_id = request.query_params.get("member_id", "")
    state = request.query_params.get("state", "")

    members_data = await api.get("/api/v1/members", token, params={"limit": 200})
    members = members_data.get("items", [])
    trunks: list[Any] = []

    params: dict[str, Any] = {"limit": 200}
    if member_id:
        params["member_id"] = member_id

    try:
        data = await api.get("/api/v1/trunks", token, params=params)
        trunks = data.get("items", [])
    except APIError:
        pass

    if state:
        trunks = [t for t in trunks if t.get("state") == state]

    member_map = {m["id"]: m for m in members}

    return render(request, "trunks/list.html", {
        "trunks": trunks,
        "members": members,
        "member_map": member_map,
        "filter_member_id": member_id,
        "filter_state": state,
        "page_title": "Trunks",
    })


@require_auth
async def trunk_detail(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    trunk_id = request.path_params["trunk_id"]

    try:
        trunk = await api.get(f"/api/v1/trunks/{trunk_id}", token)
        member = await api.get(f"/api/v1/members/{trunk['member_id']}", token)
        vlans_data = await api.get("/api/v1/vlans", token, params={"limit": 200})
        trunk_vlans = await api.get(f"/api/v1/trunks/{trunk_id}/vlans", token)
        connections = await api.get(f"/api/v1/trunks/{trunk_id}/connections", token)
    except APIError as e:
        if e.status_code == 404:
            add_flash(request, "Trunk no encontrado", "error")
            return RedirectResponse("/admin/trunks", status_code=302)
        raise

    # Enrich VLAN assignments with name/vid
    vlan_map = {v["id"]: v for v in vlans_data.get("items", [])}
    for tv in trunk_vlans:
        vlan = vlan_map.get(tv.get("vlan_id", ""), {})
        tv["vlan_name"] = vlan.get("name", "")
        tv["vid"] = vlan.get("vid", "")

    # Fetch IPs for each trunk VLAN
    trunk_ips: list[Any] = []
    ip_pools: list[Any] = []
    for tv in trunk_vlans:
        tv_id = tv.get("id", "")
        try:
            ips = await api.get(
                f"/api/v1/trunks/{trunk_id}/vlans/{tv_id}/ips", token,
            )
            for ip in ips:
                ip["trunk_vlan_id"] = tv_id
                ip["vlan_name"] = tv.get("vlan_name", "")
            trunk_ips.extend(ips)
        except APIError:
            pass

        # Fetch IP pools for each assigned VLAN
        vlan_id = tv.get("vlan_id", "")
        if vlan_id:
            try:
                pools = await api.get("/api/v1/ip-pools", token, params={"vlan_id": vlan_id})
                ip_pools.extend(pools.get("items", []))
            except APIError:
                pass

    # Deduplicate pools
    seen_pools: set[str] = set()
    unique_pools: list[Any] = []
    for p in ip_pools:
        if p["id"] not in seen_pools:
            seen_pools.add(p["id"])
            unique_pools.append(p)
    ip_pools = unique_pools

    # Enrich IPs with pool network info
    pool_cache = {p["id"]: p for p in ip_pools}
    for ip in trunk_ips:
        pool_id = ip.get("pool_id", "")
        if pool_id and pool_id not in pool_cache:
            try:
                pool_cache[pool_id] = await api.get(f"/api/v1/ip-pools/{pool_id}", token)
            except APIError:
                pool_cache[pool_id] = {}
        pool = pool_cache.get(pool_id, {})
        ip["pool_network"] = pool.get("network", "")

    # Fetch BGP sessions for this trunk's VLANs
    bgp_sessions: list[Any] = []
    rs_data = await api.get("/api/v1/route-servers", token, params={"limit": 200})
    route_servers = rs_data.get("items", []) if isinstance(rs_data, dict) else rs_data
    for rs in route_servers:
        try:
            bgp_data = await api.get(
                "/api/v1/bgp-sessions", token,
                params={"route_server_id": rs["id"], "limit": 200},
            )
            for s in bgp_data.get("items", []):
                # Only include sessions belonging to this trunk's VLANs
                tv_ids = {tv["id"] for tv in trunk_vlans}
                if s.get("trunk_vlan_id") in tv_ids:
                    s["rs_name"] = rs.get("name", "")
                    bgp_sessions.append(s)
        except APIError:
            pass

    # Fetch switches for connection display
    switches_data = await api.get("/api/v1/switches", token, params={"limit": 200})
    switch_map = {s["id"]: s for s in switches_data.get("items", [])}

    trunk["vlans"] = trunk_vlans
    trunk["ips"] = trunk_ips
    trunk["connections"] = connections if isinstance(connections, list) else []

    return render(request, "trunks/detail.html", {
        "trunk": trunk,
        "member": member,
        "available_vlans": vlans_data.get("items", []),
        "ip_pools": ip_pools,
        "bgp_sessions": bgp_sessions,
        "switches": switches_data.get("items", []),
        "switch_map": switch_map,
        "page_title": f"Trunk - {trunk.get('name', '')}",
    })


@require_auth
async def trunk_new(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    if request.method == "GET":
        members_data = await api.get("/api/v1/members", token, params={"limit": 200})
        preselect_member_id = request.query_params.get("member_id", "")

        return render(request, "trunks/form.html", {
            "trunk": None,
            "members": members_data.get("items", []),
            "preselect_member_id": preselect_member_id,
            "errors": {},
            "page_title": "Nuevo Trunk",
        })

    form = await request.form()
    payload: dict[str, Any] = {
        "member_id": str(form.get("member_id", "")),
        "name": str(form.get("name", "")),
    }
    mac = str(form.get("mac_address", "")).strip()
    if mac:
        payload["mac_address"] = mac
    notes = str(form.get("notes", "")).strip()
    if notes:
        payload["notes"] = notes

    try:
        trunk = await api.post("/api/v1/trunks", token, json=payload)
    except APIError as e:
        if e.status_code in (400, 409, 422):
            members_data = await api.get("/api/v1/members", token, params={"limit": 200})

            return render(request, "trunks/form.html", {
                "trunk": payload,
                "members": members_data.get("items", []),
                "errors": e.detail,
                "page_title": "Nuevo Trunk",
            })
        raise

    add_flash(request, "Trunk creado", "success")
    return RedirectResponse(f"/admin/trunks/{trunk['id']}", status_code=302)


@require_auth
async def trunk_edit(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    trunk_id = request.path_params["trunk_id"]

    if request.method == "GET":
        trunk = await api.get(f"/api/v1/trunks/{trunk_id}", token)
        members_data = await api.get("/api/v1/members", token, params={"limit": 200})

        return render(request, "trunks/form.html", {
            "trunk": trunk,
            "members": members_data.get("items", []),
            "errors": {},
            "page_title": "Editar Trunk",
        })

    form = await request.form()
    payload: dict[str, Any] = {}
    for field in ("name", "mac_address", "notes"):
        val = form.get(field)
        if val is not None:
            payload[field] = str(val) if str(val).strip() else None

    try:
        trunk = await api.patch(f"/api/v1/trunks/{trunk_id}", token, json=payload)
    except APIError as e:
        if e.status_code in (400, 409, 422):
            members_data = await api.get("/api/v1/members", token, params={"limit": 200})

            return render(request, "trunks/form.html", {
                "trunk": {**payload, "id": trunk_id},
                "members": members_data.get("items", []),
                "errors": e.detail,
                "page_title": "Editar Trunk",
            })
        raise

    add_flash(request, "Trunk actualizado", "success")
    return RedirectResponse(f"/admin/trunks/{trunk['id']}", status_code=302)


@require_auth
async def trunk_delete(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    trunk_id = request.path_params["trunk_id"]

    try:
        await api.delete(f"/api/v1/trunks/{trunk_id}", token)
        add_flash(request, "Trunk eliminado", "success")
    except APIError as e:
        add_flash(request, f"Error eliminando trunk: {safe_detail(e)}", "error")
        return RedirectResponse(f"/admin/trunks/{trunk_id}", status_code=302)

    return RedirectResponse("/admin/trunks", status_code=302)


@require_auth
async def trunk_transition(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    trunk_id = request.path_params["trunk_id"]
    form = await request.form()
    new_state = str(form.get("state", ""))

    try:
        await api.post(
            f"/api/v1/trunks/{trunk_id}/transition",
            token,
            json={"state": new_state},
        )
        add_flash(request, f"Estado cambiado a {new_state}", "success")
    except APIError as e:
        add_flash(request, f"Error en transicion: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/trunks/{trunk_id}", status_code=302)


@require_auth
async def trunk_assign_vlan(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    trunk_id = request.path_params["trunk_id"]
    form = await request.form()

    payload = {"vlan_id": str(form.get("vlan_id", ""))}

    try:
        await api.post(f"/api/v1/trunks/{trunk_id}/vlans", token, json=payload)
        add_flash(request, "VLAN asignada", "success")
    except APIError as e:
        add_flash(request, f"Error asignando VLAN: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/trunks/{trunk_id}", status_code=302)


@require_auth
async def trunk_unassign_vlan(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    trunk_id = request.path_params["trunk_id"]
    tv_id = request.path_params["tv_id"]

    try:
        await api.delete(f"/api/v1/trunks/{trunk_id}/vlans/{tv_id}", token)
        add_flash(request, "VLAN desasignada", "success")
    except APIError as e:
        add_flash(request, f"Error desasignando VLAN: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/trunks/{trunk_id}", status_code=302)


@require_auth
async def trunk_assign_ip(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    trunk_id = request.path_params["trunk_id"]
    tv_id = request.path_params["tv_id"]
    form = await request.form()

    payload: dict[str, Any] = {"pool_id": str(form.get("pool_id", ""))}
    address = str(form.get("address", "")).strip()
    if address:
        payload["address"] = address

    try:
        await api.post(
            f"/api/v1/trunks/{trunk_id}/vlans/{tv_id}/ips", token, json=payload,
        )
        add_flash(request, "IP asignada", "success")
    except APIError as e:
        add_flash(request, f"Error asignando IP: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/trunks/{trunk_id}", status_code=302)


@require_auth
async def trunk_release_ip(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    trunk_id = request.path_params["trunk_id"]
    tv_id = request.path_params["tv_id"]
    aid = request.path_params["aid"]

    try:
        await api.delete(
            f"/api/v1/trunks/{trunk_id}/vlans/{tv_id}/ips/{aid}", token,
        )
        add_flash(request, "IP liberada", "success")
    except APIError as e:
        add_flash(request, f"Error liberando IP: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/trunks/{trunk_id}", status_code=302)


@require_auth
async def trunk_add_connection(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    trunk_id = request.path_params["trunk_id"]
    form = await request.form()

    payload: dict[str, Any] = {
        "switch_id": str(form.get("switch_id", "")),
        "name": str(form.get("name", "")),
        "type": str(form.get("type", "physical")),
        "speed": int(str(form.get("speed", 0)) or 0) if str(form.get("speed", "")).isdigit() else 0,
    }

    try:
        await api.post(f"/api/v1/trunks/{trunk_id}/connections", token, json=payload)
        add_flash(request, "Conexion agregada", "success")
    except APIError as e:
        add_flash(request, f"Error agregando conexion: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/trunks/{trunk_id}", status_code=302)


@require_auth
async def trunk_connection_transition(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    trunk_id = request.path_params["trunk_id"]
    cid = request.path_params["cid"]
    form = await request.form()
    new_state = str(form.get("state", ""))

    try:
        await api.post(
            f"/api/v1/connections/{cid}/transition",
            token,
            json={"state": new_state},
        )
        add_flash(request, f"Conexion: estado cambiado a {new_state}", "success")
    except APIError as e:
        add_flash(request, f"Error en transicion de conexion: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/trunks/{trunk_id}", status_code=302)


@require_auth
async def trunk_connection_delete(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    trunk_id = request.path_params["trunk_id"]
    cid = request.path_params["cid"]

    try:
        await api.delete(f"/api/v1/connections/{cid}", token)
        add_flash(request, "Conexion eliminada", "success")
    except APIError as e:
        add_flash(request, f"Error eliminando conexion: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/trunks/{trunk_id}", status_code=302)
