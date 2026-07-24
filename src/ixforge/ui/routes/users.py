"""User UI routes: list, detail, create, edit, API keys."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.responses import RedirectResponse, Response

from ixforge.ui.api_client import APIClient, APIError
from ixforge.ui.deps import require_auth
from ixforge.ui.session import add_flash, require_token, safe_detail
from ixforge.ui.templating import render

if TYPE_CHECKING:
    from starlette.requests import Request


@require_auth
async def user_list(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    data = await api.get("/api/v1/users", token, params={"limit": 200})

    return render(request, "users/list.html", {
        "users": data.get("items", []),
        "page_title": "Usuarios",
    })


@require_auth
async def user_detail(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    user_id = request.path_params["user_id"]

    try:
        user = await api.get(f"/api/v1/users/{user_id}", token)
    except APIError as e:
        if e.status_code == 404:
            add_flash(request, "Usuario no encontrado", "error")
            return RedirectResponse("/admin/users", status_code=302)
        raise

    # Fetch API keys
    api_keys: list[Any] = []
    try:
        keys_data = await api.get(f"/api/v1/users/{user_id}/api-keys", token)
        api_keys = keys_data.get("items", [])
    except APIError:
        pass

    # Pop raw key from session (one-time display)
    new_raw_key = request.session.pop("new_raw_key", "")

    return render(request, "users/detail.html", {
        "user": user,
        "api_keys": api_keys,
        "new_raw_key": new_raw_key,
        "page_title": user.get("email", "Usuario"),
    })


@require_auth
async def user_new(request: Request) -> Response:
    if request.method == "GET":
        return render(request, "users/form.html", {
            "user": None,
            "errors": {},
            "page_title": "Nuevo Usuario",
        })

    token = require_token(request)
    api: APIClient = request.app.state.api
    form = await request.form()

    payload: dict[str, Any] = {
        "full_name": str(form.get("full_name", "")),
        "email": str(form.get("email", "")),
        "password": str(form.get("password", "")),
        "role": str(form.get("role", "member")),
        "is_active": form.get("is_active") == "on",
        "phone": str(form.get("phone", "")) or None,
        "position": str(form.get("position", "")) or None,
        "pgp_key": str(form.get("pgp_key", "")) or None,
    }

    try:
        user = await api.post("/api/v1/users", token, json=payload)
    except APIError as e:
        if e.status_code in (400, 409, 422):
            return render(request, "users/form.html", {
                "user": payload,
                "errors": e.detail,
                "page_title": "Nuevo Usuario",
            })
        raise

    add_flash(request, f"Usuario '{user['email']}' creado", "success")
    return RedirectResponse(f"/admin/users/{user['id']}", status_code=302)


@require_auth
async def user_edit(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    user_id = request.path_params["user_id"]

    form = await request.form()
    payload: dict[str, Any] = {}
    role = form.get("role")
    if role is not None:
        payload["role"] = str(role)
    payload["is_active"] = form.get("is_active") == "on"

    try:
        await api.patch(f"/api/v1/users/{user_id}", token, json=payload)
        add_flash(request, "Usuario actualizado", "success")
    except APIError as e:
        add_flash(request, f"Error actualizando usuario: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/users/{user_id}", status_code=302)


@require_auth
async def user_create_api_key(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    user_id = request.path_params["user_id"]
    form = await request.form()

    payload: dict[str, Any] = {
        "name": str(form.get("name", "")),
    }
    scopes = form.getlist("scopes")
    if scopes:
        payload["scopes"] = [str(s) for s in scopes]

    try:
        result = await api.post(f"/api/v1/users/{user_id}/api-keys", token, json=payload)
        raw_key = result.get("raw_key", result.get("key", ""))
        request.session["new_raw_key"] = raw_key
        add_flash(request, "API Key creada", "success")
        return RedirectResponse(f"/admin/users/{user_id}", status_code=302)
    except APIError as e:
        add_flash(request, f"Error creando API key: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/users/{user_id}", status_code=302)


@require_auth
async def user_revoke_api_key(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    user_id = request.path_params["user_id"]
    key_id = request.path_params["key_id"]

    try:
        await api.delete(f"/api/v1/users/{user_id}/api-keys/{key_id}", token)
        add_flash(request, "API Key revocada", "success")
    except APIError as e:
        add_flash(request, f"Error revocando API key: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/users/{user_id}", status_code=302)


@require_auth
async def user_delete(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    user_id = request.path_params["user_id"]
    try:
        await api.delete(f"/api/v1/users/{user_id}", token)
        add_flash(request, "Usuario eliminado", "success")
        return RedirectResponse("/admin/users", status_code=302)
    except APIError as e:
        add_flash(request, f"Error: {safe_detail(e)}", "error")
        return RedirectResponse(f"/admin/users/{user_id}", status_code=302)
