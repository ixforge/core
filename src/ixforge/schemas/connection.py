"""Connection schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ixforge.enums import ConnectionState as ConnectionState, ConnectionType as ConnectionType


class ConnectionCreate(BaseModel):
    member_id: uuid.UUID
    port_id: uuid.UUID | None = None
    type: ConnectionType
    mac_address: str | None = Field(default=None, max_length=17)
    speed: int | None = Field(default=None, gt=0)
    extra_data: dict[str, Any] | None = None


class ConnectionUpdate(BaseModel):
    port_id: uuid.UUID | None = None
    type: ConnectionType | None = None
    state: ConnectionState | None = None
    mac_address: str | None = Field(default=None, max_length=17)
    speed: int | None = Field(default=None, gt=0)
    extra_data: dict[str, Any] | None = None


class ConnectionRead(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    port_id: uuid.UUID | None
    type: ConnectionType
    state: ConnectionState
    mac_address: str | None
    speed: int | None
    extra_data: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConnectionVLANCreate(BaseModel):
    vlan_id: uuid.UUID
    tagged: bool
