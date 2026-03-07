"""Tests for member extended fields."""

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import ContractType, MemberType
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.schemas.member import MemberCreate, MemberUpdate
from ixforge.services import members as svc


class TestMemberExtendedFields:
    async def test_create_member_with_extended_fields(self, db_session: AsyncSession, ixp: IXP) -> None:
        data = MemberCreate(
            name="Test ISP", short_name="TISP", asn=65001,
            member_type=MemberType.isp, description="A test ISP",
            city="Buenos Aires", country="AR",
            connection_date=date(2024, 1, 1),
            contract_start=date(2024, 1, 1), contract_renewal=date(2025, 1, 1),
            contract_type=ContractType.standard, notes="Notes here",
            skip_ixf_export=False,
        )
        member = await svc.create(db_session, ixp.id, data)
        assert member.member_type == "isp"
        assert member.country == "AR"
        assert member.skip_ixf_export is False

    async def test_update_member_extended_fields(self, db_session: AsyncSession, ixp: IXP) -> None:
        member = await svc.create(db_session, ixp.id, MemberCreate(name="ISP", short_name="I", asn=65002))
        updated = await svc.update(db_session, member.id, MemberUpdate(description="New desc", skip_ixf_export=True))
        assert updated.description == "New desc"
        assert updated.skip_ixf_export is True

    async def test_create_member_api_with_member_type(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict
    ) -> None:
        resp = await client.post("/api/v1/members", json={
            "name": "ISP Co", "short_name": "ISP", "asn": 65003,
            "member_type": "isp",
        }, headers=auth_headers)
        assert resp.status_code == 201
        assert resp.json()["member_type"] == "isp"
        assert resp.json()["logo_url"] is None  # no logo uploaded, field present but null

    async def test_invalid_member_type_rejected(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict
    ) -> None:
        resp = await client.post("/api/v1/members", json={
            "name": "ISP Co", "short_name": "ISPC", "asn": 65004,
            "member_type": "invalid_type",
        }, headers=auth_headers)
        assert resp.status_code == 422

    async def test_skip_ixf_export_filters_member(self, db_session: AsyncSession, ixp: IXP) -> None:
        """Members with skip_ixf_export=True are excluded from IXF export."""
        from ixforge.services.ixf_export import generate_ixf_member_export
        # Create an active member that should be exported
        m1 = await svc.create(db_session, ixp.id, MemberCreate(name="Export ISP", short_name="EX", asn=65005))
        # Create one that should be skipped
        m2 = await svc.create(db_session, ixp.id, MemberCreate(
            name="Skip ISP", short_name="SK", asn=65006, skip_ixf_export=True
        ))
        # Both in prospect state - IXF only includes active, so export will be empty
        # But _get_active_members should exclude the skipped one
        from ixforge.services.ixf_export import _get_active_members
        from ixforge.enums import MemberState
        from sqlalchemy import update as sa_update
        from ixforge.models.member import Member
        # Activate both members (bypass state machine for test)
        await db_session.execute(
            sa_update(Member).where(Member.id.in_([m1.id, m2.id])).values(state=MemberState.active)
        )
        await db_session.flush()
        active_members = await _get_active_members(db_session, ixp.id)
        member_asns = [m.asn for m in active_members]
        assert 65005 in member_asns
        assert 65006 not in member_asns
