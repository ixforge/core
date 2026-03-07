"""VLANMember schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class VLANMemberCreate(BaseModel):
    member_id: uuid.UUID


class VLANMemberRead(BaseModel):
    id: uuid.UUID
    ixp_id: uuid.UUID
    vlan_id: uuid.UUID
    member_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
