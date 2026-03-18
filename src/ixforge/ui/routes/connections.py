"""Connection UI routes: standalone connection operations (transition only).

Connection management is now done from the trunk detail page.
This module retains only the transition endpoint needed for inline actions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.responses import RedirectResponse

from ixforge.ui.api_client import APIClient, APIError
from ixforge.ui.deps import require_auth
from ixforge.ui.session import add_flash, require_token, safe_detail

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response


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

    # Redirect back to the trunk detail page if we came from there
    from urllib.parse import urlparse

    referer = request.headers.get("referer", "")
    referer_path = urlparse(referer).path
    if referer_path.startswith("/admin/trunks/"):
        return RedirectResponse(referer_path, status_code=302)
    return RedirectResponse("/admin/trunks", status_code=302)
