"""IXP schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from ixforge.schemas.common import validate_country_code


class IXPUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    website: str | None = None
    country: str | None = Field(default=None, min_length=2, max_length=2)
    city: str | None = None
    peeringdb_id: int | None = None

    @field_validator("country")
    @classmethod
    def country_must_be_uppercase(cls, v: str | None) -> str | None:
        return validate_country_code(v)


class IXPRead(BaseModel):
    id: uuid.UUID
    name: str
    short_name: str
    asn: int
    website: str | None
    country: str | None
    city: str | None
    peeringdb_id: int | None
    extra_data: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
