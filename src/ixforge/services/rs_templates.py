"""Route server template service: CRUD, reference checking, validation."""

import asyncio
import uuid
from typing import Any

import structlog
from jinja2 import TemplateSyntaxError, nodes
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import ConflictError, NotFoundError
from ixforge.models.rs_template import RouteServerTemplate
from ixforge.schemas.rs_template import (
    RSTemplateCreate,
    RSTemplateUpdate,
    RSTemplateValidateResponse,
)

logger = structlog.get_logger()


async def create(
    session: AsyncSession, ixp_id: uuid.UUID, data: RSTemplateCreate,
) -> RouteServerTemplate:
    """Create a new template"""
    tpl = RouteServerTemplate(
        ixp_id=ixp_id, filename=data.filename, content=data.content, description=data.description,
    )
    session.add(tpl)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(f"Template with filename '{data.filename}' already exists") from exc
    logger.info("rs_template.created", filename=data.filename, ixp_id=str(ixp_id))
    return tpl


async def get(
    session: AsyncSession, ixp_id: uuid.UUID, template_id: uuid.UUID,
) -> RouteServerTemplate:
    """Get a template by ID or raise NotFoundError"""
    tpl = await session.get(RouteServerTemplate, template_id)
    if tpl is None or tpl.ixp_id != ixp_id:
        raise NotFoundError("RouteServerTemplate", str(template_id))
    return tpl


async def list_templates(
    session: AsyncSession, ixp_id: uuid.UUID,
) -> list[RouteServerTemplate]:
    """List all templates for an IXP ordered by filename"""
    stmt = (
        select(RouteServerTemplate)
        .where(RouteServerTemplate.ixp_id == ixp_id)
        .order_by(RouteServerTemplate.filename)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update(
    session: AsyncSession, ixp_id: uuid.UUID, template_id: uuid.UUID,
    data: RSTemplateUpdate, user_id: uuid.UUID | None = None,
) -> RouteServerTemplate:
    """Update a template's content and/or description"""
    tpl = await get(session, ixp_id, template_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(tpl, field, value)
    if user_id is not None:
        tpl.updated_by_id = user_id
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("Template could not be updated due to a conflict") from exc
    await session.refresh(tpl)
    logger.info("rs_template.updated", template_id=str(template_id), filename=tpl.filename)
    return tpl


async def delete(
    session: AsyncSession, ixp_id: uuid.UUID, template_id: uuid.UUID,
) -> None:
    """Delete a template after checking protection and references"""
    tpl = await get(session, ixp_id, template_id)
    if tpl.is_protected:
        raise ConflictError(f"Cannot delete protected template '{tpl.filename}'")
    refs = await check_template_references(session, ixp_id, tpl.filename)
    if refs:
        ref_list = ", ".join(refs)
        raise ConflictError(f"Cannot delete '{tpl.filename}': referenced by {ref_list}")
    await session.delete(tpl)
    await session.flush()
    logger.info("rs_template.deleted", filename=tpl.filename, ixp_id=str(ixp_id))


async def check_template_references(
    session: AsyncSession, ixp_id: uuid.UUID, filename: str,
) -> list[str]:
    """Check which templates reference the given filename via include/from-import.
    Uses Jinja2 AST parsing for robustness (ignores comments, raw blocks)."""
    templates = await list_templates(session, ixp_id)
    env = SandboxedEnvironment()
    referencing: list[str] = []
    for tpl in templates:
        if tpl.filename == filename:
            continue
        try:
            ast = env.parse(tpl.content)
        except TemplateSyntaxError:
            continue
        for node in ast.find_all((nodes.Include, nodes.FromImport)):
            if (
                isinstance(node, (nodes.Include, nodes.FromImport))
                and isinstance(node.template, nodes.Const)
                and node.template.value == filename
            ):
                referencing.append(tpl.filename)
                break
    return referencing


def validate_syntax(content: str) -> RSTemplateValidateResponse:
    """Validate Jinja2 syntax without rendering"""
    env = SandboxedEnvironment()
    try:
        env.parse(content)
        return RSTemplateValidateResponse(valid=True, errors=[])
    except TemplateSyntaxError as exc:
        return RSTemplateValidateResponse(valid=False, errors=[str(exc)])


async def get_all_templates(
    session: AsyncSession, ixp_id: uuid.UUID,
) -> dict[str, str]:
    """Return {filename: content} dict for all templates of an IXP. Used by DictLoader."""
    templates = await list_templates(session, ixp_id)
    return {tpl.filename: tpl.content for tpl in templates}


async def render_preview(
    session: AsyncSession, ixp_id: uuid.UUID,
    template_id: uuid.UUID, route_server_id: uuid.UUID,
) -> dict[str, Any]:
    """Render a config preview using the entry-point template with real RS data.
    Always renders from bird_v4/v6 (not partials).
    Uses asyncio.to_thread + wait_for for timeout on sync Jinja2 render."""
    from ixforge.models.ixp import IXP
    from ixforge.models.route_server import RouteServer
    from ixforge.services.config_generation import build_peers, build_rs_context
    from ixforge.services.template_env import build_template_env

    tpl = await get(session, ixp_id, template_id)
    rs = await session.get(RouteServer, route_server_id)
    if rs is None or rs.ixp_id != ixp_id:
        raise NotFoundError("RouteServer", str(route_server_id))
    ixp = await session.get(IXP, ixp_id)
    if ixp is None:
        raise NotFoundError("IXP", str(ixp_id))

    entry_point = tpl.filename
    if tpl.filename not in ("bird_v4.conf.j2", "bird_v6.conf.j2"):
        entry_point = "bird_v4.conf.j2" if rs.ip_v4 else "bird_v6.conf.j2"

    af = 4 if "v4" in entry_point else 6
    rs_context = await build_rs_context(session, rs, ixp.asn)
    peers = await build_peers(session, rs.id, af=af)

    env = await build_template_env(session, ixp_id)

    from datetime import UTC, datetime
    template = env.get_template(entry_point)
    context = {
        "route_server": rs_context,
        "peers": peers,
        "generated_at": datetime.now(UTC).isoformat(),
        "config_hash": "",
    }

    try:
        output = await asyncio.wait_for(
            asyncio.to_thread(template.render, context),
            timeout=10.0,
        )
        return {"output": output, "errors": None}
    except TimeoutError:
        return {"output": "", "errors": ["Template rendering timed out (10s limit)"]}
    except Exception as exc:
        return {"output": "", "errors": [str(exc)]}
