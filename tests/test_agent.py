"""Tests for Agent communication endpoints: config polling, status, heartbeat, config applied."""

import hashlib
import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import (
    BGPAdminState,
    BGPOperState,
    ConnectionState,
    ConnectionType,
    MemberState,
    PeeringPolicy,
    TrunkState,
    VLANType,
)
from ixforge.models.api_key import APIKey
from ixforge.models.bgp_session import BGPSession
from ixforge.models.config import ConfigVersion
from ixforge.models.connection import Connection
from ixforge.models.ixp import IXP
from ixforge.models.location import Location
from ixforge.models.member import Member
from ixforge.models.route_server import RouteServer
from ixforge.models.switch import Switch
from ixforge.models.trunk import Trunk, TrunkVLAN
from ixforge.models.user import User
from ixforge.models.vlan import VLAN
from ixforge.services.auth import hash_api_key

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RAW_AGENT_KEY = "ixf_agentkey_test_1234567890abcdef1234567890abcdef1234567890abcdef12345"


async def _setup_route_server(db: AsyncSession, ixp: IXP) -> RouteServer:
    rs = RouteServer(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name="rs-agent-test",
        ip_v4="192.0.2.250",
        ip_v6="2001:db8::250",
        is_active=True,
    )
    db.add(rs)
    await db.flush()
    return rs


async def _setup_agent_key(db: AsyncSession, rs: RouteServer, admin_user: User) -> str:
    """Create an agent API key scoped to the given route server. Returns raw key."""
    key_hash = hash_api_key(_RAW_AGENT_KEY)
    api_key = APIKey(
        id=uuid.uuid4(),
        key_hash=key_hash,
        prefix=_RAW_AGENT_KEY[:12],
        name="Agent Key",
        scopes=["agent:route_server"],
        user_id=None,
        route_server_id=rs.id,
        is_active=True,
    )
    db.add(api_key)
    await db.flush()
    return _RAW_AGENT_KEY


async def _setup_config_version(
    db: AsyncSession, rs: RouteServer, content: str = "# BIRD test config"
) -> ConfigVersion:
    config_hash = hashlib.sha256(content.encode()).hexdigest()
    cv = ConfigVersion(
        id=uuid.uuid4(),
        route_server_id=rs.id,
        content=content,
        config_hash=config_hash,
        generated_at=datetime.now(UTC),
    )
    db.add(cv)
    await db.flush()
    return cv


# ---------------------------------------------------------------------------
# Config polling
# ---------------------------------------------------------------------------


class TestAgentConfigPoll:
    async def test_get_config_with_valid_key(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs, admin_user)
        cv = await _setup_config_version(db_session, rs)

        resp = await client.get(
            f"/api/v1/route-servers/{rs.id}/agent/config",
            headers={"X-API-Key": raw_key},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["config_hash"] == cv.config_hash
        assert body["content"] == "# BIRD test config"

    async def test_get_config_without_key_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = await _setup_route_server(db_session, ixp)

        resp = await client.get(
            f"/api/v1/route-servers/{rs.id}/agent/config",
        )
        assert resp.status_code == 401

    async def test_get_config_wrong_key_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = await _setup_route_server(db_session, ixp)

        resp = await client.get(
            f"/api/v1/route-servers/{rs.id}/agent/config",
            headers={"X-API-Key": "ixf_invalid_key_value"},
        )
        assert resp.status_code == 401

    async def test_get_config_wrong_rs_scope_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        """Agent key for rs1 should not work on rs2."""
        rs1 = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs1, admin_user)

        rs2 = RouteServer(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="rs2",
            ip_v4="192.0.2.251",
            is_active=True,
        )
        db_session.add(rs2)
        await db_session.flush()

        resp = await client.get(
            f"/api/v1/route-servers/{rs2.id}/agent/config",
            headers={"X-API-Key": raw_key},
        )
        assert resp.status_code == 403

    async def test_get_config_no_config_exists(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs, admin_user)

        resp = await client.get(
            f"/api/v1/route-servers/{rs.id}/agent/config",
            headers={"X-API-Key": raw_key},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Status reporting
# ---------------------------------------------------------------------------


class TestAgentStatusReport:
    async def test_report_bgp_state_changes(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs, admin_user)

        # Create a member with a BGP session in unknown state
        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Status Test Net",
            short_name="STN",
            asn=64550,
            state=MemberState.active,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)

        location = Location(
            id=uuid.uuid4(), ixp_id=ixp.id, name="DC-status", city="Test", country="US",
        )
        db_session.add(location)
        await db_session.flush()

        switch = Switch(
            id=uuid.uuid4(), ixp_id=ixp.id, name="sw-status", location_id=location.id,
        )
        db_session.add(switch)
        await db_session.flush()

        trunk = Trunk(
            id=uuid.uuid4(), ixp_id=ixp.id, member_id=member.id,
            name="ae0", state=TrunkState.active,
        )
        db_session.add(trunk)
        vlan = VLAN(id=uuid.uuid4(), ixp_id=ixp.id, name="Peering", vid=100, type=VLANType.production)
        db_session.add(vlan)
        await db_session.flush()
        trunk_vlan = TrunkVLAN(id=uuid.uuid4(), ixp_id=ixp.id, trunk_id=trunk.id, vlan_id=vlan.id)
        db_session.add(trunk_vlan)

        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            trunk_id=trunk.id,
            switch_id=switch.id,
            name="eth-status",
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
            trunk_vlan_id=trunk_vlan.id,
            peer_ip="192.0.2.10",
            peer_asn=64550,
            admin_state=BGPAdminState.up,
            oper_state=BGPOperState.unknown,
            af=4,
            max_prefixes=100,
        )
        db_session.add(bgp)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/status",
            headers={"X-API-Key": raw_key},
            json={
                "sessions": [
                    {"peer_ip": "192.0.2.10", "oper_state": "up", "af": 4},
                ]
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated"] == 1
        assert body["unchanged"] == 0
        assert body["not_found"] == 0

    async def test_report_unknown_peer_counted_as_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs, admin_user)

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/status",
            headers={"X-API-Key": raw_key},
            json={
                "sessions": [
                    {"peer_ip": "10.99.99.99", "oper_state": "up", "af": 4},
                ]
            },
        )
        assert resp.status_code == 200
        assert resp.json()["not_found"] == 1

    async def test_report_unchanged_session(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs, admin_user)

        member = Member(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="Unchanged Net",
            short_name="UCN",
            asn=64560,
            state=MemberState.active,
            peering_policy=PeeringPolicy.open,
        )
        db_session.add(member)

        location = Location(
            id=uuid.uuid4(), ixp_id=ixp.id, name="DC-unch", city="Test", country="US",
        )
        db_session.add(location)
        await db_session.flush()

        switch = Switch(
            id=uuid.uuid4(), ixp_id=ixp.id, name="sw-unch", location_id=location.id,
        )
        db_session.add(switch)
        await db_session.flush()

        trunk = Trunk(
            id=uuid.uuid4(), ixp_id=ixp.id, member_id=member.id,
            name="ae0", state=TrunkState.active,
        )
        db_session.add(trunk)
        vlan = VLAN(id=uuid.uuid4(), ixp_id=ixp.id, name="Peering", vid=200, type=VLANType.production)
        db_session.add(vlan)
        await db_session.flush()
        trunk_vlan = TrunkVLAN(id=uuid.uuid4(), ixp_id=ixp.id, trunk_id=trunk.id, vlan_id=vlan.id)
        db_session.add(trunk_vlan)

        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            trunk_id=trunk.id,
            switch_id=switch.id,
            name="eth-unch",
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
            trunk_vlan_id=trunk_vlan.id,
            peer_ip="192.0.2.20",
            peer_asn=64560,
            admin_state=BGPAdminState.up,
            oper_state=BGPOperState.up,
            af=4,
            max_prefixes=100,
        )
        db_session.add(bgp)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/status",
            headers={"X-API-Key": raw_key},
            json={
                "sessions": [
                    {"peer_ip": "192.0.2.20", "oper_state": "up", "af": 4},
                ]
            },
        )
        assert resp.status_code == 200
        assert resp.json()["unchanged"] == 1


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


class TestAgentHeartbeat:
    async def test_heartbeat_acknowledged(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs, admin_user)
        cv = await _setup_config_version(db_session, rs)

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/heartbeat",
            headers={"X-API-Key": raw_key},
            json={
                "version": "0.1.0",
                "uptime_seconds": 3600.0,
                "current_config_hash": cv.config_hash,
                "bird_instances": [{"name": "bird_v4", "running": True, "uptime_seconds": 3600.0}],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["acknowledged"] is True
        assert body["config_hash_match"] is True

    async def test_heartbeat_config_hash_mismatch(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs, admin_user)
        await _setup_config_version(db_session, rs)

        wrong_hash = "a" * 64

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/heartbeat",
            headers={"X-API-Key": raw_key},
            json={
                "version": "0.1.0",
                "uptime_seconds": 100.0,
                "current_config_hash": wrong_hash,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["config_hash_match"] is False

    async def test_heartbeat_old_agent_gets_upgrade_header(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs, admin_user)
        cv = await _setup_config_version(db_session, rs)

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/heartbeat",
            headers={"X-API-Key": raw_key},
            json={
                "version": "0.0.1",
                "uptime_seconds": 100.0,
                "current_config_hash": cv.config_hash,
            },
        )
        assert resp.status_code == 200
        assert "x-ixforge-agent-upgrade" in resp.headers


# ---------------------------------------------------------------------------
# Config applied confirmation
# ---------------------------------------------------------------------------


class TestAgentConfigApplied:
    async def test_confirm_config_applied(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs, admin_user)
        cv = await _setup_config_version(db_session, rs)
        assert cv.applied_at is None

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/config/applied",
            headers={"X-API-Key": raw_key},
            json={"config_hash": cv.config_hash},
        )
        assert resp.status_code == 204

    async def test_confirm_nonexistent_config_hash(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs, admin_user)

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/config/applied",
            headers={"X-API-Key": raw_key},
            json={"config_hash": "b" * 64},
        )
        assert resp.status_code == 404
