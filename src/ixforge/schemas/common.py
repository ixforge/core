"""Common schemas: ErrorResponse, CursorPage, pagination utilities."""

import base64
import uuid
from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


class CursorPage[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False


class CursorParams(BaseModel):
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


def encode_cursor(sort_value: str, record_id: uuid.UUID) -> str:
    raw = f"{sort_value}|{record_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[str, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        sort_value, id_str = raw.rsplit("|", 1)
        return sort_value, uuid.UUID(id_str)
    except Exception as exc:
        from ixforge.exceptions import ValidationError

        raise ValidationError(
            "Invalid pagination cursor",
            details={"cursor": "Malformed or corrupted cursor value"},
        ) from exc
