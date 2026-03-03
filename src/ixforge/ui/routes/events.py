"""Events UI routes: list (read-only, cursor-paginated)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ixforge.ui.deps import require_auth
from ixforge.ui.session import require_token
from ixforge.ui.templating import render

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from ixforge.ui.api_client import APIClient


@require_auth
async def event_list(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    resource_type = request.query_params.get("resource_type", "")
    cursor = request.query_params.get("cursor")

    params: dict[str, Any] = {"limit": 50}
    if resource_type:
        params["resource_type"] = resource_type
    if cursor:
        params["cursor"] = cursor

    data = await api.get("/api/v1/events", token, params=params)

    items = data.get("items", [])

    is_htmx = request.headers.get("hx-request") == "true"
    template = "events/list_rows.html" if is_htmx else "events/list.html"

    return render(request, template, {
        "events": items,
        "next_cursor": data.get("next_cursor"),
        "has_more": data.get("has_more", False),
        "filter_resource_type": resource_type,
        "page_title": "Eventos",
    })
