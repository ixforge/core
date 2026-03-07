"""Custom field service: definition CRUD and extra_data validation."""

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import ConflictError, NotFoundError, ValidationError
from ixforge.models.custom_field import CustomFieldDefinition
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.custom_field import (
    CustomFieldDefinitionCreate,
    CustomFieldDefinitionRead,
    CustomFieldDefinitionUpdate,
    CustomFieldType,
)
from ixforge.services.base import paginate

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL_RE = re.compile(r"^https?://[a-zA-Z0-9][-a-zA-Z0-9.]*\.[a-zA-Z]{2,}(?:[/?#]\S*)?$")


async def create(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    data: CustomFieldDefinitionCreate,
) -> CustomFieldDefinition:
    """Create a custom field definition."""
    definition = CustomFieldDefinition(
        ixp_id=ixp_id,
        entity_type=data.entity_type,
        field_name=data.field_name,
        field_type=data.field_type,
        is_required=data.is_required,
        default_value=data.default_value,
        display_order=data.display_order,
        description=data.description,
    )
    session.add(definition)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            f"Custom field '{data.field_name}' already exists for entity type '{data.entity_type}'"
        ) from exc
    return definition


async def get(session: AsyncSession, ixp_id: uuid.UUID, definition_id: uuid.UUID) -> CustomFieldDefinition:
    """Get a custom field definition by id or raise NotFoundError."""
    definition = await session.get(CustomFieldDefinition, definition_id)
    if definition is None or definition.ixp_id != ixp_id:
        raise NotFoundError("CustomFieldDefinition", str(definition_id))
    return definition


async def list_definitions(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    params: CursorParams,
    *,
    entity_type: str | None = None,
) -> CursorPage[CustomFieldDefinitionRead]:
    """List custom field definitions for an IXP."""
    stmt = select(CustomFieldDefinition).where(CustomFieldDefinition.ixp_id == ixp_id)
    if entity_type is not None:
        stmt = stmt.where(CustomFieldDefinition.entity_type == entity_type)
    return await paginate(
        session,
        stmt,
        params,
        sort_column=CustomFieldDefinition.display_order,
        id_column=CustomFieldDefinition.id,
        schema=CustomFieldDefinitionRead,
    )


async def update(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    definition_id: uuid.UUID,
    data: CustomFieldDefinitionUpdate,
) -> CustomFieldDefinition:
    """Update a custom field definition."""
    definition = await get(session, ixp_id, definition_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(definition, field, value)
    await session.flush()
    await session.refresh(definition)
    return definition


async def delete(session: AsyncSession, ixp_id: uuid.UUID, definition_id: uuid.UUID) -> None:
    """Delete a custom field definition."""
    definition = await get(session, ixp_id, definition_id)
    await session.delete(definition)
    await session.flush()


def _validate_field_value(field_name: str, field_type: str, value: object) -> None:
    """Validate a single field value against its expected type."""
    if field_type == CustomFieldType.string:
        if not isinstance(value, str):
            raise ValidationError(
                f"Custom field '{field_name}' must be a string, got {type(value).__name__}"
            )
    elif field_type == CustomFieldType.integer:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValidationError(
                f"Custom field '{field_name}' must be an integer, got {type(value).__name__}"
            )
    elif field_type == CustomFieldType.boolean:
        if not isinstance(value, bool):
            raise ValidationError(
                f"Custom field '{field_name}' must be a boolean, got {type(value).__name__}"
            )
    elif field_type == CustomFieldType.url:
        if not isinstance(value, str) or not _URL_RE.match(value):
            raise ValidationError(
                f"Custom field '{field_name}' must be a valid URL (http:// or https://)"
            )
    elif field_type == CustomFieldType.email and (
        not isinstance(value, str) or not _EMAIL_RE.match(value)
    ):
        raise ValidationError(f"Custom field '{field_name}' must be a valid email address")


async def validate_extra_data(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    entity_type: str,
    extra_data: dict[str, Any] | None,
) -> None:
    """Validate extra_data against custom field definitions for the given entity type.

    Checks:
    - All required fields are present.
    - All provided fields match a known definition.
    - All values match their declared type.
    """
    stmt = select(CustomFieldDefinition).where(
        CustomFieldDefinition.ixp_id == ixp_id,
        CustomFieldDefinition.entity_type == entity_type,
    )
    result = await session.execute(stmt)
    definitions = list(result.scalars().all())

    if not definitions:
        provided = extra_data or {}
        if provided:
            raise ValidationError(
                f"No custom fields defined for entity type '{entity_type}'; "
                f"extra_data must be empty"
            )
        return

    definitions_by_name = {d.field_name: d for d in definitions}
    provided = extra_data or {}

    # Check required fields
    for definition in definitions:
        if definition.is_required and definition.field_name not in provided:
            raise ValidationError(
                f"Required custom field '{definition.field_name}' is missing "
                f"for entity type '{entity_type}'"
            )

    # Check provided fields against definitions
    for field_name, value in provided.items():
        defn = definitions_by_name.get(field_name)
        if defn is None:
            raise ValidationError(
                f"Unknown custom field '{field_name}' for entity type '{entity_type}'"
            )
        # None is valid for optional fields (clears the value)
        if value is None:
            if defn.is_required:
                raise ValidationError(f"Required custom field '{field_name}' cannot be null")
            continue
        _validate_field_value(field_name, defn.field_type, value)
