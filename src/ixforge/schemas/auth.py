"""Auth and user management schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from ixforge.enums import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole = UserRole.member


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None
    role: UserRole | None = None


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class APIKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=list)


class APIKeyRead(BaseModel):
    id: uuid.UUID
    prefix: str
    name: str
    scopes: list[str]
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class APIKeyCreateResponse(APIKeyRead):
    """Returned only at creation time, includes the raw key."""

    raw_key: str
