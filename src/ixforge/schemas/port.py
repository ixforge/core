"""Port schemas."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PortType(StrEnum):
    member = "member"
    infra = "infra"
    unused = "unused"


class PortCreate(BaseModel):
    switch_id: uuid.UUID
    name: str = Field(min_length=1, max_length=100)
    speed: int = Field(gt=0)
    type: PortType
    member_id: uuid.UUID | None = None
    is_active: bool = True
    extra_data: dict[str, Any] | None = None


class PortUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    speed: int | None = Field(default=None, gt=0)
    type: PortType | None = None
    member_id: uuid.UUID | None = None
    is_active: bool | None = None
    extra_data: dict[str, Any] | None = None


class PortRead(BaseModel):
    id: uuid.UUID
    switch_id: uuid.UUID
    name: str
    speed: int
    type: PortType
    member_id: uuid.UUID | None
    is_active: bool
    extra_data: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
