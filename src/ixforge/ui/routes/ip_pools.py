"""IP Pool UI routes: list, detail, create, delete."""

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
async def ip_pool_list(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    vlan_id = request.query_params.get("vlan_id", "")

    vlans_data = await api.get("/api/v1/vlans", token, params={"limit": 200})

    vlans = vlans_data.get("items", [])
    pools: list[Any] = []

    if vlan_id:
        data = await api.get("/api/v1/ip-pools", token, params={"vlan_id": vlan_id})
        pools = data.get("items", [])

    vlan_map = {v["id"]: v for v in vlans}

    return render(request, "ip_pools/list.html", {
        "pools": pools,
        "vlans": vlans,
        "vlan_map": vlan_map,
        "filter_vlan_id": vlan_id,
        "page_title": "Pools de IPs",
    })


@require_auth
async def ip_pool_detail(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    pool_id = request.path_params["pool_id"]

    try:
        pool = await api.get(f"/api/v1/ip-pools/{pool_id}", token)
        assignments_data = await api.get(f"/api/v1/ip-pools/{pool_id}/assignments", token)
        vlans_data = await api.get("/api/v1/vlans", token, params={"limit": 200})
    except APIError as e:
        if e.status_code == 404:
            add_flash(request, "Pool no encontrado", "error")
            return RedirectResponse("/admin/ip-pools", status_code=302)
        raise

    vlan_map = {v["id"]: v for v in vlans_data.get("items", [])}
    assignments = assignments_data.get("items", []) if isinstance(assignments_data, dict) else assignments_data

    # Resolve trunk_vlan_ids to readable labels
    trunk_vlan_map: dict[str, Any] = {}
    tv_ids = {a["trunk_vlan_id"] for a in assignments if a.get("trunk_vlan_id")}
    if tv_ids:
        # Fetch all trunks and find matching trunk_vlans
        try:
            trunks_data = await api.get("/api/v1/trunks", token, params={"limit": 200})
            for t in trunks_data.get("items", []):
                try:
                    tvs = await api.get(f"/api/v1/trunks/{t['id']}/vlans", token)
                    for tv in tvs:
                        if tv.get("id") in tv_ids:
                            member_name = t.get("member_name", "")
                            trunk_name = t.get("name", "")
                            vlan_name = tv.get("vlan_name", "")
                            label = f"{member_name} / {trunk_name}"
                            if vlan_name:
                                label += f" ({vlan_name})"
                            trunk_vlan_map[tv["id"]] = {
                                "label": label,
                                "trunk_id": t["id"],
                            }
                except APIError:
                    pass
        except APIError:
            pass

    return render(request, "ip_pools/detail.html", {
        "pool": pool,
        "assignments": assignments,
        "vlan_map": vlan_map,
        "trunk_vlan_map": trunk_vlan_map,
        "page_title": f"Pool {pool.get('network', '')}",
    })


@require_auth
async def ip_pool_new(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    if request.method == "GET":
        preset_vlan_id = request.query_params.get("vlan_id", "")
        vlans_data = await api.get("/api/v1/vlans", token, params={"limit": 200})

        return render(request, "ip_pools/form.html", {
            "pool": None,
            "vlans": vlans_data.get("items", []),
            "preset_vlan_id": preset_vlan_id,
            "errors": {},
            "page_title": "Nuevo Pool de IPs",
        })

    form = await request.form()
    payload = {
        "vlan_id": str(form.get("vlan_id", "")),
        "network": str(form.get("network", "")),
        "af": int(str(form.get("af", 4)) or 4),
    }

    try:
        await api.post("/api/v1/ip-pools", token, json=payload)
    except APIError as e:
        if e.status_code in (400, 404, 409, 422):
            vlans_data = await api.get("/api/v1/vlans", token, params={"limit": 200})

            return render(request, "ip_pools/form.html", {
                "pool": payload,
                "vlans": vlans_data.get("items", []),
                "preset_vlan_id": payload["vlan_id"],
                "errors": e.detail,
                "page_title": "Nuevo Pool de IPs",
            })
        raise

    add_flash(request, f"Pool {payload['network']} creado", "success")
    return RedirectResponse(f"/admin/ip-pools?vlan_id={payload['vlan_id']}", status_code=302)


@require_auth
async def ip_pool_delete(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    pool_id = request.path_params["pool_id"]

    # Fetch pool first to get vlan_id for redirect
    vlan_id = ""
    try:
        pool = await api.get(f"/api/v1/ip-pools/{pool_id}", token)
        vlan_id = pool.get("vlan_id", "")
    except APIError:
        pass

    try:
        await api.delete(f"/api/v1/ip-pools/{pool_id}", token)
        add_flash(request, "Pool eliminado", "success")
    except APIError as e:
        add_flash(request, f"Error eliminando pool: {safe_detail(e)}", "error")

    redirect_url = f"/admin/ip-pools?vlan_id={vlan_id}" if vlan_id else "/admin/ip-pools"
    return RedirectResponse(redirect_url, status_code=302)
