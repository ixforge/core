"""BGP session schemas."""

import ipaddress
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ixforge.enums import BGPAdminState, BGPOperState


class BGPSessionCreate(BaseModel):
    route_server_id: uuid.UUID
    trunk_vlan_id: uuid.UUID
    peer_ip: str
    peer_asn: int = Field(..., gt=0)
    af: Literal[4, 6]
    max_prefixes: int | None = Field(default=None, gt=0)
    import_limit: int | None = Field(default=None, gt=0)
    export_limit: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _validate_peer_ip_matches_af(self) -> "BGPSessionCreate":
        try:
            addr = ipaddress.ip_address(self.peer_ip)
        except ValueError as exc:
            raise ValueError(f"Invalid IP address: {self.peer_ip}") from exc
        if addr.is_loopback or addr.is_multicast or addr.is_unspecified or addr.is_link_local:
            raise ValueError(
                f"peer_ip {self.peer_ip} cannot be loopback, multicast, unspecified, or link-local"
            )
        if self.af == 4 and addr.version != 4:
            raise ValueError("peer_ip must be an IPv4 address when af=4")
        if self.af == 6 and addr.version != 6:
            raise ValueError("peer_ip must be an IPv6 address when af=6")
        return self


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
    import_limit: int | None
    export_limit: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BGPSessionStatusUpdate(BaseModel):
    oper_state: BGPOperState
