"""Schemas de peers de route server que no pertenecen a un miembro."""

import ipaddress
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from ixforge.enums import BGPAdminState, BGPOperState, RouteServerPeerType
from ixforge.services.template_filters import bird_community


def _validate_peer_ip(v: str) -> str:
    """La familia del peer se deriva de esta IP, asi que tiene que ser valida"""
    try:
        ipaddress.ip_address(v)
    except ValueError as exc:
        raise ValueError(f"IP invalida: {v}") from exc
    return v


def _validate_mark_community(v: str | None) -> str | None:
    """Reusa el filtro del template para rechazar lo que BIRD no puede expresar"""
    if v is None:
        return v
    bird_community(v)
    return v


class RouteServerPeerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    peer_ip: str
    peer_asn: int = Field(ge=1, le=4294967295)
    peer_type: RouteServerPeerType
    local_asn: int | None = Field(default=None, ge=1, le=4294967295)
    passive: bool = True
    mark_community: str | None = Field(default=None, max_length=32)
    max_prefixes: int | None = Field(default=None, gt=0)

    @field_validator("peer_ip")
    @classmethod
    def validate_peer_ip(cls, v: str) -> str:
        return _validate_peer_ip(v)

    @field_validator("mark_community")
    @classmethod
    def validate_mark_community(cls, v: str | None) -> str | None:
        return _validate_mark_community(v)


class RouteServerPeerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    peer_asn: int | None = Field(default=None, ge=1, le=4294967295)
    peer_type: RouteServerPeerType | None = None
    local_asn: int | None = Field(default=None, ge=1, le=4294967295)
    passive: bool | None = None
    mark_community: str | None = Field(default=None, max_length=32)
    max_prefixes: int | None = Field(default=None, gt=0)
    admin_state: BGPAdminState | None = None

    @field_validator("mark_community")
    @classmethod
    def validate_mark_community(cls, v: str | None) -> str | None:
        return _validate_mark_community(v)


class RouteServerPeerRead(BaseModel):
    id: uuid.UUID
    ixp_id: uuid.UUID
    route_server_id: uuid.UUID
    name: str
    description: str | None
    peer_ip: str
    peer_asn: int
    local_asn: int | None
    passive: bool
    peer_type: RouteServerPeerType
    mark_community: str | None
    max_prefixes: int | None
    admin_state: BGPAdminState
    oper_state: BGPOperState
    prefixes_imported: int | None
    prefixes_exported: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
