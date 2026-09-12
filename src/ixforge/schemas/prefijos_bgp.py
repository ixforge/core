"""Schemas de los prefijos que anuncia un miembro."""

from datetime import datetime

from pydantic import BaseModel

from ixforge.enums import PrefixEventType


class PrefijoAnunciadoRead(BaseModel):
    prefix: str
    as_path: list[int]
    communities: list[str]
    first_seen_at: datetime
    last_seen_at: datetime


class EventoDePrefijoRead(BaseModel):
    prefix: str
    event_type: PrefixEventType
    as_path: list[int]
    previous_as_path: list[int] | None
    communities: list[str]
    previous_communities: list[str] | None
    occurred_at: datetime
    route_server: str
