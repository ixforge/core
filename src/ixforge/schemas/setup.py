"""Setup schemas."""

from pydantic import BaseModel, EmailStr, Field, field_validator

from ixforge.schemas.common import validate_country_code


class SetupIXP(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    short_name: str = Field(min_length=1, max_length=50)
    asn: int = Field(gt=0)
    website: str | None = Field(default=None, max_length=512)
    country: str = Field(min_length=2, max_length=2)
    city: str = Field(min_length=1, max_length=255)

    @field_validator("country")
    @classmethod
    def country_must_be_uppercase(cls, v: str) -> str:
        return validate_country_code(v)


class SetupAdmin(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8)


class SetupRequest(BaseModel):
    ixp: SetupIXP
    admin: SetupAdmin


class SetupStatusResponse(BaseModel):
    configured: bool
