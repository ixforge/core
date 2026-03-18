"""Connection schemas."""

import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ixforge.enums import ConnectionState as ConnectionState
from ixforge.enums import ConnectionType as ConnectionType

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")


def _validate_mac(v: str | None) -> str | None:
    if v is None:
        return None
    if not _MAC_RE.match(v):
        raise ValueError("Invalid MAC address format, expected XX:XX:XX:XX:XX:XX")
    return v.lower()


class ConnectionCreate(BaseModel):
    switch_id: uuid.UUID
    name: str = Field(min_length=1, max_length=100)
    type: ConnectionType
    speed: int = Field(gt=0)
    notes: str | None = None
    extra_data: dict[str, Any] | None = None


class ConnectionUpdate(BaseModel):
    switch_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: ConnectionType | None = None
    speed: int | None = Field(default=None, gt=0)
    notes: str | None = None
    extra_data: dict[str, Any] | None = None


class ConnectionRead(BaseModel):
    id: uuid.UUID
    trunk_id: uuid.UUID
    switch_id: uuid.UUID
    name: str
    type: ConnectionType
    state: ConnectionState
    speed: int
    notes: str | None
    extra_data: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
