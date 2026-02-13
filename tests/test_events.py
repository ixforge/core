"""Tests for Event (audit log) endpoint."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.models.event import Event
from ixforge.models.ixp import IXP
from ixforge.models.user import User


class TestEventEndpoints:
    async def test_list_events_as_admin(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        # Seed some events
        for i in range(3):
            ev = Event(
                id=uuid.uuid4(),
                ixp_id=ixp.id,
                type="member.created",
                resource_type="member",
                resource_id=uuid.uuid4(),
                data={"name": f"Test Net {i}", "asn": 64512 + i},
            )
            db_session.add(ev)
        await db_session.flush()

        resp = await client.get("/api/v1/events", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 3

    async def test_list_events_filter_by_resource_type(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        ev = Event(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            type="connection.created",
            resource_type="connection",
            resource_id=uuid.uuid4(),
            data={},
        )
        db_session.add(ev)
        await db_session.flush()

        resp = await client.get(
            "/api/v1/events",
            headers=auth_headers,
            params={"resource_type": "connection"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        for item in items:
            assert item["resource_type"] == "connection"

    async def test_member_user_sees_only_own_events(
        self,
        client: AsyncClient,
        member_auth_headers: dict,
        member_user: User,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Member users should only see events for their own member resource.

        Since member_user has no member_id assigned, this should return 403.
        """
        resp = await client.get("/api/v1/events", headers=member_auth_headers)
        assert resp.status_code == 403
