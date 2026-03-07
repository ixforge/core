# core/src/ixforge/ui/session.py
"""Session helpers for JWT storage and flash messages."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from starlette.requests import Request

    from ixforge.ui.api_client import APIError

_TOKEN_KEY = "token"
_FLASH_KEY = "_flash"
_ROLE_KEY = "user_role"
_MEMBER_ID_KEY = "user_member_id"


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


def get_role(request: Request) -> str | None:
    return request.session.get(_ROLE_KEY)


def set_role(request: Request, role: str) -> None:
    request.session[_ROLE_KEY] = role


def get_session_member_id(request: Request) -> str | None:
    return request.session.get(_MEMBER_ID_KEY)


def set_session_member_id(request: Request, member_id: str | None) -> None:
    request.session[_MEMBER_ID_KEY] = member_id


def add_flash(request: Request, message: str, category: str = "info") -> None:
    messages = request.session.get(_FLASH_KEY, [])
    messages.append({"message": message, "category": category})
    request.session[_FLASH_KEY] = messages


def get_flash_messages(request: Request) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = request.session.pop(_FLASH_KEY, [])
    return messages


def safe_detail(e: APIError, fallback: str = "Error interno del servidor") -> str:
    """Return a safe error detail string for display in flash messages"""
    if e.status_code >= 500:
        return fallback
    detail = e.detail
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        # IXForge format: {"error": {"code": "...", "message": "..."}}
        error = detail.get("error")
        if isinstance(error, dict):
            msg = error.get("message")
            if isinstance(msg, str):
                return msg
        # FastAPI default format: {"detail": "..."}
        d = detail.get("detail")
        if isinstance(d, str):
            return d
    return "Error de validacion"
