"""Dashboard route."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ixforge.ui.api_client import APIClient, APIError
from ixforge.ui.deps import require_auth
from ixforge.ui.session import require_token
from ixforge.ui.templating import render

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response


@require_auth
async def index(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    all_members = await api.get("/api/v1/members", token, params={"limit": 200})
    vlans = await api.get("/api/v1/vlans", token, params={"limit": 200})
    switches = await api.get("/api/v1/switches", token, params={"limit": 200})

    all_member_items = all_members.get("items", [])
    all_switch_items = switches.get("items", [])
    all_vlan_items = vlans.get("items", [])

    # Connections require member_id — aggregate per member
    all_connection_items: list[dict[str, Any]] = []
    for member in all_member_items:
        try:
            conn_data = await api.get(
                "/api/v1/connections", token,
                params={"member_id": member["id"], "limit": 200},
            )
            all_connection_items.extend(conn_data.get("items", []))
        except APIError:
            pass

    # Optional fetches - don't fail dashboard if these endpoints aren't available
    route_servers_items: list[dict[str, Any]] = []
    users_items: list[dict[str, Any]] = []
    events_items: list[dict[str, Any]] = []
    try:
        rs_data = await api.get("/api/v1/route-servers", token, params={"limit": 200})
        route_servers_items = rs_data.get("items", []) if isinstance(rs_data, dict) else rs_data
    except APIError:
        pass

    try:
        users_data = await api.get("/api/v1/users", token, params={"limit": 200})
        users_items = users_data.get("items", [])
    except APIError:
        pass

    try:
        events_data = await api.get("/api/v1/events", token, params={"limit": 5})
        events_items = events_data.get("items", []) if isinstance(events_data, dict) else events_data
    except APIError:
        pass

    active_members = [m for m in all_member_items if m.get("state") == "active"]
    active_switches = [s for s in all_switch_items if s.get("is_active")]
    active_connections = [c for c in all_connection_items if c.get("state") == "active"]
    active_rs = [r for r in route_servers_items if r.get("is_active")]

    return render(request, "dashboard/index.html", {
        "members": all_member_items[:5],
        "member_count": len(all_member_items),
        "active_member_count": len(active_members),
        "vlans": all_vlan_items,
        "vlan_count": len(all_vlan_items),
        "switch_count": len(all_switch_items),
        "active_switch_count": len(active_switches),
        "connection_count": len(all_connection_items),
        "active_connection_count": len(active_connections),
        "rs_count": len(route_servers_items),
        "active_rs_count": len(active_rs),
        "user_count": len(users_items),
        "events": events_items,
    })
