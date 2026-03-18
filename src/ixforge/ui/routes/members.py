"""Member UI routes: list, detail, create, edit, state transition."""

from __future__ import annotations

import html as _html
from typing import TYPE_CHECKING, Any

from starlette.datastructures import UploadFile as StarletteUploadFile
from starlette.responses import HTMLResponse, RedirectResponse, Response

from ixforge.ui.api_client import APIClient, APIError
from ixforge.ui.deps import require_auth
from ixforge.ui.session import add_flash, require_token, safe_detail
from ixforge.ui.templating import render

if TYPE_CHECKING:
    from starlette.requests import Request


@require_auth
async def member_list(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    state = request.query_params.get("state", "")
    search = request.query_params.get("search", "")
    cursor = request.query_params.get("cursor")

    params: dict[str, Any] = {"limit": 50}
    if cursor:
        params["cursor"] = cursor

    data = await api.get("/api/v1/members", token, params=params)

    items = data.get("items", [])
    if state:
        items = [m for m in items if m.get("state") == state]
    if search:
        s = search.lower()
        items = [m for m in items if s in m.get("name", "").lower() or s in str(m.get("asn", ""))]

    is_htmx = request.headers.get("hx-request") == "true"
    template = "members/list_rows.html" if is_htmx else "members/list.html"

    return render(request, template, {
        "members": items,
        "next_cursor": data.get("next_cursor"),
        "has_more": data.get("has_more", False),
        "filter_state": state,
        "search": search,
        "page_title": "Miembros",
    })


@require_auth
async def member_detail(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    member_id = request.path_params["member_id"]

    try:
        member = await api.get(f"/api/v1/members/{member_id}", token)
        trunks_data = await api.get("/api/v1/trunks", token, params={"member_id": member_id, "limit": 200})
    except APIError as e:
        if e.status_code == 404:
            add_flash(request, "Miembro no encontrado", "error")
            return RedirectResponse("/admin/members", status_code=302)
        raise

    # Fetch contacts
    contacts: list[Any] = []
    try:
        contacts_data = await api.get(f"/api/v1/members/{member_id}/contacts", token)
        contacts = contacts_data.get("items", []) if isinstance(contacts_data, dict) else contacts_data
    except APIError:
        pass

    return render(request, "members/detail.html", {
        "member": member,
        "trunks": trunks_data.get("items", []),
        "contacts": contacts,
        "page_title": member.get("name", "Miembro"),
    })


@require_auth
async def member_new(request: Request) -> Response:
    if request.method == "GET":
        return render(request, "members/form.html", {
            "member": None,
            "errors": {},
            "page_title": "Nuevo Miembro",
        })

    token = require_token(request)
    api: APIClient = request.app.state.api
    form = await request.form()

    payload: dict[str, Any] = {
        "name": str(form.get("name", "")),
        "short_name": str(form.get("short_name", "")),
        "asn": int(str(form.get("asn", 0)) or 0),
        "peering_policy": str(form.get("peering_policy", "open")),
    }
    website = str(form.get("website", "")).strip()
    if website:
        payload["website"] = website
    peeringdb_id = form.get("peeringdb_id")
    if peeringdb_id and str(peeringdb_id).strip():
        payload["peeringdb_id"] = int(str(peeringdb_id))

    # Extended fields
    for field in ("member_type", "description", "city", "country",
                  "connection_date", "contract_type", "notes"):
        val = str(form.get(field, "")).strip()
        if val:
            payload[field] = val

    payload["skip_ixf_export"] = form.get("skip_ixf_export") == "true"

    try:
        member = await api.post("/api/v1/members", token, json=payload)
    except APIError as e:
        if e.status_code in (400, 409, 422):
            return render(request, "members/form.html", {
                "member": payload,
                "errors": e.detail,
                "page_title": "Nuevo Miembro",
            })
        raise

    add_flash(request, f"Miembro '{member['name']}' creado", "success")
    return RedirectResponse(f"/admin/members/{member['id']}", status_code=302)


@require_auth
async def member_edit(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    member_id = request.path_params["member_id"]

    if request.method == "GET":
        member = await api.get(f"/api/v1/members/{member_id}", token)
        return render(request, "members/form.html", {
            "member": member,
            "errors": {},
            "page_title": f"Editar {member.get('name', 'Miembro')}",
        })

    form = await request.form()
    payload: dict[str, Any] = {}
    for field in ("name", "short_name", "peering_policy", "website",
                  "member_type", "description", "city", "country",
                  "connection_date", "contract_type", "notes"):
        val = form.get(field)
        if val is not None:
            payload[field] = str(val) if str(val).strip() else None
    payload["skip_ixf_export"] = form.get("skip_ixf_export") == "true"
    peeringdb_id = form.get("peeringdb_id")
    if peeringdb_id and str(peeringdb_id).strip():
        payload["peeringdb_id"] = int(str(peeringdb_id))

    try:
        member = await api.patch(f"/api/v1/members/{member_id}", token, json=payload)
    except APIError as e:
        if e.status_code in (400, 409, 422):
            return render(request, "members/form.html", {
                "member": {**payload, "id": member_id},
                "errors": e.detail,
                "page_title": "Editar Miembro",
            })
        raise

    add_flash(request, "Miembro actualizado", "success")
    return RedirectResponse(f"/admin/members/{member['id']}", status_code=302)


@require_auth
async def member_transition(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    member_id = request.path_params["member_id"]
    form = await request.form()
    new_state = str(form.get("state", ""))

    try:
        await api.post(f"/api/v1/members/{member_id}/transition", token, json={"state": new_state})
        add_flash(request, f"Estado cambiado a {new_state}", "success")
    except APIError as e:
        add_flash(request, f"Error en transicion: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/members/{member_id}", status_code=302)


@require_auth
async def contact_new(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    member_id = request.path_params["member_id"]
    form = await request.form()

    payload = {
        "name": str(form.get("name", "")),
        "email": str(form.get("email", "")),
        "phone": str(form.get("phone", "")),
        "role": str(form.get("role", "noc")),
    }

    try:
        await api.post(f"/api/v1/members/{member_id}/contacts", token, json=payload)
        add_flash(request, "Contacto creado", "success")
    except APIError as e:
        add_flash(request, f"Error creando contacto: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/members/{member_id}", status_code=302)


@require_auth
async def contact_edit(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    contact_id = request.path_params["contact_id"]
    form = await request.form()

    payload: dict[str, Any] = {}
    for field in ("name", "email", "phone", "role"):
        val = form.get(field)
        if val is not None:
            payload[field] = str(val)

    member_id = str(form.get("member_id", ""))

    try:
        await api.patch(f"/api/v1/contacts/{contact_id}", token, json=payload)
        add_flash(request, "Contacto actualizado", "success")
    except APIError as e:
        add_flash(request, f"Error actualizando contacto: {safe_detail(e)}", "error")

    if member_id:
        return RedirectResponse(f"/admin/members/{member_id}", status_code=302)
    return RedirectResponse("/admin/members", status_code=302)


@require_auth
async def contact_delete(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    contact_id = request.path_params["contact_id"]
    form = await request.form()
    member_id = str(form.get("member_id", ""))

    try:
        await api.delete(f"/api/v1/contacts/{contact_id}", token)
        add_flash(request, "Contacto eliminado", "success")
    except APIError as e:
        add_flash(request, f"Error eliminando contacto: {safe_detail(e)}", "error")

    if member_id:
        return RedirectResponse(f"/admin/members/{member_id}", status_code=302)
    return RedirectResponse("/admin/members", status_code=302)


@require_auth
async def member_logo_upload(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    member_id = request.path_params["member_id"]
    form = await request.form()
    file = form.get("file")
    if not isinstance(file, StarletteUploadFile):
        add_flash(request, "No se seleccionó archivo", "error")
        return RedirectResponse(f"/admin/members/{member_id}", status_code=302)
    try:
        await api.post_file(f"/api/v1/members/{member_id}/logo", token, field="file", upload=file)
        add_flash(request, "Logo actualizado", "success")
    except APIError as e:
        add_flash(request, f"Error: {safe_detail(e)}", "error")
    return RedirectResponse(f"/admin/members/{member_id}", status_code=302)


@require_auth
async def member_logo_delete(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    member_id = request.path_params["member_id"]
    try:
        await api.delete(f"/api/v1/members/{member_id}/logo", token)
        add_flash(request, "Logo eliminado", "success")
    except APIError as e:
        add_flash(request, f"Error: {safe_detail(e)}", "error")
    return RedirectResponse(f"/admin/members/{member_id}", status_code=302)


@require_auth
async def member_delete(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    member_id = request.path_params["member_id"]
    try:
        await api.delete(f"/api/v1/members/{member_id}", token)
        add_flash(request, "Miembro eliminado", "success")
        return RedirectResponse("/admin/members", status_code=302)
    except APIError as e:
        add_flash(request, f"Error: {safe_detail(e)}", "error")
        return RedirectResponse(f"/admin/members/{member_id}", status_code=302)


@require_auth
async def asn_name_fragment(request: Request) -> Response:
    """HTMX fragment: looks up ASN name by ASN number."""
    token = require_token(request)
    api: APIClient = request.app.state.api
    asn_str = request.query_params.get("asn", "")

    if not asn_str or not asn_str.isdigit():
        return HTMLResponse(f"AS{_html.escape(asn_str or '?')}")

    try:
        data = await api.get("/api/v1/members/asn-lookup", token, params={"asn": asn_str})
        name = _html.escape(data.get("name") or "")
        asn = _html.escape(str(data.get("asn", asn_str)))
        if name:
            html = f'AS{asn} <span class="text-gray-500 text-xs">({name})</span>'
        else:
            html = f"AS{asn}"
    except APIError:
        html = f"AS{_html.escape(asn_str)}"

    return HTMLResponse(html)


@require_auth
async def member_asn_name(request: Request) -> Response:
    """HTMX fragment: returns ASN name for a member."""
    token = require_token(request)
    api: APIClient = request.app.state.api
    member_id = request.path_params["member_id"]

    try:
        data = await api.get(f"/api/v1/members/{member_id}/asn-name", token)
        name = _html.escape(data.get("name") or "")
        asn = _html.escape(str(data.get("asn", "")))
        if name:
            html = f'AS{asn} <span class="text-gray-500 text-xs">({name})</span>'
        else:
            html = f"AS{asn}"
    except APIError:
        html = "AS?"

    return HTMLResponse(html)
