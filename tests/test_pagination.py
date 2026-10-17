"""Cursor pagination must continue past the first page for every sort column type"""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import CustomFieldEntityType, CustomFieldType, MemberState, PeeringPolicy
from ixforge.models.custom_field import CustomFieldDefinition
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.schemas.common import encode_cursor


async def _collect_pages(
    client: AsyncClient, path: str, headers: dict, params: dict | None = None
) -> list[str]:
    """Follow next_cursor until the last page and return every item id in order"""
    query = {**(params or {}), "limit": 1}
    ids: list[str] = []
    while True:
        resp = await client.get(path, headers=headers, params=query)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ids.extend(item["id"] for item in body["items"])
        if not body["has_more"]:
            return ids
        query["cursor"] = body["next_cursor"]


async def test_members_are_paginated_by_timestamp_cursor(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession, ixp: IXP
):
    expected = set()
    for asn in (64501, 64502, 64503):
        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name=f"Page Net {asn}",
            short_name=f"PN{asn}",
            asn=asn,
            state=MemberState.active,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        expected.add(str(member.id))
    await db_session.flush()

    ids = await _collect_pages(client, "/api/v1/members", auth_headers)

    assert len(ids) == len(set(ids))
    assert expected <= set(ids)


async def test_custom_fields_are_paginated_by_integer_cursor(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession, ixp: IXP
):
    expected = set()
    for order in (1, 2, 3):
        field = CustomFieldDefinition(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            entity_type=CustomFieldEntityType.member,
            field_name=f"page_field_{order}",
            field_type=CustomFieldType.string,
            display_order=order,
        )
        db_session.add(field)
        expected.add(str(field.id))
    await db_session.flush()

    ids = await _collect_pages(client, "/api/v1/custom-fields", auth_headers)

    assert len(ids) == len(set(ids))
    assert expected <= set(ids)


async def test_tampered_cursor_value_is_rejected_as_validation_error(
    client: AsyncClient, auth_headers: dict, ixp: IXP
):
    cursor = encode_cursor("not-a-timestamp", uuid.uuid4())

    resp = await client.get("/api/v1/members", headers=auth_headers, params={"cursor": cursor})

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
