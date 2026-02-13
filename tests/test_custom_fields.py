"""Tests for Custom Field Definition CRUD endpoints."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import CustomFieldEntityType, CustomFieldType
from ixforge.models.custom_field import CustomFieldDefinition
from ixforge.models.ixp import IXP
from ixforge.models.user import User


class TestCustomFieldCRUD:
    async def test_create_custom_field(self, client: AsyncClient, auth_headers: dict, ixp: IXP):
        resp = await client.post(
            "/api/v1/custom-fields",
            headers=auth_headers,
            json={
                "entity_type": "member",
                "field_name": "contract_id",
                "field_type": "string",
                "is_required": False,
                "description": "External contract identifier",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["field_name"] == "contract_id"
        assert body["entity_type"] == "member"
        assert body["field_type"] == "string"

    async def test_create_custom_field_with_types(
        self, client: AsyncClient, auth_headers: dict, ixp: IXP
    ):
        """Test creating custom fields for different types."""
        for field_type in ["string", "integer", "boolean", "url", "email"]:
            resp = await client.post(
                "/api/v1/custom-fields",
                headers=auth_headers,
                json={
                    "entity_type": "connection",
                    "field_name": f"test_{field_type}",
                    "field_type": field_type,
                },
            )
            assert resp.status_code == 201
            assert resp.json()["field_type"] == field_type

    async def test_list_custom_fields(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        for i in range(3):
            cf = CustomFieldDefinition(
                id=uuid.uuid4(),
                ixp_id=ixp.id,
                entity_type=CustomFieldEntityType.member,
                field_name=f"list_field_{i}",
                field_type=CustomFieldType.string,
                display_order=i,
            )
            db_session.add(cf)
        await db_session.flush()

        resp = await client.get("/api/v1/custom-fields", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 3

    async def test_list_custom_fields_filter_entity_type(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        cf_member = CustomFieldDefinition(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            entity_type=CustomFieldEntityType.member,
            field_name="member_only",
            field_type=CustomFieldType.string,
        )
        cf_conn = CustomFieldDefinition(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            entity_type=CustomFieldEntityType.connection,
            field_name="conn_only",
            field_type=CustomFieldType.integer,
        )
        db_session.add_all([cf_member, cf_conn])
        await db_session.flush()

        resp = await client.get(
            "/api/v1/custom-fields",
            headers=auth_headers,
            params={"entity_type": "member"},
        )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["entity_type"] == "member"

    async def test_update_custom_field(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        cf = CustomFieldDefinition(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            entity_type=CustomFieldEntityType.member,
            field_name="updatable",
            field_type=CustomFieldType.string,
            is_required=False,
        )
        db_session.add(cf)
        await db_session.flush()

        resp = await client.patch(
            f"/api/v1/custom-fields/{cf.id}",
            headers=auth_headers,
            json={"is_required": True, "description": "Now required"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_required"] is True
        assert resp.json()["description"] == "Now required"

    async def test_delete_custom_field(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        cf = CustomFieldDefinition(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            entity_type=CustomFieldEntityType.member,
            field_name="deletable",
            field_type=CustomFieldType.boolean,
        )
        db_session.add(cf)
        await db_session.flush()

        resp = await client.delete(f"/api/v1/custom-fields/{cf.id}", headers=auth_headers)
        assert resp.status_code == 204

    async def test_member_can_list_custom_fields(
        self,
        client: AsyncClient,
        member_auth_headers: dict,
        member_user: User,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Member users can read custom field definitions."""
        resp = await client.get("/api/v1/custom-fields", headers=member_auth_headers)
        assert resp.status_code == 200

    async def test_member_cannot_create_custom_field(
        self,
        client: AsyncClient,
        member_auth_headers: dict,
        member_user: User,
        ixp: IXP,
    ):
        resp = await client.post(
            "/api/v1/custom-fields",
            headers=member_auth_headers,
            json={
                "entity_type": "member",
                "field_name": "hacker_field",
                "field_type": "string",
            },
        )
        assert resp.status_code == 403
