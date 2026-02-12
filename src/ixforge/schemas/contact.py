"""Contact schemas."""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ContactRole(StrEnum):
    noc = "noc"
    admin = "admin"
    technical = "technical"
    billing = "billing"


class ContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=1, max_length=255)
    phone: str | None = None
    role: ContactRole


class ContactUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = None
    role: ContactRole | None = None


class ContactRead(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    name: str
    email: str
    phone: str | None
    role: ContactRole
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
