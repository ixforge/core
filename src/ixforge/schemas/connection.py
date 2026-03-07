"""Connection schemas."""

import re
import uuid
from datetime import datetime
from typing import Any, cast

from pydantic import BaseModel, Field, field_validator, model_validator

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
    member_id: uuid.UUID
    port_id: uuid.UUID | None = None
    type: ConnectionType
    mac_address: str | None = Field(default=None, max_length=17)
    speed: int | None = Field(default=None, gt=0)
    extra_data: dict[str, Any] | None = None

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, v: str | None) -> str | None:
        return _validate_mac(v)


class ConnectionUpdate(BaseModel):
    port_id: uuid.UUID | None = None
    type: ConnectionType | None = None
    mac_address: str | None = Field(default=None, max_length=17)
    speed: int | None = Field(default=None, gt=0)
    extra_data: dict[str, Any] | None = None

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, v: str | None) -> str | None:
        return _validate_mac(v)


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
    member_name: str | None = None
    port_name: str | None = None

    model_config = {"from_attributes": True}

    @model_validator(mode="wrap")
    @classmethod
    def _populate_names(cls, values: Any, handler: Any) -> "ConnectionRead":
        obj = cast("ConnectionRead", handler(values))
        # Extract display names from loaded relationships (joinedload)
        # Gracefully skip if relationships are not loaded (lazy="raise")
        try:
            if values.member is not None:
                obj.member_name = values.member.name
        except Exception:
            pass
        try:
            if values.port is not None:
                obj.port_name = values.port.name
        except Exception:
            pass
        return obj


class ConnectionVLANCreate(BaseModel):
    vlan_id: uuid.UUID
    tagged: bool
