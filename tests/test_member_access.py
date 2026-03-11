"""Tests for member-role access control on connections and BGP sessions."""

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
from ixforge.models.location import Location
from ixforge.models.member import Member
from ixforge.models.route_server import RouteServer
from ixforge.models.switch import Switch
from ixforge.models.user import User, UserRole
from ixforge.services.auth import create_access_token, hash_password

_conn_counter = 0


async def _create_connection(
    db: AsyncSession, ixp: IXP, member: Member, **overrides,
) -> Connection:
    """Create a Connection with required Location + Switch."""
    global _conn_counter
    _conn_counter += 1
    tag = f"ma-{_conn_counter}"

    location = Location(
        id=uuid.uuid4(), ixp_id=ixp.id, name=f"DC-{tag}", city="Test", country="US",
    )
    db.add(location)
    await db.flush()

    switch = Switch(
        id=uuid.uuid4(), ixp_id=ixp.id, name=f"sw-{tag}", location_id=location.id,
    )
    db.add(switch)
    await db.flush()

    defaults = {
        "id": uuid.uuid4(),
        "ixp_id": ixp.id,
        "member_id": member.id,
        "switch_id": switch.id,
        "name": f"eth-{tag}",
        "type": ConnectionType.physical,
        "state": ConnectionState.draft,
        "speed": 10000,
    }
    defaults.update(overrides)
    conn = Connection(**defaults)
    db.add(conn)
    await db.flush()
    return conn


async def _create_member(db: AsyncSession, ixp: IXP, **overrides) -> Member:
    defaults = {
        "id": uuid.uuid4(),
        "ixp_id": ixp.id,
        "name": f"Access Test Net {uuid.uuid4().hex[:6]}",
        "short_name": f"AT{uuid.uuid4().hex[:4]}",
        "asn": 64512 + hash(uuid.uuid4()) % 1000,
        "state": MemberState.active,
        "peering_policy": PeeringPolicy.open,
    }
    defaults.update(overrides)
    member = Member(**defaults)
    db.add(member)
    await db.flush()
    return member


async def _create_member_user(
    db: AsyncSession, member_id: uuid.UUID | None = None
) -> tuple[User, dict[str, str]]:
    """Create a member-role user and return (user, auth_headers)."""
    user = User(
        id=uuid.uuid4(),
        email=f"member-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password=hash_password("testpass123"),
        full_name="Test Member User",
        role=UserRole.member,
        member_id=member_id,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    token = create_access_token(subject=str(user.id))
    headers = {"Authorization": f"Bearer {token}"}
    return user, headers


class TestMemberConnectionAccess:
    async def test_member_can_list_own_connections(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        _user, headers = await _create_member_user(db_session, member_id=member.id)

        await _create_connection(db_session, ixp, member)

        resp = await client.get(
            "/api/v1/connections",
            headers=headers,
            params={"member_id": str(member.id)},
        )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 1

    async def test_member_cannot_list_other_member_connections(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member_a = await _create_member(db_session, ixp)
        member_b = await _create_member(db_session, ixp)
        _user, headers_a = await _create_member_user(db_session, member_id=member_a.id)

        resp = await client.get(
            "/api/v1/connections",
            headers=headers_a,
            params={"member_id": str(member_b.id)},
        )
        assert resp.status_code == 403

    async def test_member_can_get_own_connection(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        _user, headers = await _create_member_user(db_session, member_id=member.id)

        conn = await _create_connection(db_session, ixp, member)

        resp = await client.get(
            f"/api/v1/connections/{conn.id}",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == str(conn.id)

    async def test_member_cannot_get_other_connection(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member_a = await _create_member(db_session, ixp)
        member_b = await _create_member(db_session, ixp)
        _user, headers_a = await _create_member_user(db_session, member_id=member_a.id)

        conn_b = await _create_connection(db_session, ixp, member_b)

        resp = await client.get(
            f"/api/v1/connections/{conn_b.id}",
            headers=headers_a,
        )
        assert resp.status_code == 403

    async def test_member_without_member_id_cannot_list_connections(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        _user, headers = await _create_member_user(db_session, member_id=None)

        resp = await client.get(
            "/api/v1/connections",
            headers=headers,
            params={"member_id": str(member.id)},
        )
        assert resp.status_code == 403


class TestMemberBGPSessionAccess:
    async def test_member_can_list_own_bgp_sessions(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member = await _create_member(db_session, ixp)
        _user, headers = await _create_member_user(db_session, member_id=member.id)

        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name=f"rs-{uuid.uuid4().hex[:6]}",
            hostname="rs.test.example.net",
            ip_v4="192.0.2.250",
            asn=65000,
            is_active=True,
        )
        db_session.add(rs)
        await db_session.flush()

        conn = await _create_connection(db_session, ixp, member, state=ConnectionState.active)

        bgp = BGPSession(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            route_server_id=rs.id,
            connection_id=conn.id,
            peer_ip="192.0.2.10",
            peer_asn=member.asn,
            admin_state=BGPAdminState.up,
            oper_state=BGPOperState.up,
            af=4,
            max_prefixes=100,
        )
        db_session.add(bgp)
        await db_session.flush()

        resp = await client.get(
            "/api/v1/bgp-sessions",
            headers=headers,
            params={"route_server_id": str(rs.id)},
        )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 1

    async def test_member_cannot_get_other_bgp_session(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        member_a = await _create_member(db_session, ixp)
        member_b = await _create_member(db_session, ixp)
        _user, headers_a = await _create_member_user(db_session, member_id=member_a.id)

        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name=f"rs-{uuid.uuid4().hex[:6]}",
            hostname="rs.test.example.net",
            ip_v4="192.0.2.251",
            asn=65000,
            is_active=True,
        )
        db_session.add(rs)
        await db_session.flush()

        conn_b = await _create_connection(db_session, ixp, member_b, state=ConnectionState.active)

        bgp = BGPSession(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            route_server_id=rs.id,
            connection_id=conn_b.id,
            peer_ip="192.0.2.20",
            peer_asn=member_b.asn,
            admin_state=BGPAdminState.up,
            oper_state=BGPOperState.up,
            af=4,
            max_prefixes=100,
        )
        db_session.add(bgp)
        await db_session.flush()

        resp = await client.get(
            f"/api/v1/bgp-sessions/{bgp.id}",
            headers=headers_a,
        )
        assert resp.status_code == 403

    async def test_member_without_member_id_cannot_list_bgp_sessions(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        _user, headers = await _create_member_user(db_session, member_id=None)

        rs = RouteServer(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name=f"rs-{uuid.uuid4().hex[:6]}",
            hostname="rs.test.example.net",
            ip_v4="192.0.2.252",
            asn=65000,
            is_active=True,
        )
        db_session.add(rs)
        await db_session.flush()

        resp = await client.get(
            "/api/v1/bgp-sessions",
            headers=headers,
            params={"route_server_id": str(rs.id)},
        )
        assert resp.status_code == 403
