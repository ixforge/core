"""BGP session schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from ixforge.enums import BGPAdminState, BGPOperState


class BGPSessionRead(BaseModel):
    id: uuid.UUID
    route_server_id: uuid.UUID
    connection_id: uuid.UUID
    peer_ip: str
    peer_asn: int
    admin_state: BGPAdminState
    oper_state: BGPOperState
    af: Literal[4, 6]
    max_prefixes: int | None
    import_limit: int | None
    export_limit: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BGPSessionStatusUpdate(BaseModel):
    oper_state: BGPOperState
