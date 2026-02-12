"""Custom field definition endpoints."""

import uuid

from fastapi import APIRouter, Query, Response

from ixforge.api.deps import AdminUser, CurrentUser, DBSession, IXPId
from ixforge.models.custom_field import CustomFieldDefinition
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.custom_field import (
    CustomFieldDefinitionCreate,
    CustomFieldDefinitionRead,
    CustomFieldDefinitionUpdate,
)
from ixforge.services import custom_fields as cf_svc

custom_fields_router = APIRouter(prefix="/custom-fields", tags=["custom-fields"])


@custom_fields_router.get("", response_model=CursorPage[CustomFieldDefinitionRead])
async def list_custom_fields(
    db: DBSession,
    ixp_id: IXPId,
    _user: CurrentUser,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    entity_type: str | None = Query(default=None),
) -> CursorPage[CustomFieldDefinitionRead]:
    """List custom field definitions, optionally filtered by entity_type."""
    params = CursorParams(cursor=cursor, limit=limit)
    return await cf_svc.list_definitions(db, ixp_id, params, entity_type=entity_type)


@custom_fields_router.post("", response_model=CustomFieldDefinitionRead, status_code=201)
async def create_custom_field(
    body: CustomFieldDefinitionCreate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> CustomFieldDefinition:
    """Create a custom field definition (admin only)."""
    return await cf_svc.create(db, ixp_id, body)


@custom_fields_router.patch("/{definition_id}", response_model=CustomFieldDefinitionRead)
async def update_custom_field(
    definition_id: uuid.UUID,
    body: CustomFieldDefinitionUpdate,
    db: DBSession,
    _admin: AdminUser,
) -> CustomFieldDefinition:
    """Update a custom field definition (admin only)."""
    return await cf_svc.update(db, definition_id, body)


@custom_fields_router.delete("/{definition_id}", status_code=204)
async def delete_custom_field(
    definition_id: uuid.UUID,
    db: DBSession,
    _admin: AdminUser,
) -> Response:
    """Delete a custom field definition (admin only)."""
    await cf_svc.delete(db, definition_id)
    return Response(status_code=204)
