"""Custom field definition schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from ixforge.enums import CustomFieldEntityType as CustomFieldEntityType, CustomFieldType as CustomFieldType


class CustomFieldDefinitionCreate(BaseModel):
    entity_type: CustomFieldEntityType
    field_name: str = Field(min_length=1, max_length=100)
    field_type: CustomFieldType
    is_required: bool = False
    default_value: str | None = None
    display_order: int = 0
    description: str | None = None


class CustomFieldDefinitionUpdate(BaseModel):
    field_type: CustomFieldType | None = None
    is_required: bool | None = None
    default_value: str | None = None
    display_order: int | None = None
    description: str | None = None


class CustomFieldDefinitionRead(BaseModel):
    id: uuid.UUID
    ixp_id: uuid.UUID
    entity_type: CustomFieldEntityType
    field_name: str
    field_type: CustomFieldType
    is_required: bool
    default_value: str | None
    display_order: int
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
