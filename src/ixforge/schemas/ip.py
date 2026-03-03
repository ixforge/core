"""IP pool and assignment schemas."""

import ipaddress
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class IPPoolCreate(BaseModel):
    vlan_id: uuid.UUID
    network: str = Field(max_length=50)
    af: Literal[4, 6]

    @model_validator(mode="after")
    def _validate_af_matches_network(self) -> "IPPoolCreate":
        """Validate that af matches the address family of network."""
        try:
            net = ipaddress.ip_network(self.network, strict=False)
        except ValueError:
            return self  # Let service layer handle invalid CIDR
        if net.version != self.af:
            raise ValueError(
                f"Address family mismatch: network is IPv{net.version} but af={self.af}"
            )
        return self


class IPPoolRead(BaseModel):
    id: uuid.UUID
    vlan_id: uuid.UUID
    network: str
    af: Literal[4, 6]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IPAssignmentCreate(BaseModel):
    pool_id: uuid.UUID
    connection_id: uuid.UUID
    address: str = Field(max_length=45)


class IPAssignmentRead(BaseModel):
    id: uuid.UUID
    pool_id: uuid.UUID
    connection_id: uuid.UUID
    address: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
