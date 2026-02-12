"""Switch schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SwitchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    hostname: str = Field(min_length=1, max_length=255)
    vendor: str | None = None
    model: str | None = None
    management_ip: str | None = None
    snmp_community: str | None = None
    is_active: bool = True
    extra_data: dict[str, Any] | None = None


class SwitchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    hostname: str | None = Field(default=None, min_length=1, max_length=255)
    vendor: str | None = None
    model: str | None = None
    management_ip: str | None = None
    snmp_community: str | None = None
    is_active: bool | None = None
    extra_data: dict[str, Any] | None = None


class SwitchRead(BaseModel):
    id: uuid.UUID
    ixp_id: uuid.UUID
    name: str
    hostname: str
    vendor: str | None
    model: str | None
    management_ip: str | None
    is_active: bool
    extra_data: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
