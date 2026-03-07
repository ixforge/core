"""RS IP assignment schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class RSIPAssignmentCreate(BaseModel):
    pool_id: uuid.UUID
    address: str | None = None


class RSIPAssignmentRead(BaseModel):
    id: uuid.UUID
    ixp_id: uuid.UUID
    route_server_id: uuid.UUID
    pool_id: uuid.UUID
    address: str
    af: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
