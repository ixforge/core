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
    trunks_data = await api.get("/api/v1/trunks", token, params={"member_id": member_id, "limit": 200})

    trunk_items = trunks_data.get("items", [])
    active_trunks = sum(1 for t in trunk_items if t.get("state") == "active")

    return render(request, "portal/dashboard.html", {
        "member": member,
        "active_trunks": active_trunks,
        "total_trunks": len(trunk_items),
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
async def portal_trunks(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    member_id = get_session_member_id(request)
    if member_id is None:
        return render(request, "portal/not_linked.html", {"page_title": "Cuenta no vinculada"})
    trunks_data = await api.get("/api/v1/trunks", token, params={"member_id": member_id, "limit": 200})
    return render(request, "portal/trunks.html", {
        "trunks": trunks_data.get("items", []),
        "page_title": "Trunks",
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
