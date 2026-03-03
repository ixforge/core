"""IX-F Member Export UI route: preview and download link."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ixforge.ui.api_client import APIClient, APIError
from ixforge.ui.deps import require_auth
from ixforge.ui.session import require_token
from ixforge.ui.templating import render

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response


@require_auth
async def ixf_export_view(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    ixf_data = None
    ixf_json = ""
    try:
        ixf_data = await api.get("/api/v1/ixf/member-export", token)
        import json
        ixf_json = json.dumps(ixf_data, indent=2, ensure_ascii=False)
    except APIError:
        pass

    # Build the public URL for the API endpoint
    api_url = f"{api.base_url}/api/v1/ixf/member-export"

    return render(request, "ixf_export/view.html", {
        "ixf_data": ixf_data,
        "ixf_json": ixf_json,
        "api_url": api_url,
        "page_title": "IX-F Member Export",
    })
