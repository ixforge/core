"""VLAN schemas."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class VLANType(StrEnum):
    production = "production"
    quarantine = "quarantine"
    management = "management"
    other = "other"


class VLANCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    vid: int = Field(ge=1, le=4094)
    type: VLANType
    description: str | None = None
    extra_data: dict[str, Any] | None = None


class VLANUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    vid: int | None = Field(default=None, ge=1, le=4094)
    type: VLANType | None = None
    description: str | None = None
    extra_data: dict[str, Any] | None = None


class VLANRead(BaseModel):
    id: uuid.UUID
    ixp_id: uuid.UUID
    name: str
    vid: int
    type: VLANType
    description: str | None
    extra_data: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
