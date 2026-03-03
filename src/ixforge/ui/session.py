# core/src/ixforge/ui/session.py
"""Session helpers for JWT storage and flash messages."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from starlette.requests import Request

_TOKEN_KEY = "token"
_FLASH_KEY = "_flash"


def get_token(request: Request) -> str | None:
    return request.session.get(_TOKEN_KEY)


def require_token(request: Request) -> str:
    """Return token or raise ValueError — use inside @require_auth routes only."""
    token = request.session.get(_TOKEN_KEY)
    if token is None:
        msg = "No token in session (should be unreachable inside @require_auth)"
        raise ValueError(msg)
    return str(token)


def set_token(request: Request, token: str) -> None:
    request.session[_TOKEN_KEY] = token


def clear_session(request: Request) -> None:
    request.session.clear()


def add_flash(request: Request, message: str, category: str = "info") -> None:
    messages = request.session.get(_FLASH_KEY, [])
    messages.append({"message": message, "category": category})
    request.session[_FLASH_KEY] = messages


def get_flash_messages(request: Request) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = request.session.pop(_FLASH_KEY, [])
    return messages
