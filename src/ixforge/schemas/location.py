"""Location schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from ixforge.schemas.common import validate_country_code


class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    city: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, min_length=2, max_length=2)

    @field_validator("country")
    @classmethod
    def country_must_be_uppercase(cls, v: str | None) -> str | None:
        return validate_country_code(v)


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    city: str | None = None
    country: str | None = Field(default=None, min_length=2, max_length=2)

    @field_validator("country")
    @classmethod
    def country_must_be_uppercase(cls, v: str | None) -> str | None:
        return validate_country_code(v)


class LocationRead(BaseModel):
    id: uuid.UUID
    ixp_id: uuid.UUID
    name: str
    city: str | None
    country: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
