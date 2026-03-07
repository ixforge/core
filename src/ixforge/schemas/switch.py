"""Switch schemas."""

import ipaddress
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


def _validate_management_ip(v: str | None) -> str | None:
    """Validate that a value is a valid IP address (IPv4 or IPv6)."""
    if v is not None:
        try:
            ipaddress.ip_address(v)
        except ValueError as exc:
            raise ValueError(f"Invalid IP address: {v}") from exc
    return v


class SwitchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    hostname: str = Field(min_length=1, max_length=255)
    vendor: str | None = None
    model: str | None = None
    management_ip: str | None = None
    snmp_community: str | None = None
    is_active: bool = True
    extra_data: dict[str, Any] | None = None
    location_id: uuid.UUID | None = None

    @field_validator("management_ip")
    @classmethod
    def validate_management_ip(cls, v: str | None) -> str | None:
        return _validate_management_ip(v)


class SwitchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    hostname: str | None = Field(default=None, min_length=1, max_length=255)
    vendor: str | None = None
    model: str | None = None
    management_ip: str | None = None
    snmp_community: str | None = None
    is_active: bool | None = None
    extra_data: dict[str, Any] | None = None
    location_id: uuid.UUID | None = None

    @field_validator("management_ip")
    @classmethod
    def validate_management_ip(cls, v: str | None) -> str | None:
        return _validate_management_ip(v)


class SwitchRead(BaseModel):
    id: uuid.UUID
    ixp_id: uuid.UUID
    location_id: uuid.UUID | None
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
