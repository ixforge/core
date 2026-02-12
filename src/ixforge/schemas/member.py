"""Member schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ixforge.enums import MemberState as MemberState
from ixforge.enums import PeeringPolicy as PeeringPolicy


class MemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    short_name: str = Field(min_length=1, max_length=50)
    asn: int = Field(gt=0, le=4294967295)
    peering_policy: PeeringPolicy = PeeringPolicy.open
    peering_policy_details: str | None = None
    website: str | None = None
    peeringdb_id: int | None = None
    extra_data: dict[str, Any] | None = None


class MemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    short_name: str | None = Field(default=None, min_length=1, max_length=50)
    peering_policy: PeeringPolicy | None = None
    peering_policy_details: str | None = None
    website: str | None = None
    peeringdb_id: int | None = None
    extra_data: dict[str, Any] | None = None


class MemberRead(BaseModel):
    id: uuid.UUID
    ixp_id: uuid.UUID
    name: str
    short_name: str
    asn: int
    state: MemberState
    peering_policy: PeeringPolicy
    peering_policy_details: str | None
    website: str | None
    peeringdb_id: int | None
    extra_data: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MemberStateTransition(BaseModel):
    state: MemberState
