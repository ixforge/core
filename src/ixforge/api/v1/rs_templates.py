"""Route server template endpoints: CRUD + validation (admin only)."""

import uuid

from fastapi import APIRouter, Response

from ixforge.api.deps import AdminUser, DBSession, IXPId
from ixforge.models.rs_template import RouteServerTemplate
from ixforge.schemas.rs_template import (
    RSTemplateCreate,
    RSTemplatePreviewRequest,
    RSTemplatePreviewResponse,
    RSTemplateRead,
    RSTemplateUpdate,
    RSTemplateValidateRequest,
    RSTemplateValidateResponse,
)
from ixforge.services import rs_templates as tpl_svc

rs_templates_router = APIRouter(prefix="/rs-templates", tags=["rs-templates"])


@rs_templates_router.post("/validate", response_model=RSTemplateValidateResponse)
async def validate_template(
    body: RSTemplateValidateRequest,
    _admin: AdminUser,
) -> RSTemplateValidateResponse:
    """Validate Jinja2 template syntax without saving."""
    return tpl_svc.validate_syntax(body.content)


@rs_templates_router.get("", response_model=list[RSTemplateRead])
async def list_templates(
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> list[RouteServerTemplate]:
    """List all templates for the current IXP."""
    return await tpl_svc.list_templates(db, ixp_id)


@rs_templates_router.post("", response_model=RSTemplateRead, status_code=201)
async def create_template(
    body: RSTemplateCreate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> RouteServerTemplate:
    """Create a new template."""
    return await tpl_svc.create(db, ixp_id, body)


@rs_templates_router.get("/{template_id}", response_model=RSTemplateRead)
async def get_template(
    template_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> RouteServerTemplate:
    """Get a single template by ID."""
    return await tpl_svc.get(db, ixp_id, template_id)


@rs_templates_router.patch("/{template_id}", response_model=RSTemplateRead)
async def update_template(
    template_id: uuid.UUID,
    body: RSTemplateUpdate,
    db: DBSession,
    ixp_id: IXPId,
    admin: AdminUser,
) -> RouteServerTemplate:
    """Update a template's content and/or description."""
    return await tpl_svc.update(db, ixp_id, template_id, body, user_id=admin.id)


@rs_templates_router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> Response:
    """Delete a template."""
    await tpl_svc.delete(db, ixp_id, template_id)
    return Response(status_code=204)


@rs_templates_router.post("/{template_id}/preview", response_model=RSTemplatePreviewResponse)
async def preview_template(
    template_id: uuid.UUID,
    body: RSTemplatePreviewRequest,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> RSTemplatePreviewResponse:
    """Render a config preview with real route server data"""
    result = await tpl_svc.render_preview(db, ixp_id, template_id, body.route_server_id)
    return RSTemplatePreviewResponse(**result)
