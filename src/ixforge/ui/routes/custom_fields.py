"""Custom Fields UI routes: list, create, edit, delete."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.responses import RedirectResponse, Response

from ixforge.ui.api_client import APIClient, APIError
from ixforge.ui.deps import require_auth
from ixforge.ui.session import add_flash, require_token
from ixforge.ui.templating import render

if TYPE_CHECKING:
    from starlette.requests import Request


@require_auth
async def custom_field_list(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    entity_type = request.query_params.get("entity_type", "")

    params: dict[str, Any] = {"limit": 200}
    if entity_type:
        params["entity_type"] = entity_type
    data = await api.get("/api/v1/custom-fields", token, params=params)

    items = data.get("items", [])

    # Group by entity_type for display
    grouped: dict[str, list[Any]] = {}
    for item in items:
        et = item.get("entity_type", "other")
        grouped.setdefault(et, []).append(item)

    return render(request, "custom_fields/list.html", {
        "fields": items,
        "grouped_fields": grouped,
        "filter_entity_type": entity_type,
        "page_title": "Custom Fields",
    })


@require_auth
async def custom_field_new(request: Request) -> Response:
    if request.method == "GET":
        return render(request, "custom_fields/form.html", {
            "field": None,
            "errors": {},
            "page_title": "Nuevo Custom Field",
        })

    token = require_token(request)
    api: APIClient = request.app.state.api
    form = await request.form()

    payload: dict[str, Any] = {
        "entity_type": str(form.get("entity_type", "")),
        "field_name": str(form.get("field_name", "")),
        "field_type": str(form.get("field_type", "string")),
        "is_required": form.get("is_required") == "on",
        "description": str(form.get("description", "")),
    }
    default_value = str(form.get("default_value", "")).strip()
    if default_value:
        payload["default_value"] = default_value
    display_order = form.get("display_order")
    if display_order and str(display_order).strip():
        payload["display_order"] = int(str(display_order))

    try:
        await api.post("/api/v1/custom-fields", token, json=payload)
    except APIError as e:
        if e.status_code == 422:
            return render(request, "custom_fields/form.html", {
                "field": payload,
                "errors": e.detail,
                "page_title": "Nuevo Custom Field",
            })
        raise

    add_flash(request, f"Custom field '{payload['field_name']}' creado", "success")
    return RedirectResponse("/admin/custom-fields", status_code=302)


@require_auth
async def custom_field_edit(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    field_id = request.path_params["field_id"]
    form = await request.form()

    payload: dict[str, Any] = {}
    for f in ("field_name", "field_type", "description", "default_value"):
        val = form.get(f)
        if val is not None:
            payload[f] = str(val)
    payload["is_required"] = form.get("is_required") == "on"
    display_order = form.get("display_order")
    if display_order and str(display_order).strip():
        payload["display_order"] = int(str(display_order))

    try:
        await api.patch(f"/api/v1/custom-fields/{field_id}", token, json=payload)
        add_flash(request, "Custom field actualizado", "success")
    except APIError as e:
        add_flash(request, f"Error actualizando custom field: {e.detail}", "error")

    return RedirectResponse("/admin/custom-fields", status_code=302)


@require_auth
async def custom_field_delete(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    field_id = request.path_params["field_id"]

    try:
        await api.delete(f"/api/v1/custom-fields/{field_id}", token)
        add_flash(request, "Custom field eliminado", "success")
    except APIError as e:
        add_flash(request, f"Error eliminando custom field: {e.detail}", "error")

    return RedirectResponse("/admin/custom-fields", status_code=302)
