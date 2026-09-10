"""Schemas de servidores RTR para validacion RPKI."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from ixforge.enums import RPKITransport


class RPKIServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=3323, ge=1, le=65535)
    route_server_id: uuid.UUID | None = None
    transport: RPKITransport = RPKITransport.tcp
    refresh_time: int | None = Field(default=None, gt=0)
    retry_time: int | None = Field(default=None, gt=0)
    expire_time: int | None = Field(default=None, gt=0)


class RPKIServerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    route_server_id: uuid.UUID | None = None
    transport: RPKITransport | None = None
    refresh_time: int | None = Field(default=None, gt=0)
    retry_time: int | None = Field(default=None, gt=0)
    expire_time: int | None = Field(default=None, gt=0)


class RPKIServerRead(BaseModel):
    id: uuid.UUID
    ixp_id: uuid.UUID
    name: str
    host: str
    port: int
    route_server_id: uuid.UUID | None
    transport: RPKITransport
    refresh_time: int | None
    retry_time: int | None
    expire_time: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
