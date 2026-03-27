"""Route server template schemas."""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

_FILENAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]*(/[a-zA-Z0-9][a-zA-Z0-9_\-]*)*\.j2$")
_MAX_CONTENT_LENGTH = 524288  # 512 KB


def _validate_filename(v: str) -> str:
    if not _FILENAME_RE.match(v):
        raise ValueError("Filename must contain only alphanumeric, _, -, / characters and end with .j2")
    if v.count("/") > 1:
        raise ValueError("Filename cannot have more than one directory level")
    return v


class RSTemplateCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=_MAX_CONTENT_LENGTH)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        return _validate_filename(v)


class RSTemplateUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=_MAX_CONTENT_LENGTH)
    description: str | None = None
    # None means "don't update" (PATCH semantics via exclude_unset)


class RSTemplateRead(BaseModel):
    id: uuid.UUID
    ixp_id: uuid.UUID
    filename: str
    content: str
    description: str | None
    is_protected: bool
    updated_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RSTemplatePreviewRequest(BaseModel):
    route_server_id: uuid.UUID


class RSTemplatePreviewResponse(BaseModel):
    output: str
    errors: list[str] | None = None


class RSTemplateValidateRequest(BaseModel):
    content: str = Field(max_length=_MAX_CONTENT_LENGTH)


class RSTemplateValidateResponse(BaseModel):
    valid: bool
    errors: list[str]
