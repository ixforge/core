"""BGP session schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from ixforge.enums import BGPAdminState, BGPOperState


class BGPSessionCreate(BaseModel):
    route_server_id: uuid.UUID
    trunk_vlan_id: uuid.UUID
    af: Literal[4, 6]
    max_prefixes: int | None = Field(default=None, gt=0)


class BGPSessionRead(BaseModel):
    id: uuid.UUID
    route_server_id: uuid.UUID
    trunk_vlan_id: uuid.UUID
    peer_ip: str
    peer_asn: int
    admin_state: BGPAdminState
    oper_state: BGPOperState
    af: Literal[4, 6]
    max_prefixes: int | None
    created_at: datetime
    updated_at: datetime


class BGPSessionStatusUpdate(BaseModel):
    oper_state: BGPOperState
