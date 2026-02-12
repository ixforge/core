"""IP pool and assignment schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class IPPoolCreate(BaseModel):
    vlan_id: uuid.UUID
    network: str = Field(max_length=50)
    gateway: str = Field(max_length=45)
    af: Literal[4, 6]


class IPPoolRead(BaseModel):
    id: uuid.UUID
    vlan_id: uuid.UUID
    network: str
    gateway: str
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
