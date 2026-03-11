"""Connection UI routes: list, detail, create, edit, transitions, VLAN/IP assignment."""

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
async def connection_list(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    member_id = request.query_params.get("member_id", "")
    state = request.query_params.get("state", "")

    members_data = await api.get("/api/v1/members", token, params={"limit": 200})

    members = members_data.get("items", [])
    connections: list[Any] = []

    # Fetch connections — API requires member_id, so aggregate if none specified
    if member_id:
        try:
            data = await api.get(
                "/api/v1/connections", token,
                params={"member_id": member_id, "limit": 50},
            )
            connections = data.get("items", [])
        except APIError:
            pass
    else:
        for m in members:
            try:
                data = await api.get(
                    "/api/v1/connections", token,
                    params={"member_id": m["id"], "limit": 50},
                )
                connections.extend(data.get("items", []))
            except APIError:
                pass

    if state:
        connections = [c for c in connections if c.get("state") == state]

    # Build member lookup for display names (used by member filter dropdown)
    member_map = {m["id"]: m for m in members}

    return render(request, "connections/list.html", {
        "connections": connections,
        "members": members,
        "member_map": member_map,
        "filter_member_id": member_id,
        "filter_state": state,
        "page_title": "Conexiones",
    })


@require_auth
async def connection_detail(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    connection_id = request.path_params["connection_id"]

    try:
        connection = await api.get(f"/api/v1/connections/{connection_id}", token)
        member = await api.get(f"/api/v1/members/{connection['member_id']}", token)
        vlans_data = await api.get("/api/v1/vlans", token, params={"limit": 200})
        conn_vlans = await api.get(f"/api/v1/connections/{connection_id}/vlans", token)
        conn_ips = await api.get(f"/api/v1/connections/{connection_id}/ips", token)
    except APIError as e:
        if e.status_code == 404:
            add_flash(request, "Conexion no encontrada", "error")
            return RedirectResponse("/admin/connections", status_code=302)
        raise

    # Enrich VLAN assignments with name/vid from the full VLAN list
    vlan_map = {v["id"]: v for v in vlans_data.get("items", [])}
    for cv in conn_vlans:
        vlan = vlan_map.get(cv.get("vlan_id", ""), {})
        cv["vlan_name"] = vlan.get("name", "")
        cv["vid"] = vlan.get("vid", "")

    # Fetch IP pools for each assigned VLAN
    ip_pools: list[Any] = []
    for cv in conn_vlans:
        vlan_id = cv.get("vlan_id", "")
        if vlan_id:
            try:
                pools = await api.get("/api/v1/ip-pools", token, params={"vlan_id": vlan_id})
                ip_pools.extend(pools.get("items", []))
            except APIError:
                pass

    # Inject vlans and ips into connection dict for template
    connection["vlans"] = conn_vlans
    connection["ips"] = conn_ips

    return render(request, "connections/detail.html", {
        "connection": connection,
        "member": member,
        "available_vlans": vlans_data.get("items", []),
        "ip_pools": ip_pools,
        "page_title": f"Conexion - {member.get('name', '')}",
    })


@require_auth
async def connection_new(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    if request.method == "GET":
        members_data = await api.get("/api/v1/members", token, params={"limit": 200})
        switches_data = await api.get("/api/v1/switches", token, params={"limit": 200})

        return render(request, "connections/form.html", {
            "connection": None,
            "members": members_data.get("items", []),
            "switches": switches_data.get("items", []),
            "errors": {},
            "page_title": "Nueva Conexion",
        })

    form = await request.form()
    payload: dict[str, Any] = {
        "member_id": str(form.get("member_id", "")),
        "type": str(form.get("type", "physical")),
        "speed": int(str(form.get("speed", 0)) or 0),
        "mac_address": str(form.get("mac_address", "")),
        "switch_id": str(form.get("switch_id", "")),
        "name": str(form.get("name", "")),
    }

    try:
        connection = await api.post("/api/v1/connections", token, json=payload)
    except APIError as e:
        if e.status_code in (400, 409, 422):
            members_data = await api.get("/api/v1/members", token, params={"limit": 200})
            switches_data = await api.get("/api/v1/switches", token, params={"limit": 200})

            return render(request, "connections/form.html", {
                "connection": payload,
                "members": members_data.get("items", []),
                "switches": switches_data.get("items", []),
                "errors": e.detail,
                "page_title": "Nueva Conexion",
            })
        raise

    add_flash(request, "Conexion creada", "success")
    return RedirectResponse(f"/admin/connections/{connection['id']}", status_code=302)


@require_auth
async def connection_edit(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    connection_id = request.path_params["connection_id"]

    if request.method == "GET":
        connection = await api.get(f"/api/v1/connections/{connection_id}", token)
        members_data = await api.get("/api/v1/members", token, params={"limit": 200})
        switches_data = await api.get("/api/v1/switches", token, params={"limit": 200})

        return render(request, "connections/form.html", {
            "connection": connection,
            "members": members_data.get("items", []),
            "switches": switches_data.get("items", []),
            "errors": {},
            "page_title": "Editar Conexion",
        })

    form = await request.form()
    payload: dict[str, Any] = {}
    for field in ("type", "mac_address", "name"):
        val = form.get(field)
        if val is not None:
            payload[field] = str(val)
    speed_val = form.get("speed")
    if speed_val is not None and speed_val != "":
        payload["speed"] = int(str(speed_val))
    switch_id = str(form.get("switch_id", ""))
    if switch_id:
        payload["switch_id"] = switch_id

    try:
        connection = await api.patch(f"/api/v1/connections/{connection_id}", token, json=payload)
    except APIError as e:
        if e.status_code in (400, 409, 422):
            members_data = await api.get("/api/v1/members", token, params={"limit": 200})
            switches_data = await api.get("/api/v1/switches", token, params={"limit": 200})

            return render(request, "connections/form.html", {
                "connection": {**payload, "id": connection_id},
                "members": members_data.get("items", []),
                "switches": switches_data.get("items", []),
                "errors": e.detail,
                "page_title": "Editar Conexion",
            })
        raise

    add_flash(request, "Conexion actualizada", "success")
    return RedirectResponse(f"/admin/connections/{connection['id']}", status_code=302)


@require_auth
async def connection_delete(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    connection_id = request.path_params["connection_id"]

    try:
        await api.delete(f"/api/v1/connections/{connection_id}", token)
        add_flash(request, "Conexion eliminada", "success")
    except APIError as e:
        add_flash(request, f"Error eliminando conexion: {safe_detail(e)}", "error")
        return RedirectResponse(f"/admin/connections/{connection_id}", status_code=302)

    return RedirectResponse("/admin/connections", status_code=302)


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

    return RedirectResponse(f"/admin/connections/{connection_id}", status_code=302)


@require_auth
async def connection_assign_vlan(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    connection_id = request.path_params["connection_id"]
    form = await request.form()

    payload = {
        "vlan_id": str(form.get("vlan_id", "")),
    }

    try:
        await api.post(f"/api/v1/connections/{connection_id}/vlans", token, json=payload)
        add_flash(request, "VLAN asignada", "success")
    except APIError as e:
        add_flash(request, f"Error asignando VLAN: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/connections/{connection_id}", status_code=302)


@require_auth
async def connection_unassign_vlan(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    connection_id = request.path_params["connection_id"]
    vlan_id = request.path_params["vlan_id"]

    try:
        await api.delete(f"/api/v1/connections/{connection_id}/vlans/{vlan_id}", token)
        add_flash(request, "VLAN desasignada", "success")
    except APIError as e:
        add_flash(request, f"Error desasignando VLAN: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/connections/{connection_id}", status_code=302)


@require_auth
async def connection_assign_ip(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    connection_id = request.path_params["connection_id"]
    form = await request.form()

    payload: dict[str, Any] = {"pool_id": str(form.get("pool_id", ""))}
    address = str(form.get("address", "")).strip()
    if address:
        payload["address"] = address

    try:
        await api.post(f"/api/v1/connections/{connection_id}/ips", token, json=payload)
        add_flash(request, "IP asignada", "success")
    except APIError as e:
        add_flash(request, f"Error asignando IP: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/connections/{connection_id}", status_code=302)


@require_auth
async def connection_release_ip(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    connection_id = request.path_params["connection_id"]
    assignment_id = request.path_params["assignment_id"]

    try:
        await api.delete(
            f"/api/v1/connections/{connection_id}/ips/{assignment_id}", token,
        )
        add_flash(request, "IP liberada", "success")
    except APIError as e:
        add_flash(request, f"Error liberando IP: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/connections/{connection_id}", status_code=302)
