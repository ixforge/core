# core/src/ixforge/ui/deps.py
"""Auth dependencies for UI routes."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

from starlette.responses import RedirectResponse, Response

from ixforge.ui.api_client import AuthenticationError
from ixforge.ui.session import clear_session, get_token

if TYPE_CHECKING:
    from collections.abc import Callable

    from starlette.requests import Request


def require_auth(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that redirects to /login if no JWT in session.

    Also catches AuthenticationError from route handlers — clears the
    stale session to prevent redirect loops and sends user to login.
    """

    @functools.wraps(func)
    async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Response:
        token = get_token(request)
        if not token:
            return RedirectResponse("/login", status_code=302)
        try:
            resp: Response = await func(request, *args, **kwargs)
            return resp
        except AuthenticationError:
            clear_session(request)
            return RedirectResponse("/login", status_code=302)

    return wrapper
