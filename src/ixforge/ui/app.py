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

    from starlette.types import ASGIApp, Receive, Scope, Send

_STATIC_DIR = Path(__file__).parent / "static"


class SetupRedirectMiddleware:
    """Redirect all routes to /setup when no IXP is configured."""

    _EXEMPT_PREFIXES = ("/setup", "/static", "/media")

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if any(path.startswith(p) for p in self._EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        # Check cache first
        app = scope.get("app")
        if app and getattr(app.state, "ixp_configured", False):
            await self.app(scope, receive, send)
            return

        # Check via API
        try:
            api = app.state.api if app else None
            if api:
                status = await api.get_public("/api/v1/setup/status")
                if status.get("configured"):
                    if app:
                        app.state.ixp_configured = True
                    await self.app(scope, receive, send)
                    return
        except Exception:
            # Fail open: let the request through
            await self.app(scope, receive, send)
            return

        # Not configured: redirect to /setup
        response = RedirectResponse("/setup", status_code=302)
        await response(scope, receive, send)


def create_ui_app() -> Starlette:
    config = get_settings()

    _media_dir = Path(config.media_root)
    _media_dir.mkdir(parents=True, exist_ok=True)

    from ixforge.ui.routes import (
        auth,
        bgp_sessions,
        connections,
        custom_fields,
        dashboard,
        events,
        ip_pools,
        ixf_export,
        locations,
        members,
        portal,
        route_servers,
        settings,
        setup,
        switches,
        trunks,
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
        # Setup
        Route("/setup", setup.setup_page, methods=["GET"]),
        Route("/setup", setup.setup_submit, methods=["POST"]),
        # Dashboard
        Route("/admin", dashboard.index),
        # Members
        Route("/admin/asn-name", members.asn_name_fragment),
        Route("/admin/members", members.member_list),
        Route("/admin/members/new", members.member_new, methods=["GET", "POST"]),
        Route("/admin/members/{member_id}/asn-name", members.member_asn_name),
        Route("/admin/members/{member_id}", members.member_detail),
        Route("/admin/members/{member_id}/edit", members.member_edit, methods=["GET", "POST"]),
        Route("/admin/members/{member_id}/transition", members.member_transition, methods=["POST"]),
        Route("/admin/members/{member_id}/logo", members.member_logo_upload, methods=["POST"]),
        Route("/admin/members/{member_id}/logo/delete", members.member_logo_delete, methods=["POST"]),
        Route("/admin/members/{member_id}/contacts/new", members.contact_new, methods=["POST"]),
        Route("/admin/members/{member_id}/delete", members.member_delete, methods=["POST"]),
        # Contacts (top-level for edit/delete)
        Route("/admin/contacts/{contact_id}/edit", members.contact_edit, methods=["POST"]),
        Route("/admin/contacts/{contact_id}/delete", members.contact_delete, methods=["POST"]),
        # Users
        Route("/admin/users", users.user_list),
        Route("/admin/users/new", users.user_new, methods=["GET", "POST"]),
        Route("/admin/users/{user_id}", users.user_detail),
        Route("/admin/users/{user_id}/edit", users.user_edit, methods=["POST"]),
        Route("/admin/users/{user_id}/api-keys", users.user_create_api_key, methods=["POST"]),
        Route("/admin/users/{user_id}/delete", users.user_delete, methods=["POST"]),
        # Locations
        Route("/admin/locations", locations.location_list),
        Route("/admin/locations/new", locations.location_new, methods=["GET", "POST"]),
        Route("/admin/locations/{location_id}/edit", locations.location_edit, methods=["GET", "POST"]),
        Route("/admin/locations/{location_id}/delete", locations.location_delete, methods=["POST"]),
        # Switches
        Route("/admin/switches", switches.switch_list),
        Route("/admin/switches/new", switches.switch_new, methods=["GET", "POST"]),
        Route("/admin/switches/{switch_id}", switches.switch_detail),
        Route("/admin/switches/{switch_id}/edit", switches.switch_edit, methods=["GET", "POST"]),
        Route("/admin/switches/{switch_id}/delete", switches.switch_delete, methods=["POST"]),
        # Route Servers
        Route("/admin/route-servers", route_servers.route_server_list),
        Route("/admin/route-servers/new", route_servers.route_server_new, methods=["GET", "POST"]),
        Route("/admin/route-servers/vlan-pools", route_servers.route_server_vlan_pools, methods=["GET"]),
        Route("/admin/route-servers/{rs_id}", route_servers.route_server_detail),
        Route("/admin/route-servers/{rs_id}/edit", route_servers.route_server_edit, methods=["GET", "POST"]),
        Route("/admin/route-servers/{rs_id}/vlans/add", route_servers.rs_vlan_add, methods=["POST"]),
        Route("/admin/route-servers/{rs_id}/vlans/{vlan_id}/remove", route_servers.rs_vlan_remove, methods=["POST"]),
        Route("/admin/route-servers/{rs_id}/ips/assign", route_servers.rs_ip_assign, methods=["POST"]),
        Route("/admin/route-servers/{rs_id}/ips/{assignment_id}/release", route_servers.rs_ip_release, methods=["POST"]),
        Route("/admin/route-servers/{route_server_id}/bgp-sessions", route_servers.route_server_add_bgp_session, methods=["POST"]),
        Route("/admin/route-servers/{rs_id}/delete", route_servers.route_server_delete, methods=["POST"]),
        Route("/admin/route-servers/{rs_id}/config/generate", route_servers.route_server_config_generate, methods=["POST"]),
        Route("/admin/route-servers/{rs_id}/config/history", route_servers.route_server_config_history),
        Route("/admin/route-servers/{rs_id}/config/diff", route_servers.route_server_config_diff),
        # VLANs
        Route("/admin/vlans", vlans.vlan_list),
        Route("/admin/vlans/new", vlans.vlan_new, methods=["GET", "POST"]),
        Route("/admin/vlans/{vlan_id}", vlans.vlan_detail),
        Route("/admin/vlans/{vlan_id}/edit", vlans.vlan_edit, methods=["GET", "POST"]),
        Route("/admin/vlans/{vlan_id}/delete", vlans.vlan_delete, methods=["POST"]),
        Route("/admin/vlans/{vlan_id}/members/add", vlans.vlan_member_add, methods=["POST"]),
        Route("/admin/vlans/{vlan_id}/members/{member_id}/remove", vlans.vlan_member_remove, methods=["POST"]),
        # IP Pools
        Route("/admin/ip-pools", ip_pools.ip_pool_list),
        Route("/admin/ip-pools/new", ip_pools.ip_pool_new, methods=["GET", "POST"]),
        Route("/admin/ip-pools/{pool_id}", ip_pools.ip_pool_detail),
        Route("/admin/ip-pools/{pool_id}/delete", ip_pools.ip_pool_delete, methods=["POST"]),
        # BGP Sessions
        Route("/admin/bgp-sessions", bgp_sessions.bgp_session_list),
        Route("/admin/bgp-sessions/new", bgp_sessions.bgp_session_new, methods=["GET", "POST"]),
        Route("/admin/bgp-sessions/{session_id}", bgp_sessions.bgp_session_detail),
        Route("/admin/bgp-sessions/{session_id}/delete", bgp_sessions.bgp_session_delete, methods=["POST"]),
        Route("/admin/bgp-sessions/{session_id}/toggle", bgp_sessions.bgp_session_toggle, methods=["POST"]),
        # Trunks
        Route("/admin/trunks", trunks.trunk_list),
        Route("/admin/trunks/new", trunks.trunk_new, methods=["GET", "POST"]),
        Route("/admin/trunks/{trunk_id}", trunks.trunk_detail),
        Route("/admin/trunks/{trunk_id}/edit", trunks.trunk_edit, methods=["GET", "POST"]),
        Route("/admin/trunks/{trunk_id}/delete", trunks.trunk_delete, methods=["POST"]),
        Route("/admin/trunks/{trunk_id}/transition", trunks.trunk_transition, methods=["POST"]),
        Route("/admin/trunks/{trunk_id}/vlans", trunks.trunk_assign_vlan, methods=["POST"]),
        Route("/admin/trunks/{trunk_id}/vlans/{tv_id}/delete", trunks.trunk_unassign_vlan, methods=["POST"]),
        Route("/admin/trunks/{trunk_id}/vlans/{tv_id}/ips", trunks.trunk_assign_ip, methods=["POST"]),
        Route("/admin/trunks/{trunk_id}/vlans/{tv_id}/ips/{aid}/delete", trunks.trunk_release_ip, methods=["POST"]),
        Route("/admin/trunks/{trunk_id}/connections", trunks.trunk_add_connection, methods=["POST"]),
        Route("/admin/trunks/{trunk_id}/connections/{cid}/transition", trunks.trunk_connection_transition, methods=["POST"]),
        # Connections
        Route("/admin/connections", connections.connection_list),
        Route("/admin/connections/new", connections.connection_new, methods=["GET", "POST"]),
        Route("/admin/connections/{connection_id}/transition", connections.connection_transition, methods=["POST"]),
        # Events
        Route("/admin/events", events.event_list),
        # Custom Fields
        Route("/admin/custom-fields", custom_fields.custom_field_list),
        Route("/admin/custom-fields/new", custom_fields.custom_field_new, methods=["GET", "POST"]),
        Route("/admin/custom-fields/{field_id}/edit", custom_fields.custom_field_edit, methods=["POST"]),
        Route("/admin/custom-fields/{field_id}/delete", custom_fields.custom_field_delete, methods=["POST"]),
        # IX-F Export
        Route("/admin/ixf-export", ixf_export.ixf_export_view),
        # Settings
        Route("/admin/settings", settings.settings_edit, methods=["GET", "POST"]),
        # Portal (member-only)
        Route("/portal", portal.portal_redirect),
        Route("/portal/dashboard", portal.portal_dashboard),
        Route("/portal/profile", portal.portal_profile),
        Route("/portal/trunks", portal.portal_trunks),
        Route("/portal/bgp-sessions", portal.portal_bgp_sessions),
        Route("/portal/contacts", portal.portal_contacts),
        # Static
        Mount("/static", app=StaticFiles(directory=str(_STATIC_DIR)), name="static"),
        Mount("/media", app=StaticFiles(directory=str(_media_dir)), name="media"),
    ]

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncGenerator[None, None]:
        yield
        await _app.state.api.close()

    app = Starlette(routes=routes, lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=config.secret_key,
        session_cookie="ixforge_session",
        same_site="lax",
        https_only=not config.debug,
    )
    app.add_middleware(SetupRedirectMiddleware)

    app.state.api = APIClient(base_url=config.core_url)

    return app
