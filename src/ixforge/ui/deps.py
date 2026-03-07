# core/src/ixforge/ui/deps.py
"""Auth dependencies for UI routes."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

from starlette.responses import RedirectResponse, Response

from ixforge.ui.api_client import AuthenticationError
from ixforge.ui.session import clear_session, get_role, get_token

if TYPE_CHECKING:
    from collections.abc import Callable

    from starlette.requests import Request


def require_auth(func: Callable[..., Any]) -> Callable[..., Any]:
    """Admin routes: redirect if no token or if user is not an admin."""

    @functools.wraps(func)
    async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Response:
        token = get_token(request)
        if not token:
            return RedirectResponse("/login", status_code=302)
        role = get_role(request)
        if role != "admin":
            if role == "member":
                return RedirectResponse("/portal/dashboard", status_code=302)
            # Unknown or None role: clear session and redirect to login
            clear_session(request)
            return RedirectResponse("/login", status_code=302)
        try:
            resp: Response = await func(request, *args, **kwargs)
            return resp
        except AuthenticationError:
            clear_session(request)
            return RedirectResponse("/login", status_code=302)

    return wrapper


def require_portal_auth(func: Callable[..., Any]) -> Callable[..., Any]:
    """Portal routes: require token, redirect admins to /admin."""

    @functools.wraps(func)
    async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Response:
        token = get_token(request)
        if not token:
            return RedirectResponse("/login", status_code=302)
        role = get_role(request)
        if role != "member":
            if role == "admin":
                return RedirectResponse("/admin", status_code=302)
            # Unknown or None role: clear session and redirect to login
            clear_session(request)
            return RedirectResponse("/login", status_code=302)
        try:
            resp: Response = await func(request, *args, **kwargs)
            return resp
        except AuthenticationError:
            clear_session(request)
            return RedirectResponse("/login", status_code=302)

    return wrapper
