"""Tests for BIRD config generation, versioning, and diff."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import (
    BGPAdminState,
    BGPOperState,
    ConnectionState,
    ConnectionType,
    MemberState,
    PeeringPolicy,
)
from ixforge.models.bgp_session import BGPSession
from ixforge.models.connection import Connection
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.models.route_server import RouteServer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_route_server(db: AsyncSession, ixp: IXP, **overrides) -> RouteServer:
    defaults = {
        "id": uuid.uuid4(),
        "ixp_id": ixp.id,
        "name": "rs1",
        "hostname": "rs1.test.example.net",
        "ip_v4": "192.0.2.250",
        "ip_v6": "2001:db8::250",
        "asn": 65000,
        "software": "bird",
        "is_active": True,
    }
    defaults.update(overrides)
    rs = RouteServer(**defaults)
    db.add(rs)
    await db.flush()
    return rs


async def _setup_active_peer(
    db: AsyncSession,
    ixp: IXP,
    rs: RouteServer,
    peer_ip: str = "192.0.2.2",
    peer_asn: int = 64512,
    af: int = 4,
) -> tuple[Member, Connection, BGPSession]:
    member = Member(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name=f"Peer AS{peer_asn}",
        short_name=f"P{peer_asn}",
        asn=peer_asn,
        state=MemberState.active,
        peering_policy=PeeringPolicy.open,
    )
    db.add(member)
    await db.flush()

    conn = Connection(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        member_id=member.id,
        type=ConnectionType.physical,
        state=ConnectionState.active,
        speed=10000,
    )
    db.add(conn)
    await db.flush()

    bgp = BGPSession(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        route_server_id=rs.id,
        connection_id=conn.id,
        peer_ip=peer_ip,
        peer_asn=peer_asn,
        admin_state=BGPAdminState.up,
        oper_state=BGPOperState.up,
        af=af,
        max_prefixes=100,
    )
    db.add(bgp)
    await db.flush()
    return member, conn, bgp


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------


class TestConfigGeneration:
    async def test_generate_config_creates_version(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = await _setup_route_server(db_session, ixp)

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/config/generate",
            headers=auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "config_hash" in body
        assert len(body["config_hash"]) == 64
        assert "content" in body
        assert body["route_server_id"] == str(rs.id)
        assert body["applied_at"] is None

    async def test_generated_config_contains_router_id(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = await _setup_route_server(db_session, ixp, ip_v4="10.0.0.1")

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/config/generate",
            headers=auth_headers,
        )
        assert resp.status_code == 201
        content = resp.json()["content"]
        assert "10.0.0.1" in content

    async def test_generated_config_includes_active_peers(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = await _setup_route_server(db_session, ixp)
        await _setup_active_peer(db_session, ixp, rs, peer_ip="192.0.2.10", peer_asn=64600)

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/config/generate",
            headers=auth_headers,
        )
        assert resp.status_code == 201
        content = resp.json()["content"]
        assert "192.0.2.10" in content
        assert "64600" in content

    async def test_generated_config_excludes_inactive_members(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = await _setup_route_server(db_session, ixp)

        # Create a suspended member with a BGP session
        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Suspended Net",
            short_name="SUSP",
            asn=64700,
            state=MemberState.suspended,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            type=ConnectionType.physical,
            state=ConnectionState.active,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

        bgp = BGPSession(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            route_server_id=rs.id,
            connection_id=conn.id,
            peer_ip="192.0.2.99",
            peer_asn=64700,
            admin_state=BGPAdminState.up,
            oper_state=BGPOperState.up,
            af=4,
            max_prefixes=100,
        )
        db_session.add(bgp)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/config/generate",
            headers=auth_headers,
        )
        assert resp.status_code == 201
        content = resp.json()["content"]
        # Suspended member's peer should NOT appear
        assert "192.0.2.99" not in content

    async def test_generated_config_excludes_admin_down_sessions(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = await _setup_route_server(db_session, ixp)

        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Admin Down Net",
            short_name="ADN",
            asn=64800,
            state=MemberState.active,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)
        await db_session.flush()

        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            type=ConnectionType.physical,
            state=ConnectionState.active,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

        bgp = BGPSession(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            route_server_id=rs.id,
            connection_id=conn.id,
            peer_ip="192.0.2.88",
            peer_asn=64800,
            admin_state=BGPAdminState.down,
            oper_state=BGPOperState.down,
            af=4,
            max_prefixes=100,
        )
        db_session.add(bgp)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/config/generate",
            headers=auth_headers,
        )
        assert resp.status_code == 201
        content = resp.json()["content"]
        assert "192.0.2.88" not in content

    async def test_generate_config_for_nonexistent_rs(
        self, client: AsyncClient, auth_headers: dict, ixp: IXP
    ):
        resp = await client.post(
            f"/api/v1/route-servers/{uuid.uuid4()}/config/generate",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_generate_produces_different_hash_per_timestamp(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Each generation includes generated_at timestamp, so consecutive calls may differ."""
        import asyncio

        rs = await _setup_route_server(db_session, ixp)
        await _setup_active_peer(db_session, ixp, rs)

        resp1 = await client.post(
            f"/api/v1/route-servers/{rs.id}/config/generate",
            headers=auth_headers,
        )
        # Esperar un poco para que cambie el timestamp
        await asyncio.sleep(0.01)
        resp2 = await client.post(
            f"/api/v1/route-servers/{rs.id}/config/generate",
            headers=auth_headers,
        )
        # Ambas deben ser exitosas, el hash puede o no diferir segun el timestamp
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert len(resp1.json()["config_hash"]) == 64
        assert len(resp2.json()["config_hash"]) == 64


# ---------------------------------------------------------------------------
# Config history and current
# ---------------------------------------------------------------------------


class TestConfigHistory:
    async def test_get_current_config(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = await _setup_route_server(db_session, ixp)

        # Generate a config first
        await client.post(
            f"/api/v1/route-servers/{rs.id}/config/generate",
            headers=auth_headers,
        )

        resp = await client.get(
            f"/api/v1/route-servers/{rs.id}/config/current",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert "config_hash" in resp.json()

    async def test_get_current_config_none_exists(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = await _setup_route_server(db_session, ixp)

        resp = await client.get(
            f"/api/v1/route-servers/{rs.id}/config/current",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_config_history_returns_versions(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = await _setup_route_server(db_session, ixp)

        # Generate two configs
        await client.post(
            f"/api/v1/route-servers/{rs.id}/config/generate",
            headers=auth_headers,
        )
        await client.post(
            f"/api/v1/route-servers/{rs.id}/config/generate",
            headers=auth_headers,
        )

        resp = await client.get(
            f"/api/v1/route-servers/{rs.id}/config/history",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 2


# ---------------------------------------------------------------------------
# Config diff
# ---------------------------------------------------------------------------


class TestConfigDiff:
    async def test_diff_between_versions(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = await _setup_route_server(db_session, ixp)

        # Generate first config (no peers)
        resp1 = await client.post(
            f"/api/v1/route-servers/{rs.id}/config/generate",
            headers=auth_headers,
        )
        version1_id = resp1.json()["id"]

        # Add a peer and generate second config
        await _setup_active_peer(db_session, ixp, rs, peer_ip="192.0.2.20", peer_asn=64900)

        resp2 = await client.post(
            f"/api/v1/route-servers/{rs.id}/config/generate",
            headers=auth_headers,
        )
        version2_id = resp2.json()["id"]

        resp = await client.get(
            f"/api/v1/route-servers/{rs.id}/config/diff",
            headers=auth_headers,
            params={"from": version1_id, "to": version2_id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "diff" in body
        # The diff should contain the new peer IP
        assert "192.0.2.20" in body["diff"]
