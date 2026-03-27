"""Route Server Template UI routes: list, create, edit, delete, preview."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.responses import RedirectResponse, Response

from ixforge.ui.api_client import APIClient, APIError
from ixforge.ui.deps import require_auth
from ixforge.ui.session import add_flash, require_token, safe_detail
from ixforge.ui.templating import render

if TYPE_CHECKING:
    from starlette.requests import Request


async def _load_route_servers(api: APIClient, token: str) -> list[dict[str, Any]]:
    """Load all route servers for the preview dropdown."""
    try:
        data = await api.get("/api/v1/route-servers", token, params={"limit": 200})
        return list(data.get("items", []))
    except APIError as e:
        if e.status_code is not None and e.status_code < 500:
            return []
        raise


@require_auth
async def template_list(request: Request) -> Response:
    """GET list of all RS templates."""
    token = require_token(request)
    api: APIClient = request.app.state.api

    try:
        templates = await api.get("/api/v1/rs-templates", token)
    except APIError:
        templates = []

    return render(request, "rs_templates/list.html", {
        "templates": templates if isinstance(templates, list) else [],
        "page_title": "Plantillas de Route Server",
    })


@require_auth
async def template_new(request: Request) -> Response:
    """GET shows form, POST creates via API."""
    token = require_token(request)
    api: APIClient = request.app.state.api

    if request.method == "GET":
        return render(request, "rs_templates/new.html", {
            "form_data": None,
            "errors": {},
            "page_title": "Nueva Plantilla",
        })

    form = await request.form()

    payload: dict[str, Any] = {
        "filename": str(form.get("filename", "")),
        "content": str(form.get("content", "")),
    }
    description = str(form.get("description", "")).strip()
    if description:
        payload["description"] = description

    try:
        tpl = await api.post("/api/v1/rs-templates", token, json=payload)
    except APIError as e:
        if e.status_code in (400, 409, 422):
            return render(request, "rs_templates/new.html", {
                "form_data": payload,
                "errors": e.detail,
                "page_title": "Nueva Plantilla",
            })
        raise

    add_flash(request, f"Plantilla '{tpl['filename']}' creada", "success")
    return RedirectResponse(
        f"/admin/route-servers/templates/{tpl['id']}/edit",
        status_code=302,
    )


@require_auth
async def template_edit(request: Request) -> Response:
    """GET shows the template editor with RS list for preview."""
    token = require_token(request)
    api: APIClient = request.app.state.api
    tpl_id = request.path_params["tpl_id"]

    try:
        tpl = await api.get(f"/api/v1/rs-templates/{tpl_id}", token)
    except APIError as e:
        if e.status_code == 404:
            add_flash(request, "Plantilla no encontrada", "error")
            return RedirectResponse("/admin/route-servers/templates", status_code=302)
        raise

    route_servers = await _load_route_servers(api, token)

    return render(request, "rs_templates/edit.html", {
        "template": tpl,
        "route_servers": route_servers,
        "errors": {},
        "page_title": f"Editar {tpl.get('name', 'Plantilla')}",
    })


@require_auth
async def template_save(request: Request) -> Response:
    """POST saves changes via PATCH API, redirect back to edit."""
    token = require_token(request)
    api: APIClient = request.app.state.api
    tpl_id = request.path_params["tpl_id"]

    form = await request.form()
    payload: dict[str, Any] = {}

    name_val = form.get("name")
    if name_val is not None:
        payload["name"] = str(name_val)
    content_val = form.get("content")
    if content_val is not None:
        payload["content"] = str(content_val)
    description_val = form.get("description")
    if description_val is not None:
        payload["description"] = str(description_val).strip() or None

    try:
        await api.patch(f"/api/v1/rs-templates/{tpl_id}", token, json=payload)
    except APIError as e:
        if e.status_code in (400, 409, 422):
            route_servers = await _load_route_servers(api, token)
            return render(request, "rs_templates/edit.html", {
                "template": {**payload, "id": tpl_id},
                "route_servers": route_servers,
                "errors": e.detail,
                "page_title": "Editar Plantilla",
            })
        raise

    add_flash(request, "Plantilla actualizada", "success")
    return RedirectResponse(
        f"/admin/route-servers/templates/{tpl_id}/edit",
        status_code=302,
    )


@require_auth
async def template_delete(request: Request) -> Response:
    """POST deletes via DELETE API, redirect to list."""
    token = require_token(request)
    api: APIClient = request.app.state.api
    tpl_id = request.path_params["tpl_id"]

    try:
        await api.delete(f"/api/v1/rs-templates/{tpl_id}", token)
        add_flash(request, "Plantilla eliminada", "success")
    except APIError as e:
        add_flash(request, f"Error eliminando plantilla: {safe_detail(e)}", "error")

    return RedirectResponse("/admin/route-servers/templates", status_code=302)


@require_auth
async def template_preview(request: Request) -> Response:
    """POST renders preview via API, returns HTMX fragment."""
    token = require_token(request)
    api: APIClient = request.app.state.api
    tpl_id = request.path_params["tpl_id"]

    form = await request.form()
    route_server_id = str(form.get("route_server_id", "")).strip()

    if not route_server_id:
        return render(request, "rs_templates/_preview_fragment.html", {
            "preview": None,
            "error": "Debe seleccionar un Route Server",
        })

    try:
        result = await api.post(
            f"/api/v1/rs-templates/{tpl_id}/preview",
            token,
            json={"route_server_id": route_server_id},
        )
    except APIError as e:
        return render(request, "rs_templates/_preview_fragment.html", {
            "preview": None,
            "error": safe_detail(e),
        })

    return render(request, "rs_templates/_preview_fragment.html", {
        "preview": result,
        "error": None,
    })
