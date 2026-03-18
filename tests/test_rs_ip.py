"""Tests for RS IP assignment service and API."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import ConnectionType, MemberState, PeeringPolicy, TrunkState, VLANType
from ixforge.exceptions import ConflictError, NotFoundError, ValidationError
from ixforge.models.connection import Connection
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.ixp import IXP
from ixforge.models.location import Location
from ixforge.models.member import Member
from ixforge.models.route_server import RouteServer
from ixforge.models.switch import Switch
from ixforge.models.trunk import Trunk, TrunkVLAN
from ixforge.models.vlan import VLAN
from ixforge.schemas.rs_ip import RSIPAssignmentCreate
from ixforge.services import rs_ip as svc


@pytest.fixture
async def rs(db_session: AsyncSession, ixp: IXP) -> RouteServer:
    r = RouteServer(ixp_id=ixp.id, name="RS1")
    db_session.add(r)
    await db_session.flush()
    return r


@pytest.fixture
async def pool_v4(db_session: AsyncSession, ixp: IXP) -> IPPool:
    vlan = VLAN(ixp_id=ixp.id, name="IXP", vid=10, type=VLANType.production)
    db_session.add(vlan)
    await db_session.flush()
    p = IPPool(ixp_id=ixp.id, vlan_id=vlan.id, network="192.0.2.0/24", af=4)
    db_session.add(p)
    await db_session.flush()
    return p


class TestRSIPService:
    async def test_assign_ip_sequential(self, db_session: AsyncSession, ixp: IXP, rs: RouteServer, pool_v4: IPPool) -> None:
        result = await svc.assign(db_session, ixp.id, rs.id, RSIPAssignmentCreate(pool_id=pool_v4.id))
        assert result.address.startswith("192.0.2.")
        assert result.af == 4
        await db_session.refresh(rs)
        assert rs.ip_v4 == result.address

    async def test_assign_ip_manual(self, db_session: AsyncSession, ixp: IXP, rs: RouteServer, pool_v4: IPPool) -> None:
        result = await svc.assign(db_session, ixp.id, rs.id, RSIPAssignmentCreate(pool_id=pool_v4.id, address="192.0.2.100"))
        assert result.address == "192.0.2.100"

    async def test_assign_duplicate_af_raises(self, db_session: AsyncSession, ixp: IXP, rs: RouteServer, pool_v4: IPPool) -> None:
        await svc.assign(db_session, ixp.id, rs.id, RSIPAssignmentCreate(pool_id=pool_v4.id))
        with pytest.raises(ConflictError):
            await svc.assign(db_session, ixp.id, rs.id, RSIPAssignmentCreate(pool_id=pool_v4.id))

    async def test_release_clears_rs_ip(self, db_session: AsyncSession, ixp: IXP, rs: RouteServer, pool_v4: IPPool) -> None:
        result = await svc.assign(db_session, ixp.id, rs.id, RSIPAssignmentCreate(pool_id=pool_v4.id))
        await svc.release(db_session, ixp.id, rs.id, result.id)
        await db_session.refresh(rs)
        assert rs.ip_v4 is None

    async def test_assign_wrong_pool_ixp_raises(self, db_session: AsyncSession, ixp: IXP, rs: RouteServer) -> None:
        other_ixp = IXP(name="Other IXP", short_name="OTH", asn=65200, country="AR", city="X")
        db_session.add(other_ixp)
        await db_session.flush()
        vlan2 = VLAN(ixp_id=other_ixp.id, name="V", vid=20, type=VLANType.production)
        db_session.add(vlan2)
        await db_session.flush()
        pool2 = IPPool(ixp_id=other_ixp.id, vlan_id=vlan2.id, network="10.0.0.0/24", af=4)
        db_session.add(pool2)
        await db_session.flush()
        with pytest.raises(ValidationError):
            await svc.assign(db_session, ixp.id, rs.id, RSIPAssignmentCreate(pool_id=pool2.id))

    async def test_assign_sequential_skips_member_assignments(
        self, db_session: AsyncSession, ixp: IXP, rs: RouteServer, pool_v4: IPPool
    ) -> None:
        member = Member(
            ixp_id=ixp.id,
            name="Test Member",
            short_name="TM",
            asn=64512,
            state=MemberState.provisioning,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()
        location = Location(
            id=uuid.uuid4(), ixp_id=ixp.id, name="DC-test", city="Test", country="US",
        )
        db_session.add(location)
        await db_session.flush()
        switch = Switch(
            id=uuid.uuid4(), ixp_id=ixp.id, name="sw-test", location_id=location.id,
        )
        db_session.add(switch)
        await db_session.flush()
        trunk = Trunk(ixp_id=ixp.id, member_id=member.id, name="ae0", state=TrunkState.active)
        db_session.add(trunk)
        vlan = VLAN(id=uuid.uuid4(), ixp_id=ixp.id, name="Peering", vid=100, type=VLANType.production)
        db_session.add(vlan)
        await db_session.flush()
        trunk_vlan = TrunkVLAN(ixp_id=ixp.id, trunk_id=trunk.id, vlan_id=vlan.id)
        db_session.add(trunk_vlan)
        connection = Connection(
            ixp_id=ixp.id,
            trunk_id=trunk.id,
            type=ConnectionType.physical,
            switch_id=switch.id,
            name="eth-test",
            speed=1000,
        )
        db_session.add(connection)
        await db_session.flush()
        member_assign = IPAssignment(
            ixp_id=ixp.id,
            pool_id=pool_v4.id,
            trunk_vlan_id=trunk_vlan.id,
            address="192.0.2.1",
        )
        db_session.add(member_assign)
        await db_session.flush()
        result = await svc.assign(db_session, ixp.id, rs.id, RSIPAssignmentCreate(pool_id=pool_v4.id))
        assert result.address != "192.0.2.1"
        assert result.address.startswith("192.0.2.")

    async def test_release_nonexistent_assignment_raises(self, db_session: AsyncSession, ixp: IXP, rs: RouteServer) -> None:
        with pytest.raises(NotFoundError):
            await svc.release(db_session, ixp.id, rs.id, uuid.uuid4())

    async def test_assign_rs_not_found_raises(self, db_session: AsyncSession, ixp: IXP, pool_v4: IPPool) -> None:
        with pytest.raises(NotFoundError):
            await svc.assign(db_session, ixp.id, uuid.uuid4(), RSIPAssignmentCreate(pool_id=pool_v4.id))

    async def test_assign_rs_wrong_ixp_raises(self, db_session: AsyncSession, ixp: IXP, rs: RouteServer, pool_v4: IPPool) -> None:
        """Assigning an IP to a RS that belongs to a different IXP should raise NotFoundError"""
        other_ixp = IXP(name="Other IXP RS", short_name="ORS", asn=65300, country="AR", city="X")
        db_session.add(other_ixp)
        await db_session.flush()
        with pytest.raises(NotFoundError):
            await svc.assign(db_session, other_ixp.id, rs.id, RSIPAssignmentCreate(pool_id=pool_v4.id))

    async def test_list_assignments_rs_wrong_ixp_raises(self, db_session: AsyncSession, ixp: IXP, rs: RouteServer) -> None:
        """Listing assignments for a RS that belongs to a different IXP should raise NotFoundError"""
        other_ixp = IXP(name="Other IXP List", short_name="ORL", asn=65301, country="AR", city="X")
        db_session.add(other_ixp)
        await db_session.flush()
        with pytest.raises(NotFoundError):
            await svc.list_assignments(db_session, other_ixp.id, rs.id)


class TestRSIPGlobalUniqueness:
    async def test_rs_ip_sequential_skips_globally_used_ip(
        self, db_session: AsyncSession, ixp: IXP, rs: RouteServer, pool_v4: IPPool
    ) -> None:
        """Sequential RS IP allocation must skip IPs assigned in a different pool with same address."""
        # Create a second VLAN and pool with the same network range
        vlan2 = VLAN(ixp_id=ixp.id, name="IXP2-gu", vid=50, type=VLANType.production)
        db_session.add(vlan2)
        await db_session.flush()
        pool2 = IPPool(ixp_id=ixp.id, vlan_id=vlan2.id, network="192.0.2.0/24", af=4)
        db_session.add(pool2)
        await db_session.flush()

        member = Member(
            ixp_id=ixp.id,
            name="Global Uniq Member",
            short_name="GUM",
            asn=64513,
            state=MemberState.provisioning,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()
        location = Location(
            id=uuid.uuid4(), ixp_id=ixp.id, name="DC-gu", city="Test", country="US",
        )
        db_session.add(location)
        await db_session.flush()
        switch = Switch(
            id=uuid.uuid4(), ixp_id=ixp.id, name="sw-gu", location_id=location.id,
        )
        db_session.add(switch)
        await db_session.flush()
        trunk = Trunk(ixp_id=ixp.id, member_id=member.id, name="ae0", state=TrunkState.active)
        db_session.add(trunk)
        await db_session.flush()
        trunk_vlan = TrunkVLAN(ixp_id=ixp.id, trunk_id=trunk.id, vlan_id=vlan2.id)
        db_session.add(trunk_vlan)
        connection = Connection(
            ixp_id=ixp.id,
            trunk_id=trunk.id,
            type=ConnectionType.physical,
            switch_id=switch.id,
            name="eth-gu",
            speed=1000,
        )
        db_session.add(connection)
        await db_session.flush()
        # Assign .1 from pool2 (different pool, same address range)
        member_assign = IPAssignment(
            ixp_id=ixp.id,
            pool_id=pool2.id,
            trunk_vlan_id=trunk_vlan.id,
            address="192.0.2.1",
        )
        db_session.add(member_assign)
        await db_session.flush()
        # Sequential RS IP allocation from pool_v4 should skip .1 and assign .2
        result = await svc.assign(
            db_session, ixp.id, rs.id, RSIPAssignmentCreate(pool_id=pool_v4.id)
        )
        assert result.address == "192.0.2.2"


class TestRSIPAPI:
    async def test_list_rs_ips_empty(self, client: AsyncClient, ixp: IXP, auth_headers: dict[str, str], db_session: AsyncSession) -> None:
        rs = RouteServer(ixp_id=ixp.id, name="RS-api")
        db_session.add(rs)
        await db_session.flush()
        resp = await client.get(f"/api/v1/route-servers/{rs.id}/ips", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_assign_rs_ip_api(self, client: AsyncClient, ixp: IXP, auth_headers: dict[str, str], db_session: AsyncSession) -> None:
        rs = RouteServer(ixp_id=ixp.id, name="RS-api2")
        vlan = VLAN(ixp_id=ixp.id, name="IXP-api", vid=30, type=VLANType.production)
        db_session.add(rs)
        db_session.add(vlan)
        await db_session.flush()
        pool = IPPool(ixp_id=ixp.id, vlan_id=vlan.id, network="198.51.100.0/24", af=4)
        db_session.add(pool)
        await db_session.flush()
        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/ips",
            json={"pool_id": str(pool.id)},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["af"] == 4
        assert data["address"].startswith("198.51.100.")

    async def test_release_rs_ip_api(self, client: AsyncClient, ixp: IXP, auth_headers: dict[str, str], db_session: AsyncSession) -> None:
        rs = RouteServer(ixp_id=ixp.id, name="RS-api3")
        vlan = VLAN(ixp_id=ixp.id, name="IXP-api3", vid=40, type=VLANType.production)
        db_session.add(rs)
        db_session.add(vlan)
        await db_session.flush()
        pool = IPPool(ixp_id=ixp.id, vlan_id=vlan.id, network="203.0.113.0/24", af=4)
        db_session.add(pool)
        await db_session.flush()
        assign_resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/ips",
            json={"pool_id": str(pool.id)},
            headers=auth_headers,
        )
        assert assign_resp.status_code == 201
        assignment_id = assign_resp.json()["id"]
        delete_resp = await client.delete(
            f"/api/v1/route-servers/{rs.id}/ips/{assignment_id}",
            headers=auth_headers,
        )
        assert delete_resp.status_code == 204
