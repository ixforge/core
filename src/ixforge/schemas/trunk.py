"""Trunk schemas."""

import uuid
from datetime import datetime
from typing import Any, cast

from pydantic import BaseModel, Field, field_validator, model_validator

from ixforge.enums import TrunkState
from ixforge.schemas.connection import _validate_mac


class TrunkCreate(BaseModel):
    member_id: uuid.UUID
    name: str = Field(min_length=1, max_length=100)
    mac_address: str | None = Field(default=None, max_length=17)
    notes: str | None = None
    extra_data: dict[str, Any] | None = None

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, v: str | None) -> str | None:
        return _validate_mac(v)


class TrunkUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    mac_address: str | None = Field(default=None, max_length=17)
    notes: str | None = None
    extra_data: dict[str, Any] | None = None

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, v: str | None) -> str | None:
        return _validate_mac(v)


class TrunkRead(BaseModel):
    id: uuid.UUID
    ixp_id: uuid.UUID
    member_id: uuid.UUID
    name: str
    state: TrunkState
    mac_address: str | None
    notes: str | None
    extra_data: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    member_name: str | None = None

    model_config = {"from_attributes": True}

    @model_validator(mode="wrap")
    @classmethod
    def _populate_names(cls, values: Any, handler: Any) -> "TrunkRead":
        obj = cast("TrunkRead", handler(values))
        try:
            if values.member is not None:
                obj.member_name = values.member.name
        except AttributeError:
            pass
        return obj


class TrunkVLANCreate(BaseModel):
    vlan_id: uuid.UUID


class TrunkVLANRead(BaseModel):
    id: uuid.UUID
    trunk_id: uuid.UUID
    vlan_id: uuid.UUID
    vlan_name: str | None = None
    vid: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="wrap")
    @classmethod
    def _populate_vlan(cls, values: Any, handler: Any) -> "TrunkVLANRead":
        obj = cast("TrunkVLANRead", handler(values))
        try:
            if values.vlan is not None:
                obj.vlan_name = values.vlan.name
                obj.vid = values.vlan.vid
        except AttributeError:
            pass
        return obj


class TrunkStateTransition(BaseModel):
    state: TrunkState
