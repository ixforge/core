"""Route server schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class RouteServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    hostname: str = Field(min_length=1, max_length=255)
    ip_v4: str | None = None
    ip_v6: str | None = None
    asn: int = Field(gt=0, le=4294967295)
    software: str = "bird"
    is_active: bool = True


class RouteServerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    hostname: str | None = Field(default=None, min_length=1, max_length=255)
    ip_v4: str | None = None
    ip_v6: str | None = None
    asn: int | None = Field(default=None, gt=0, le=4294967295)
    software: str | None = None
    is_active: bool | None = None


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
