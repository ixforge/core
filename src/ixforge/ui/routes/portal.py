"""Member portal routes (read-only, role=member only)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.responses import RedirectResponse, Response

from ixforge.ui.deps import require_portal_auth
from ixforge.ui.session import get_session_member_id, require_token
from ixforge.ui.templating import render

if TYPE_CHECKING:
    from starlette.requests import Request

    from ixforge.ui.api_client import APIClient


@require_portal_auth
async def portal_redirect(request: Request) -> Response:
    return RedirectResponse("/portal/dashboard", status_code=302)


@require_portal_auth
async def portal_dashboard(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    member_id = get_session_member_id(request)
    if member_id is None:
        return render(request, "portal/not_linked.html", {"page_title": "Cuenta no vinculada"})

    member = await api.get(f"/api/v1/members/{member_id}", token)
    connections_data = await api.get("/api/v1/connections", token, params={"member_id": member_id, "limit": 200})
    bgp_data = await api.get("/api/v1/bgp-sessions", token, params={"member_id": member_id, "limit": 200})

    conn_items = connections_data.get("items", [])
    session_items = bgp_data.get("items", [])
    active_conns = sum(1 for c in conn_items if c.get("state") == "active")
    sessions_up = sum(1 for s in session_items if s.get("oper_state") == "up")

    return render(request, "portal/dashboard.html", {
        "member": member,
        "active_connections": active_conns,
        "total_connections": len(conn_items),
        "sessions_up": sessions_up,
        "total_sessions": len(session_items),
        "page_title": "Dashboard",
    })


@require_portal_auth
async def portal_profile(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    member_id = get_session_member_id(request)
    if member_id is None:
        return render(request, "portal/not_linked.html", {"page_title": "Cuenta no vinculada"})
    member = await api.get(f"/api/v1/members/{member_id}", token)
    return render(request, "portal/profile.html", {"member": member, "page_title": "Mi Perfil"})


@require_portal_auth
async def portal_connections(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    member_id = get_session_member_id(request)
    if member_id is None:
        return render(request, "portal/not_linked.html", {"page_title": "Cuenta no vinculada"})
    connections_data = await api.get("/api/v1/connections", token, params={"member_id": member_id, "limit": 200})
    return render(request, "portal/connections.html", {
        "connections": connections_data.get("items", []),
        "page_title": "Conexiones",
    })


@require_portal_auth
async def portal_bgp_sessions(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    member_id = get_session_member_id(request)
    if member_id is None:
        return render(request, "portal/not_linked.html", {"page_title": "Cuenta no vinculada"})
    bgp_data = await api.get("/api/v1/bgp-sessions", token, params={"member_id": member_id, "limit": 200})
    return render(request, "portal/bgp_sessions.html", {
        "sessions": bgp_data.get("items", []),
        "page_title": "Sesiones BGP",
    })


@require_portal_auth
async def portal_contacts(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    member_id = get_session_member_id(request)
    if member_id is None:
        return render(request, "portal/not_linked.html", {"page_title": "Cuenta no vinculada"})
    contacts_data = await api.get("/api/v1/contacts", token, params={"member_id": member_id, "limit": 200})
    return render(request, "portal/contacts.html", {
        "contacts": contacts_data.get("items", []),
        "page_title": "Contactos",
    })
