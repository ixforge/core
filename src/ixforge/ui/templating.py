"""Jinja2 template configuration."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from starlette.templating import Jinja2Templates

from ixforge.ui.session import get_flash_messages

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import HTMLResponse

_TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def render(request: Request, template_name: str, context: dict[str, Any] | None = None) -> HTMLResponse:
    """Render a template with flash messages and request injected."""
    ctx: dict[str, Any] = {"request": request}
    ctx["flash_messages"] = get_flash_messages(request)
    if context:
        ctx.update(context)
    return templates.TemplateResponse(request, template_name, ctx)
