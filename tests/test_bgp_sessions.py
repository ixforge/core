"""Tests for BGP Session endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import (
    BGPAdminState,
    BGPOperState,
    MemberState,
    PeeringPolicy,
    TrunkState,
    VLANType,
)
from ixforge.models.bgp_session import BGPSession
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.models.route_server import RouteServer
from ixforge.models.trunk import Trunk, TrunkVLAN
from ixforge.models.vlan import VLAN


async def _create_trunk_with_vlan(
    db: AsyncSession, ixp: IXP, member: Member,
) -> TrunkVLAN:
    """Create a trunk in active state with a VLAN assignment."""
    trunk = Trunk(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        member_id=member.id,
        name=f"ae{uuid.uuid4().hex[:4]}",
        state=TrunkState.active,
    )
    db.add(trunk)
    await db.flush()

    vlan = VLAN(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name=f"Test VLAN {uuid.uuid4().hex[:6]}",
        vid=100 + hash(uuid.uuid4()) % 3900,
        type=VLANType.production,
    )
    db.add(vlan)
    await db.flush()

    trunk_vlan = TrunkVLAN(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        trunk_id=trunk.id,
        vlan_id=vlan.id,
    )
    db.add(trunk_vlan)
    await db.flush()

    return trunk_vlan


async def _add_ip_assignment(
    db: AsyncSession,
    ixp: IXP,
    trunk_vlan: TrunkVLAN,
    address: str = "192.0.2.10",
    af: int = 4,
) -> IPAssignment:
    """Create an IPPool + IPAssignment for a trunk_vlan so peer_ip can be resolved."""
    pool = IPPool(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        vlan_id=trunk_vlan.vlan_id,
        network="192.0.2.0/24" if af == 4 else "2001:db8::/64",
        af=af,
    )
    db.add(pool)
    await db.flush()

    ip = IPAssignment(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        pool_id=pool.id,
        trunk_vlan_id=trunk_vlan.id,
        address=address,
    )
    db.add(ip)
    await db.flush()
    return ip


async def _setup_bgp_session(db: AsyncSession, ixp: IXP) -> tuple[RouteServer, BGPSession]:
    rs = RouteServer(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name="rs-bgp",
        ip_v4="192.0.2.250",
        is_active=True,
    )
    db.add(rs)

    member = Member(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name="BGP Test Net",
        short_name="BGPT",
        asn=64600,
        state=MemberState.active,
        peering_policy=PeeringPolicy.open,
    )
    db.add(member)
    await db.flush()

    trunk_vlan = await _create_trunk_with_vlan(db, ixp, member)

    await _add_ip_assignment(db, ixp, trunk_vlan, address="192.0.2.10")

    bgp = BGPSession(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        route_server_id=rs.id,
        trunk_vlan_id=trunk_vlan.id,
        admin_state=BGPAdminState.up,
        oper_state=BGPOperState.up,
        af=4,
        max_prefixes=100,
    )
    db.add(bgp)
    await db.flush()
    return rs, bgp


class TestBGPSessionEndpoints:
    async def test_list_bgp_sessions(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs, _bgp = await _setup_bgp_session(db_session, ixp)

        resp = await client.get(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            params={"route_server_id": str(rs.id)},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1
        assert items[0]["peer_asn"] == 64600

    async def test_get_bgp_session(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        _rs, bgp = await _setup_bgp_session(db_session, ixp)

        resp = await client.get(f"/api/v1/bgp-sessions/{bgp.id}", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["peer_ip"] == "192.0.2.10"
        assert body["admin_state"] == "up"
        assert body["oper_state"] == "up"

    async def test_update_admin_state_to_down(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        _rs, bgp = await _setup_bgp_session(db_session, ixp)

        resp = await client.patch(
            f"/api/v1/bgp-sessions/{bgp.id}",
            headers=auth_headers,
            json={"admin_state": "down"},
        )
        assert resp.status_code == 200
        assert resp.json()["admin_state"] == "down"

    async def test_update_admin_state_to_up(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        _rs, bgp = await _setup_bgp_session(db_session, ixp)
        bgp.admin_state = BGPAdminState.down
        await db_session.flush()

        resp = await client.patch(
            f"/api/v1/bgp-sessions/{bgp.id}",
            headers=auth_headers,
            json={"admin_state": "up"},
        )
        assert resp.status_code == 200
        assert resp.json()["admin_state"] == "up"

    async def test_get_nonexistent_bgp_session(
        self, client: AsyncClient, auth_headers: dict, ixp: IXP
    ):
        resp = await client.get(f"/api/v1/bgp-sessions/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404


class TestBGPSessionCreate:
    async def test_create_bgp_session(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="rs-create",
            ip_v4="192.0.2.251",
            is_active=True,
        )
        db_session.add(rs)

        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Create Test Net",
            short_name="CTN",
            asn=64700,
            state=MemberState.active,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        trunk_vlan = await _create_trunk_with_vlan(db_session, ixp, member)

        await _add_ip_assignment(db_session, ixp, trunk_vlan, address="192.0.2.10")

        resp = await client.post(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            json={
                "route_server_id": str(rs.id),
                "trunk_vlan_id": str(trunk_vlan.id),
                "af": 4,
                "max_prefixes": 100,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["route_server_id"] == str(rs.id)
        assert body["trunk_vlan_id"] == str(trunk_vlan.id)
        assert body["peer_ip"] == "192.0.2.10"
        assert body["peer_asn"] == 64700
        assert body["af"] == 4
        assert body["admin_state"] == "up"
        assert body["oper_state"] == "unknown"
        assert body["max_prefixes"] == 100

    async def test_create_bgp_session_duplicate_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="rs-dup",
            ip_v4="192.0.2.252",
            is_active=True,
        )
        db_session.add(rs)

        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Dup Test Net",
            short_name="DTN",
            asn=64701,
            state=MemberState.active,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        trunk_vlan = await _create_trunk_with_vlan(db_session, ixp, member)

        await _add_ip_assignment(db_session, ixp, trunk_vlan, address="192.0.2.20")

        payload = {
            "route_server_id": str(rs.id),
            "trunk_vlan_id": str(trunk_vlan.id),
            "af": 4,
        }

        # First creation should succeed
        resp1 = await client.post(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            json=payload,
        )
        assert resp1.status_code == 201

        # Duplicate should be rejected (same RS + trunk_vlan + AF)
        resp2 = await client.post(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            json=payload,
        )
        assert resp2.status_code == 409

    async def test_create_bgp_session_inactive_trunk_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="rs-inact",
            ip_v4="192.0.2.253",
            is_active=True,
        )
        db_session.add(rs)

        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Inactive Test Net",
            short_name="ITN",
            asn=64702,
            state=MemberState.active,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        # Trunk in draft state (not active)
        trunk = Trunk(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            name="ae-draft",
            state=TrunkState.draft,
        )
        db_session.add(trunk)
        await db_session.flush()

        vlan = VLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Draft VLAN",
            vid=500,
            type=VLANType.production,
        )
        db_session.add(vlan)
        await db_session.flush()

        trunk_vlan = TrunkVLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            trunk_id=trunk.id,
            vlan_id=vlan.id,
        )
        db_session.add(trunk_vlan)
        await db_session.flush()

        resp = await client.post(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            json={
                "route_server_id": str(rs.id),
                "trunk_vlan_id": str(trunk_vlan.id),
                "af": 4,
            },
        )
        assert resp.status_code == 422

    async def test_create_bgp_session_without_ip_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Creating a BGP session without an IP assignment for the AF should fail."""
        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="rs-no-ip",
            ip_v4="192.0.2.249",
            is_active=True,
        )
        db_session.add(rs)

        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="No IP Test Net",
            short_name="NIT",
            asn=64704,
            state=MemberState.active,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        trunk_vlan = await _create_trunk_with_vlan(db_session, ixp, member)
        # NO IPPool/IPAssignment created

        resp = await client.post(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            json={
                "route_server_id": str(rs.id),
                "trunk_vlan_id": str(trunk_vlan.id),
                "af": 4,
            },
        )
        assert resp.status_code == 422

    async def test_create_bgp_session_wrong_ixp_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        # RS belongs to a different IXP
        other_ixp = IXP(
            id=uuid.uuid4(),
            name="Other IXP",
            short_name=f"OIX{uuid.uuid4().hex[:4]}",
            asn=65999,
        )
        db_session.add(other_ixp)
        await db_session.flush()

        rs_other = RouteServer(
            id=uuid.uuid4(),
            ixp_id=other_ixp.id,
            name="rs-other",
            ip_v4="192.0.2.254",
            is_active=True,
        )
        db_session.add(rs_other)

        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Wrong IXP Test Net",
            short_name="WTN",
            asn=64703,
            state=MemberState.active,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        trunk_vlan = await _create_trunk_with_vlan(db_session, ixp, member)

        resp = await client.post(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            json={
                "route_server_id": str(rs_other.id),
                "trunk_vlan_id": str(trunk_vlan.id),
                "af": 4,
            },
        )
        assert resp.status_code == 404


class TestBGPSessionConstraints:
    async def test_create_bgp_session_af_5_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        ixp: IXP,
    ):
        """af must be 4 or 6 (Literal), af=5 should fail Pydantic validation."""
        resp = await client.post(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            json={
                "route_server_id": str(uuid.uuid4()),
                "trunk_vlan_id": str(uuid.uuid4()),
                "af": 5,
            },
        )
        assert resp.status_code == 422


class TestBGPSessionDelete:
    async def test_delete_bgp_session(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        _rs, bgp = await _setup_bgp_session(db_session, ixp)

        resp = await client.delete(
            f"/api/v1/bgp-sessions/{bgp.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204

    async def test_delete_bgp_session_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict,
        ixp: IXP,
    ):
        resp = await client.delete(
            f"/api/v1/bgp-sessions/{uuid.uuid4()}",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_delete_bgp_session_wrong_ixp_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Deleting a BGP session from a different IXP should return 404."""
        other_ixp = IXP(
            id=uuid.uuid4(),
            name="Other IXP Del",
            short_name=f"OID{uuid.uuid4().hex[:4]}",
            asn=65999,
        )
        db_session.add(other_ixp)
        await db_session.flush()

        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=other_ixp.id,
            name="rs-other-del",
            is_active=True,
        )
        db_session.add(rs)

        member = Member(
            id=uuid.uuid4(),
            ixp_id=other_ixp.id,
            name="Other Del Net",
            short_name="ODN",
            asn=64800,
            state=MemberState.active,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        trunk_vlan = await _create_trunk_with_vlan(db_session, other_ixp, member)

        bgp = BGPSession(
            id=uuid.uuid4(),
            ixp_id=other_ixp.id,
            route_server_id=rs.id,
            trunk_vlan_id=trunk_vlan.id,
            admin_state=BGPAdminState.up,
            oper_state=BGPOperState.unknown,
            af=4,
        )
        db_session.add(bgp)
        await db_session.flush()

        resp = await client.delete(
            f"/api/v1/bgp-sessions/{bgp.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 404


class TestBGPSessionConfigRegeneration:
    """Las mutaciones de sesiones BGP deben encolar la regeneracion de config del RS."""

    @pytest.fixture
    def defer_spy(self, monkeypatch):
        calls: list[tuple[str, str]] = []

        async def fake_defer(route_server_id, triggered_by):
            calls.append((str(route_server_id), triggered_by))

        monkeypatch.setattr(
            "ixforge.tasks.config.defer_rs_config_regeneration", fake_defer,
        )
        return calls

    async def test_create_defers_regeneration(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
        defer_spy: list,
    ):
        rs = RouteServer(
            id=uuid.uuid4(), ixp_id=ixp.id, name="rs-defer", ip_v4="192.0.2.249", is_active=True,
        )
        db_session.add(rs)
        member = Member(
            id=uuid.uuid4(), ixp_id=ixp.id, name="Defer Net", short_name="DEFN",
            asn=64710, state=MemberState.active, peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()
        trunk_vlan = await _create_trunk_with_vlan(db_session, ixp, member)
        await _add_ip_assignment(db_session, ixp, trunk_vlan, address="192.0.2.20")

        resp = await client.post(
            "/api/v1/bgp-sessions",
            headers=auth_headers,
            json={
                "route_server_id": str(rs.id),
                "trunk_vlan_id": str(trunk_vlan.id),
                "af": 4,
            },
        )
        assert resp.status_code == 201
        assert (str(rs.id), "bgp_session.created") in defer_spy

    async def test_delete_defers_regeneration(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
        defer_spy: list,
    ):
        rs, bgp = await _setup_bgp_session(db_session, ixp)

        resp = await client.delete(f"/api/v1/bgp-sessions/{bgp.id}", headers=auth_headers)
        assert resp.status_code == 204
        assert (str(rs.id), "bgp_session.deleted") in defer_spy

    async def test_admin_state_change_defers_regeneration(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
        defer_spy: list,
    ):
        rs, bgp = await _setup_bgp_session(db_session, ixp)

        resp = await client.patch(
            f"/api/v1/bgp-sessions/{bgp.id}",
            headers=auth_headers,
            json={"admin_state": "down"},
        )
        assert resp.status_code == 200
        assert (str(rs.id), "bgp_session.admin_state_changed") in defer_spy
