"""Member schemas."""

import os
import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from ixforge.enums import ContractType, MemberType
from ixforge.enums import MemberState as MemberState
from ixforge.enums import PeeringPolicy as PeeringPolicy
from ixforge.schemas.common import validate_country_code


class MemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    short_name: str = Field(min_length=1, max_length=50)
    asn: int = Field(gt=0, le=4294967295)
    peering_policy: PeeringPolicy = PeeringPolicy.open
    peering_policy_details: str | None = None
    website: str | None = None
    peeringdb_id: int | None = None
    extra_data: dict[str, Any] | None = None
    member_type: MemberType | None = None
    description: str | None = None
    city: str | None = None
    country: str | None = Field(default=None, min_length=2, max_length=2)
    connection_date: date | None = None
    contract_type: ContractType | None = None
    notes: str | None = None
    skip_ixf_export: bool = False

    @field_validator("country")
    @classmethod
    def country_must_be_uppercase(cls, v: str | None) -> str | None:
        return validate_country_code(v)


class MemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    short_name: str | None = Field(default=None, min_length=1, max_length=50)
    peering_policy: PeeringPolicy | None = None
    peering_policy_details: str | None = None
    website: str | None = None
    peeringdb_id: int | None = None
    extra_data: dict[str, Any] | None = None
    member_type: MemberType | None = None
    description: str | None = None
    city: str | None = None
    country: str | None = Field(default=None, min_length=2, max_length=2)
    connection_date: date | None = None
    contract_type: ContractType | None = None
    notes: str | None = None
    skip_ixf_export: bool | None = None

    @field_validator("country")
    @classmethod
    def country_must_be_uppercase(cls, v: str | None) -> str | None:
        return validate_country_code(v)


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
    member_type: MemberType | None
    description: str | None
    city: str | None
    country: str | None
    connection_date: date | None
    contract_type: ContractType | None
    notes: str | None
    skip_ixf_export: bool
    logo_url: str | None = None

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _compute_logo_url(self) -> "MemberRead":
        from ixforge.config import get_settings

        settings = get_settings()
        path = os.path.join(settings.media_root, "members", str(self.id), "logo.png")
        self.logo_url = f"{settings.media_url}/members/{self.id}/logo.png" if os.path.exists(path) else None
        return self


class ASNLookupResponse(BaseModel):
    asn: int
    name: str | None


class MemberStateTransition(BaseModel):
    state: MemberState
