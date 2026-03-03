"""Starlette application factory for the UI portal."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from ixforge.config import get_settings
from ixforge.ui.api_client import APIClient

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

_STATIC_DIR = Path(__file__).parent / "static"


def create_ui_app() -> Starlette:
    settings = get_settings()

    from ixforge.ui.routes import (
        auth,
        bgp_sessions,
        connections,
        custom_fields,
        dashboard,
        events,
        ip_pools,
        ixf_export,
        members,
        ports,
        route_servers,
        switches,
        users,
        vlans,
    )

    routes = [
        # Root redirect
        Route("/", lambda r: RedirectResponse("/admin", status_code=302)),
        # Auth
        Route("/login", auth.login_page, methods=["GET"]),
        Route("/login", auth.login_submit, methods=["POST"]),
        Route("/logout", auth.logout, methods=["POST"]),
        # Dashboard
        Route("/admin", dashboard.index),
        # Members
        Route("/admin/members", members.member_list),
        Route("/admin/members/new", members.member_new, methods=["GET", "POST"]),
        Route("/admin/members/{member_id}", members.member_detail),
        Route("/admin/members/{member_id}/edit", members.member_edit, methods=["GET", "POST"]),
        Route("/admin/members/{member_id}/transition", members.member_transition, methods=["POST"]),
        Route("/admin/members/{member_id}/contacts/new", members.contact_new, methods=["POST"]),
        # Contacts (top-level for edit/delete)
        Route("/admin/contacts/{contact_id}/edit", members.contact_edit, methods=["POST"]),
        Route("/admin/contacts/{contact_id}/delete", members.contact_delete, methods=["POST"]),
        # Users
        Route("/admin/users", users.user_list),
        Route("/admin/users/new", users.user_new, methods=["GET", "POST"]),
        Route("/admin/users/{user_id}", users.user_detail),
        Route("/admin/users/{user_id}/edit", users.user_edit, methods=["POST"]),
        Route("/admin/users/{user_id}/api-keys", users.user_create_api_key, methods=["POST"]),
        # Switches
        Route("/admin/switches", switches.switch_list),
        Route("/admin/switches/new", switches.switch_new, methods=["GET", "POST"]),
        Route("/admin/switches/{switch_id}", switches.switch_detail),
        Route("/admin/switches/{switch_id}/edit", switches.switch_edit, methods=["GET", "POST"]),
        Route("/admin/switches/{switch_id}/delete", switches.switch_delete, methods=["POST"]),
        # Ports
        Route("/admin/ports/options", ports.port_options),
        Route("/admin/ports", ports.port_list),
        Route("/admin/ports/new", ports.port_new, methods=["GET", "POST"]),
        Route("/admin/ports/{port_id}/edit", ports.port_edit, methods=["GET", "POST"]),
        Route("/admin/ports/{port_id}/delete", ports.port_delete, methods=["POST"]),
        Route("/admin/ports/{port_id}/assign", ports.port_assign, methods=["POST"]),
        Route("/admin/ports/{port_id}/release", ports.port_release, methods=["POST"]),
        # Route Servers
        Route("/admin/route-servers", route_servers.route_server_list),
        Route("/admin/route-servers/new", route_servers.route_server_new, methods=["GET", "POST"]),
        Route("/admin/route-servers/{rs_id}", route_servers.route_server_detail),
        Route("/admin/route-servers/{rs_id}/edit", route_servers.route_server_edit, methods=["GET", "POST"]),
        Route("/admin/route-servers/{rs_id}/delete", route_servers.route_server_delete, methods=["POST"]),
        Route("/admin/route-servers/{rs_id}/config/generate", route_servers.route_server_config_generate, methods=["POST"]),
        Route("/admin/route-servers/{rs_id}/config/history", route_servers.route_server_config_history),
        Route("/admin/route-servers/{rs_id}/config/diff", route_servers.route_server_config_diff),
        # VLANs
        Route("/admin/vlans", vlans.vlan_list),
        Route("/admin/vlans/new", vlans.vlan_new, methods=["GET", "POST"]),
        Route("/admin/vlans/{vlan_id}/edit", vlans.vlan_edit, methods=["GET", "POST"]),
        Route("/admin/vlans/{vlan_id}/delete", vlans.vlan_delete, methods=["POST"]),
        # IP Pools
        Route("/admin/ip-pools", ip_pools.ip_pool_list),
        Route("/admin/ip-pools/new", ip_pools.ip_pool_new, methods=["GET", "POST"]),
        Route("/admin/ip-pools/{pool_id}", ip_pools.ip_pool_detail),
        Route("/admin/ip-pools/{pool_id}/delete", ip_pools.ip_pool_delete, methods=["POST"]),
        # BGP Sessions
        Route("/admin/bgp-sessions", bgp_sessions.bgp_session_list),
        Route("/admin/bgp-sessions/{session_id}", bgp_sessions.bgp_session_detail),
        Route("/admin/bgp-sessions/{session_id}/toggle", bgp_sessions.bgp_session_toggle, methods=["POST"]),
        # Connections
        Route("/admin/connections", connections.connection_list),
        Route("/admin/connections/new", connections.connection_new, methods=["GET", "POST"]),
        Route("/admin/connections/{connection_id}", connections.connection_detail),
        Route("/admin/connections/{connection_id}/edit", connections.connection_edit, methods=["GET", "POST"]),
        Route("/admin/connections/{connection_id}/transition", connections.connection_transition, methods=["POST"]),
        Route("/admin/connections/{connection_id}/vlans", connections.connection_assign_vlan, methods=["POST"]),
        Route("/admin/connections/{connection_id}/vlans/{vlan_id}/delete", connections.connection_unassign_vlan, methods=["POST"]),
        Route("/admin/connections/{connection_id}/ips", connections.connection_assign_ip, methods=["POST"]),
        Route("/admin/connections/{connection_id}/ips/{assignment_id}/delete", connections.connection_release_ip, methods=["POST"]),
        # Events
        Route("/admin/events", events.event_list),
        # Custom Fields
        Route("/admin/custom-fields", custom_fields.custom_field_list),
        Route("/admin/custom-fields/new", custom_fields.custom_field_new, methods=["GET", "POST"]),
        Route("/admin/custom-fields/{field_id}/edit", custom_fields.custom_field_edit, methods=["POST"]),
        Route("/admin/custom-fields/{field_id}/delete", custom_fields.custom_field_delete, methods=["POST"]),
        # IX-F Export
        Route("/admin/ixf-export", ixf_export.ixf_export_view),
        # Static
        Mount("/static", app=StaticFiles(directory=str(_STATIC_DIR)), name="static"),
    ]

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncGenerator[None, None]:
        yield
        await _app.state.api.close()

    app = Starlette(routes=routes, lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="ixforge_session",
        same_site="lax",
        https_only=not settings.debug,
    )

    app.state.api = APIClient(base_url=settings.core_url)

    return app
