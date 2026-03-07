"""Route server schemas."""

import ipaddress
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def _validate_ipv4(v: str | None) -> str | None:
    """Validate that a value is a valid IPv4 address."""
    if v is not None:
        try:
            addr = ipaddress.ip_address(v)
            if addr.version != 4:
                raise ValueError("ip_v4 must be an IPv4 address")
        except ValueError as exc:
            raise ValueError(f"Invalid IPv4 address: {v}") from exc
    return v


def _validate_ipv6(v: str | None) -> str | None:
    """Validate that a value is a valid IPv6 address."""
    if v is not None:
        try:
            addr = ipaddress.ip_address(v)
            if addr.version != 6:
                raise ValueError("ip_v6 must be an IPv6 address")
        except ValueError as exc:
            raise ValueError(f"Invalid IPv6 address: {v}") from exc
    return v


class RouteServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    hostname: str = Field(min_length=1, max_length=255)
    ip_v4: str | None = None
    ip_v6: str | None = None
    asn: int = Field(gt=0, le=4294967295)
    software: str = "bird"
    is_active: bool = True

    @field_validator("ip_v4")
    @classmethod
    def validate_ip_v4(cls, v: str | None) -> str | None:
        return _validate_ipv4(v)

    @field_validator("ip_v6")
    @classmethod
    def validate_ip_v6(cls, v: str | None) -> str | None:
        return _validate_ipv6(v)


class RouteServerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    hostname: str | None = Field(default=None, min_length=1, max_length=255)
    ip_v4: str | None = None
    ip_v6: str | None = None
    asn: int | None = Field(default=None, gt=0, le=4294967295)
    software: str | None = None
    is_active: bool | None = None

    @field_validator("ip_v4")
    @classmethod
    def validate_ip_v4(cls, v: str | None) -> str | None:
        return _validate_ipv4(v)

    @field_validator("ip_v6")
    @classmethod
    def validate_ip_v6(cls, v: str | None) -> str | None:
        return _validate_ipv6(v)


class RouteServerRead(BaseModel):
    id: uuid.UUID
    ixp_id: uuid.UUID
    name: str
    hostname: str
    ip_v4: str | None
    ip_v6: str | None
    asn: int
    software: str
    is_active: bool
    last_heartbeat_at: datetime | None
    agent_version: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
