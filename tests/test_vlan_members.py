"""Tests for VLANMember service and API endpoints."""


import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import MemberState, VLANType
from ixforge.exceptions import ConflictError, NotFoundError, ValidationError
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.models.vlan import VLAN
from ixforge.services import vlan_members as svc


class TestVLANMemberService:
    async def test_add_member_to_private_vlan(self, db_session: AsyncSession, ixp: IXP) -> None:
        vlan = VLAN(ixp_id=ixp.id, name="Private1", vid=100, type=VLANType.private)
        member = Member(ixp_id=ixp.id, name="ISP", short_name="I", asn=65200, state=MemberState.prospect)
        db_session.add(vlan)
        db_session.add(member)
        await db_session.flush()
        vm = await svc.add_member(db_session, ixp.id, vlan.id, member.id)
        assert vm.vlan_id == vlan.id
        assert vm.member_id == member.id

    async def test_add_member_to_non_private_vlan_raises(self, db_session: AsyncSession, ixp: IXP) -> None:
        vlan = VLAN(ixp_id=ixp.id, name="Prod", vid=101, type=VLANType.production)
        member = Member(ixp_id=ixp.id, name="ISP2", short_name="I2", asn=65201, state=MemberState.prospect)
        db_session.add(vlan)
        db_session.add(member)
        await db_session.flush()
        with pytest.raises(ValidationError):
            await svc.add_member(db_session, ixp.id, vlan.id, member.id)

    async def test_remove_member_from_vlan(self, db_session: AsyncSession, ixp: IXP) -> None:
        vlan = VLAN(ixp_id=ixp.id, name="Private2", vid=102, type=VLANType.private)
        member = Member(ixp_id=ixp.id, name="ISP3", short_name="I3", asn=65202, state=MemberState.prospect)
        db_session.add(vlan)
        db_session.add(member)
        await db_session.flush()
        await svc.add_member(db_session, ixp.id, vlan.id, member.id)
        await svc.remove_member(db_session, ixp.id, vlan.id, member.id)

    async def test_add_duplicate_member_raises(self, db_session: AsyncSession, ixp: IXP) -> None:
        vlan = VLAN(ixp_id=ixp.id, name="Private3", vid=103, type=VLANType.private)
        member = Member(ixp_id=ixp.id, name="ISP4", short_name="I4", asn=65203, state=MemberState.prospect)
        db_session.add(vlan)
        db_session.add(member)
        await db_session.flush()
        await svc.add_member(db_session, ixp.id, vlan.id, member.id)
        with pytest.raises(ConflictError):
            await svc.add_member(db_session, ixp.id, vlan.id, member.id)

    async def test_remove_nonexistent_member_raises(self, db_session: AsyncSession, ixp: IXP) -> None:
        vlan = VLAN(ixp_id=ixp.id, name="Private4", vid=104, type=VLANType.private)
        member = Member(ixp_id=ixp.id, name="ISP5", short_name="I5", asn=65204, state=MemberState.prospect)
        db_session.add(vlan)
        db_session.add(member)
        await db_session.flush()
        with pytest.raises(NotFoundError):
            await svc.remove_member(db_session, ixp.id, vlan.id, member.id)

    async def test_add_member_wrong_ixp_vlan_raises(self, db_session: AsyncSession, ixp: IXP) -> None:
        other_ixp = IXP(name="Other IXP", short_name="OTH", asn=65300, country="CL", city="X")
        db_session.add(other_ixp)
        await db_session.flush()
        vlan = VLAN(ixp_id=other_ixp.id, name="OtherVLAN", vid=200, type=VLANType.private)
        member = Member(ixp_id=ixp.id, name="ISP6", short_name="I6", asn=65205, state=MemberState.prospect)
        db_session.add(vlan)
        db_session.add(member)
        await db_session.flush()
        with pytest.raises(NotFoundError):
            await svc.add_member(db_session, ixp.id, vlan.id, member.id)


class TestVLANMemberAPI:
    async def test_list_vlan_members_empty(self, client: AsyncClient, ixp: IXP, auth_headers: dict[str, str], db_session: AsyncSession) -> None:
        vlan = VLAN(ixp_id=ixp.id, name="APIVLAN", vid=300, type=VLANType.private)
        db_session.add(vlan)
        await db_session.flush()
        resp = await client.get(f"/api/v1/vlans/{vlan.id}/members", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_add_vlan_member_api(self, client: AsyncClient, ixp: IXP, auth_headers: dict[str, str], db_session: AsyncSession) -> None:
        vlan = VLAN(ixp_id=ixp.id, name="APIVLAN2", vid=301, type=VLANType.private)
        member = Member(ixp_id=ixp.id, name="APIISP", short_name="AI", asn=65400, state=MemberState.prospect)
        db_session.add(vlan)
        db_session.add(member)
        await db_session.flush()
        resp = await client.post(
            f"/api/v1/vlans/{vlan.id}/members",
            json={"member_id": str(member.id)},
            headers=auth_headers,
        )
        assert resp.status_code == 201

    async def test_remove_vlan_member_api(self, client: AsyncClient, ixp: IXP, auth_headers: dict[str, str], db_session: AsyncSession) -> None:
        vlan = VLAN(ixp_id=ixp.id, name="APIVLAN3", vid=302, type=VLANType.private)
        member = Member(ixp_id=ixp.id, name="APIISP2", short_name="AI2", asn=65401, state=MemberState.prospect)
        db_session.add(vlan)
        db_session.add(member)
        await db_session.flush()
        # Add first
        await client.post(
            f"/api/v1/vlans/{vlan.id}/members",
            json={"member_id": str(member.id)},
            headers=auth_headers,
        )
        # Then remove
        resp = await client.delete(
            f"/api/v1/vlans/{vlan.id}/members/{member.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204

    async def test_add_member_to_production_vlan_returns_422(self, client: AsyncClient, ixp: IXP, auth_headers: dict[str, str], db_session: AsyncSession) -> None:
        vlan = VLAN(ixp_id=ixp.id, name="ProdVLAN", vid=303, type=VLANType.production)
        member = Member(ixp_id=ixp.id, name="APIISP3", short_name="AI3", asn=65402, state=MemberState.prospect)
        db_session.add(vlan)
        db_session.add(member)
        await db_session.flush()
        resp = await client.post(
            f"/api/v1/vlans/{vlan.id}/members",
            json={"member_id": str(member.id)},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_add_duplicate_member_returns_409(self, client: AsyncClient, ixp: IXP, auth_headers: dict[str, str], db_session: AsyncSession) -> None:
        vlan = VLAN(ixp_id=ixp.id, name="APIVLAN4", vid=304, type=VLANType.private)
        member = Member(ixp_id=ixp.id, name="APIISP4", short_name="AI4", asn=65403, state=MemberState.prospect)
        db_session.add(vlan)
        db_session.add(member)
        await db_session.flush()
        await client.post(
            f"/api/v1/vlans/{vlan.id}/members",
            json={"member_id": str(member.id)},
            headers=auth_headers,
        )
        resp = await client.post(
            f"/api/v1/vlans/{vlan.id}/members",
            json={"member_id": str(member.id)},
            headers=auth_headers,
        )
        assert resp.status_code == 409
