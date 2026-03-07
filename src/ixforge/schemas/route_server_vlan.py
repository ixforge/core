"""RouteServerVLAN schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class RouteServerVLANCreate(BaseModel):
    vlan_id: uuid.UUID


class RouteServerVLANRead(BaseModel):
    id: uuid.UUID
    ixp_id: uuid.UUID
    route_server_id: uuid.UUID
    vlan_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
