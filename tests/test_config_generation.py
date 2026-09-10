"""Tests for BIRD config generation, versioning, and diff."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import (
    BGPAdminState,
    BGPOperState,
    ConnectionState,
    ConnectionType,
    MemberState,
    MemberType,
    PeeringPolicy,
    TrunkState,
    VLANType,
)
from ixforge.models.bgp_session import BGPSession
from ixforge.models.connection import Connection
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.ixp import IXP
from ixforge.models.location import Location
from ixforge.models.member import Member
from ixforge.models.member_prefix_filter import MemberPrefixFilter
from ixforge.models.route_server import RouteServer
from ixforge.models.switch import Switch
from ixforge.models.trunk import Trunk, TrunkVLAN
from ixforge.models.vlan import VLAN
from ixforge.services.default_templates import install_default_templates


@pytest.fixture(autouse=True)
async def _templates(db_session: AsyncSession, ixp: IXP) -> None:
    # En produccion el setup instala los templates default para el IXP
    await install_default_templates(db_session, ixp.id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_route_server(db: AsyncSession, ixp: IXP, **overrides) -> RouteServer:
    defaults = {
        "id": uuid.uuid4(),
        "ixp_id": ixp.id,
        "name": "rs1",
        "ip_v4": "192.0.2.250",
        "ip_v6": "2001:db8::250",
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
) -> tuple[Member, Trunk, BGPSession]:
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

    trunk = Trunk(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        member_id=member.id,
        name=f"ae-{peer_asn}",
        state=TrunkState.active,
    )
    db.add(trunk)
    await db.flush()

    vlan = VLAN(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name=f"VLAN-{peer_asn}",
        vid=100 + peer_asn % 3900,
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

    location = Location(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name=f"DC-{peer_asn}",
        city="Test",
        country="US",
    )
    db.add(location)
    await db.flush()

    switch = Switch(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name=f"sw-{peer_asn}",
        location_id=location.id,
    )
    db.add(switch)
    await db.flush()

    conn = Connection(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        trunk_id=trunk.id,
        switch_id=switch.id,
        name=f"eth-{peer_asn}",
        type=ConnectionType.physical,
        state=ConnectionState.active,
        speed=10000,
    )
    db.add(conn)
    await db.flush()

    network = "192.0.2.0/24" if af == 4 else "2001:db8::/64"
    pool = IPPool(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        vlan_id=vlan.id,
        network=network,
        af=af,
    )
    db.add(pool)
    await db.flush()

    ip = IPAssignment(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        pool_id=pool.id,
        trunk_vlan_id=trunk_vlan.id,
        address=peer_ip,
    )
    db.add(ip)
    await db.flush()

    bgp = BGPSession(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        route_server_id=rs.id,
        trunk_vlan_id=trunk_vlan.id,
        admin_state=BGPAdminState.up,
        oper_state=BGPOperState.up,
        af=af,
        max_prefixes=100,
    )
    db.add(bgp)
    await db.flush()
    return member, trunk, bgp


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------


class TestCombinedConfigValidity:
    """El config combinado v4+v6 debe ser cargable por un solo daemon BIRD 2.x.

    BIRD rechaza definiciones duplicadas de protocol device y de funciones,
    asi que la seccion global debe aparecer exactamente una vez
    """

    async def test_dual_stack_config_has_no_duplicate_globals(
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
        content = resp.json()["content"]

        assert content.count("protocol device") == 1
        assert content.count("protocol direct") == 1
        assert content.count("router id ") == 1
        assert content.count("function net_len_valid") == 1
        assert content.count("function honor_graceful_shutdown") == 1
        assert content.count("log syslog all;") == 1
        # Lo especifico de cada familia si va una vez por AF
        assert content.count("protocol kernel") == 2
        assert content.count("function is_bogon_v4") == 1
        assert content.count("function is_bogon_v6") == 1

    async def test_v6_only_config_includes_globals(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        # Los ultimos 4 bytes derivan el router id, deben formar una IPv4 valida
        rs = await _setup_route_server(
            db_session, ixp, ip_v4=None, ip_v6="2001:db8::4501:203", name="rs-v6only",
        )

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/config/generate",
            headers=auth_headers,
        )
        assert resp.status_code == 201
        content = resp.json()["content"]

        assert content.count("protocol device") == 1
        assert content.count("router id ") == 1
        assert content.count("function net_len_valid") == 1


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

        # Create a suspended member with a BGP session via active trunk
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

        trunk = Trunk(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            name="ae-susp",
            state=TrunkState.active,
        )
        db_session.add(trunk)
        await db_session.flush()

        vlan = VLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="VLAN-susp",
            vid=700,
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

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="192.0.2.0/24",
            af=4,
        )
        db_session.add(pool)
        await db_session.flush()

        ip = IPAssignment(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            pool_id=pool.id,
            trunk_vlan_id=trunk_vlan.id,
            address="192.0.2.99",
        )
        db_session.add(ip)
        await db_session.flush()

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

        trunk = Trunk(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            name="ae-adn",
            state=TrunkState.active,
        )
        db_session.add(trunk)
        await db_session.flush()

        vlan = VLAN(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            name="VLAN-adn",
            vid=800,
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

        pool = IPPool(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            vlan_id=vlan.id,
            network="192.0.2.0/24",
            af=4,
        )
        db_session.add(pool)
        await db_session.flush()

        ip = IPAssignment(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            pool_id=pool.id,
            trunk_vlan_id=trunk_vlan.id,
            address="192.0.2.88",
        )
        db_session.add(ip)
        await db_session.flush()

        bgp = BGPSession(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            route_server_id=rs.id,
            trunk_vlan_id=trunk_vlan.id,
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

    async def test_generate_idempotent_same_input(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Consecutive generations with same input should succeed"""
        rs = await _setup_route_server(db_session, ixp)
        await _setup_active_peer(db_session, ixp, rs)

        resp1 = await client.post(
            f"/api/v1/route-servers/{rs.id}/config/generate",
            headers=auth_headers,
        )
        resp2 = await client.post(
            f"/api/v1/route-servers/{rs.id}/config/generate",
            headers=auth_headers,
        )
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

    async def test_get_config_version_by_id_returns_content(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs = await _setup_route_server(db_session, ixp)
        gen = await client.post(
            f"/api/v1/route-servers/{rs.id}/config/generate", headers=auth_headers
        )
        version_id = gen.json()["id"]

        resp = await client.get(
            f"/api/v1/route-servers/{rs.id}/config/{version_id}", headers=auth_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == version_id
        assert body["content"]

    async def test_get_config_version_wrong_rs_is_404(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        rs1 = await _setup_route_server(db_session, ixp, name="rs1-cfg")
        rs2 = await _setup_route_server(
            db_session, ixp, name="rs2-cfg", ip_v4="192.0.2.211", ip_v6="2001:db8::211"
        )
        gen = await client.post(
            f"/api/v1/route-servers/{rs1.id}/config/generate", headers=auth_headers
        )
        version_id = gen.json()["id"]

        resp = await client.get(
            f"/api/v1/route-servers/{rs2.id}/config/{version_id}", headers=auth_headers
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

    async def test_diff_without_from_uses_previous_version(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Sin ?from, diffea contra la version inmediatamente anterior del RS.

        Es lo que necesita el boton 'Ver Diff' del portal, que solo pasa ?to
        """
        rs = await _setup_route_server(db_session, ixp)
        await client.post(f"/api/v1/route-servers/{rs.id}/config/generate", headers=auth_headers)
        await _setup_active_peer(db_session, ixp, rs, peer_ip="192.0.2.21", peer_asn=64901)
        resp2 = await client.post(
            f"/api/v1/route-servers/{rs.id}/config/generate", headers=auth_headers
        )
        version2_id = resp2.json()["id"]

        resp = await client.get(
            f"/api/v1/route-servers/{rs.id}/config/diff",
            headers=auth_headers,
            params={"to": version2_id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "192.0.2.21" in body["diff"]
        assert body["current_hash"] is not None

    async def test_diff_without_from_on_first_version(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """Sin ?from y sin version anterior, diffea contra vacio (no revienta)."""
        rs = await _setup_route_server(db_session, ixp)
        resp1 = await client.post(
            f"/api/v1/route-servers/{rs.id}/config/generate", headers=auth_headers
        )
        version1_id = resp1.json()["id"]

        resp = await client.get(
            f"/api/v1/route-servers/{rs.id}/config/diff",
            headers=auth_headers,
            params={"to": version1_id},
        )
        assert resp.status_code == 200
        assert resp.json()["current_hash"] is None

    async def test_diff_rejects_versions_from_other_route_server(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        """GET /route-servers/{rs_id}/config/diff returns 404 when version IDs belong to another RS."""
        rs1 = await _setup_route_server(db_session, ixp, name="rs1")
        rs2 = await _setup_route_server(
            db_session, ixp, name="rs2", ip_v4="192.0.2.251"
        )

        # Generate configs on rs1
        resp1 = await client.post(
            f"/api/v1/route-servers/{rs1.id}/config/generate",
            headers=auth_headers,
        )
        assert resp1.status_code == 201
        v1_id = resp1.json()["id"]

        resp2 = await client.post(
            f"/api/v1/route-servers/{rs1.id}/config/generate",
            headers=auth_headers,
        )
        assert resp2.status_code == 201
        v2_id = resp2.json()["id"]

        # Try to diff rs1 versions via rs2 endpoint -- should be 404
        resp = await client.get(
            f"/api/v1/route-servers/{rs2.id}/config/diff",
            headers=auth_headers,
            params={"from": v1_id, "to": v2_id},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Helpers con LAN de peering compartida
#
# _setup_active_peer, mas arriba, crea UNA VLAN POR MIEMBRO. Sirve para los
# tests que ya estaban, pero no reproduce el caso que importa para el patron
# euro-ix: varios miembros en la misma VLAN, que es de donde sale allips
# ---------------------------------------------------------------------------

PEERING_VLAN_VID = 64


async def _get_or_create_peering_lan(
    db: AsyncSession, ixp: IXP
) -> tuple[VLAN, IPPool, IPPool]:
    """Una unica LAN de peering compartida por todos los miembros del IXP

    Idempotente: el primer miembro la crea y los siguientes la reusan, asi cada
    test la pide sin coordinarse con los demas
    """
    existing = (
        await db.execute(
            select(VLAN).where(VLAN.ixp_id == ixp.id, VLAN.vid == PEERING_VLAN_VID)
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = VLAN(
            ixp_id=ixp.id,
            name="Peering LAN",
            vid=PEERING_VLAN_VID,
            type=VLANType.production,
        )
        db.add(existing)
        await db.flush()
        db.add_all(
            [
                IPPool(
                    ixp_id=ixp.id,
                    vlan_id=existing.id,
                    network="192.0.2.0/24",
                    af=4,
                ),
                IPPool(
                    ixp_id=ixp.id,
                    vlan_id=existing.id,
                    network="2001:db8::/64",
                    af=6,
                ),
            ]
        )
        await db.flush()

    pools = (
        (
            await db.execute(
                select(IPPool)
                .where(IPPool.vlan_id == existing.id)
                .order_by(IPPool.af)
            )
        )
        .scalars()
        .all()
    )
    return existing, pools[0], pools[1]


async def _attach_trunk(
    db: AsyncSession,
    ixp: IXP,
    rs: RouteServer,
    member: Member,
    vlan: VLAN,
    pool_v4: IPPool,
    pool_v6: IPPool,
    *,
    trunk_name: str,
    ipv4: str | None,
    ipv6: str | None,
    max_prefixes: int | None = None,
) -> TrunkVLAN:
    """Trunk activo con su conexion, IPs y sesiones BGP en la VLAN dada"""
    location = Location(
        ixp_id=ixp.id, name=f"DC-{trunk_name}", city="Test", country="US"
    )
    db.add(location)
    await db.flush()

    switch = Switch(ixp_id=ixp.id, name=f"sw-{trunk_name}", location_id=location.id)
    db.add(switch)
    await db.flush()

    trunk = Trunk(
        ixp_id=ixp.id, member_id=member.id, name=trunk_name, state=TrunkState.active
    )
    db.add(trunk)
    await db.flush()

    db.add(
        Connection(
            ixp_id=ixp.id,
            trunk_id=trunk.id,
            switch_id=switch.id,
            name=f"eth-{trunk_name}",
            type=ConnectionType.physical,
            state=ConnectionState.active,
            speed=10000,
        )
    )

    trunk_vlan = TrunkVLAN(ixp_id=ixp.id, trunk_id=trunk.id, vlan_id=vlan.id)
    db.add(trunk_vlan)
    await db.flush()

    for address, pool, af in ((ipv4, pool_v4, 4), (ipv6, pool_v6, 6)):
        if address is None:
            continue
        db.add(
            IPAssignment(
                ixp_id=ixp.id,
                pool_id=pool.id,
                trunk_vlan_id=trunk_vlan.id,
                address=address,
            )
        )
        db.add(
            BGPSession(
                ixp_id=ixp.id,
                route_server_id=rs.id,
                trunk_vlan_id=trunk_vlan.id,
                af=af,
                admin_state=BGPAdminState.up,
                max_prefixes=max_prefixes,
            )
        )
    await db.flush()
    return trunk_vlan


async def _setup_member_peer(
    db: AsyncSession,
    ixp: IXP,
    rs: RouteServer,
    *,
    asn: int,
    ipv4: str | None = None,
    ipv6: str | None = None,
    short_name: str | None = None,
    member_type: MemberType | None = None,
    max_prefixes: int | None = None,
) -> Member:
    """Miembro activo con trunk, conexion, IPs y sesiones BGP en la LAN compartida

    Devuelve el Member para que el test le pueda colgar un MemberPrefixFilter
    """
    vlan, pool_v4, pool_v6 = await _get_or_create_peering_lan(db, ixp)

    member = Member(
        ixp_id=ixp.id,
        name=f"Miembro AS{asn}",
        short_name=short_name or f"AS{asn}",
        asn=asn,
        state=MemberState.active,
        peering_policy=PeeringPolicy.open,
        member_type=member_type,
    )
    db.add(member)
    await db.flush()

    await _attach_trunk(
        db,
        ixp,
        rs,
        member,
        vlan,
        pool_v4,
        pool_v6,
        trunk_name=f"ae-{asn}",
        ipv4=ipv4,
        ipv6=ipv6,
        max_prefixes=max_prefixes,
    )
    return member


async def _add_second_connection(
    db: AsyncSession, ixp: IXP, rs: RouteServer, member: Member, *, ipv4: str
) -> None:
    """Segundo trunk del mismo miembro en la misma VLAN, con su propia IP

    Reproduce a un miembro con dos puertos: las dos IPs son legitimas y las dos
    tienen que entrar en allips, o el chequeo de next hop marca como hijack su
    propio segundo puerto
    """
    vlan, pool_v4, pool_v6 = await _get_or_create_peering_lan(db, ixp)
    await _attach_trunk(
        db,
        ixp,
        rs,
        member,
        vlan,
        pool_v4,
        pool_v6,
        trunk_name=f"ae-{member.asn}-2",
        ipv4=ipv4,
        ipv6=None,
    )

# ---------------------------------------------------------------------------
# Presupuesto de nombres de simbolos BIRD
# ---------------------------------------------------------------------------


def test_peer_slug_truncates_to_55():
    from ixforge.services.config_generation import PEER_SLUG_MAX_LEN, _build_peer_slug

    slug = _build_peer_slug("A" * 200, "192.0.2.1", 4)

    assert len(slug) == PEER_SLUG_MAX_LEN == 55


def test_derived_symbols_fit_in_bird_limit():
    """f_import_ es el prefijo mas largo del patron euro-ix: 9 caracteres"""
    from ixforge.services.config_generation import _build_peer_slug

    slug = _build_peer_slug("A" * 200, "192.0.2.1", 4)

    for prefix in ("t_", "pb_", "pp_", "f_import_", "f_export_"):
        assert len(prefix + slug) <= 64


def test_peer_slug_sanitizes_and_keeps_af():
    from ixforge.services.config_generation import _build_peer_slug

    slug_v4 = _build_peer_slug("Rio Negro S.A.", "192.0.2.1", 4)
    slug_v6 = _build_peer_slug("Rio Negro S.A.", "2001:db8::1", 6)

    assert slug_v4 == "Rio_Negro_S_A__192_0_2_1_v4"
    assert slug_v6 != slug_v4
    assert all(c.isalnum() or c == "_" for c in slug_v4)


def test_long_name_does_not_eat_the_distinguishing_part():
    """Truncar el string completo borra la IP y la familia, que es lo unico
    que distingue dos sesiones del mismo miembro
    """
    from ixforge.services.config_generation import _build_peer_slug

    largo = "A" * 200
    v4 = _build_peer_slug(largo, "192.0.2.5", 4)
    v6 = _build_peer_slug(largo, "2001:db8::5", 6)
    otra_ip = _build_peer_slug(largo, "192.0.2.6", 4)

    assert v4 != v6
    assert v4 != otra_ip
    assert v4.endswith("_192_0_2_5_v4")
    assert v6.endswith("_2001_db8__5_v6")


def test_deduplicate_slugs_works_across_families():
    """BIRD tiene un namespace de simbolos por daemon, no uno por familia"""
    from dataclasses import dataclass

    from ixforge.services.config_generation import _deduplicate_slugs

    # frozen igual que los contextos reales: por eso la funcion usa
    # dataclasses.replace en vez de asignar el atributo
    @dataclass(frozen=True)
    class _Ctx:
        slug: str

    grupos = _deduplicate_slugs([[_Ctx("dup")], [_Ctx("dup")]])
    slugs = [c.slug for grupo in grupos for c in grupo]

    assert len(set(slugs)) == 2


# ---------------------------------------------------------------------------
# Contexto extendido de peers de miembros
# ---------------------------------------------------------------------------


async def test_peer_context_defaults_origin_to_member_asn(db_session, ixp):
    """Un miembro sin fila en member_prefix_filters filtra por su propio ASN"""
    from ixforge.services.config_generation import build_peers

    rs = await _setup_route_server(db_session, ixp)
    await _setup_member_peer(db_session, ixp, rs, asn=61455, ipv4="192.0.2.16")

    peers = await build_peers(db_session, rs.id, af=4)

    # los campos del contexto son tuplas: comparar contra una lista da False
    assert len(peers) == 1
    assert peers[0].origin_asns == (61455,)
    assert peers[0].prefixes is None


async def test_peer_context_uses_prefix_filter(db_session, ixp):
    from ixforge.services.config_generation import build_peers

    rs = await _setup_route_server(db_session, ixp)
    member = await _setup_member_peer(db_session, ixp, rs, asn=273973, ipv4="192.0.2.11")
    db_session.add(
        MemberPrefixFilter(
            ixp_id=ixp.id,
            member_id=member.id,
            af=4,
            origin_asns=[273973, 64512],
            prefixes=["45.170.100.0/24", "45.238.179.0/24"],
        )
    )
    await db_session.flush()

    peers = await build_peers(db_session, rs.id, af=4)

    assert peers[0].origin_asns == (273973, 64512)
    assert peers[0].prefixes == ("45.170.100.0/24", "45.238.179.0/24")


async def test_peer_context_prefix_filter_is_per_af(db_session, ixp):
    """El filtro v6 no se le puede aplicar a la sesion v4"""
    from ixforge.services.config_generation import build_peers

    rs = await _setup_route_server(db_session, ixp)
    member = await _setup_member_peer(
        db_session, ixp, rs, asn=273973, ipv4="192.0.2.11", ipv6="2001:db8::11"
    )
    db_session.add(
        MemberPrefixFilter(
            ixp_id=ixp.id, member_id=member.id, af=6, prefixes=["2001:db8:aa::/48"]
        )
    )
    await db_session.flush()

    peers_v4 = await build_peers(db_session, rs.id, af=4)
    peers_v6 = await build_peers(db_session, rs.id, af=6)

    assert peers_v4[0].prefixes is None
    assert peers_v6[0].prefixes == ("2001:db8:aa::/48",)


async def test_empty_prefix_list_is_not_the_same_as_null(db_session, ixp):
    """NULL desactiva el filtro, la lista vacia no autoriza ningun prefijo

    Colapsarlos seria fail-open: el operador que vacia la lista esperando
    cerrar el filtro terminaria abriendolo del todo
    """
    from ixforge.services.config_generation import build_peers

    rs = await _setup_route_server(db_session, ixp)
    member = await _setup_member_peer(db_session, ixp, rs, asn=273973, ipv4="192.0.2.11")
    db_session.add(
        MemberPrefixFilter(ixp_id=ixp.id, member_id=member.id, af=4, prefixes=[])
    )
    await db_session.flush()

    peers = await build_peers(db_session, rs.id, af=4)

    assert peers[0].prefixes == ()
    assert peers[0].prefixes is not None


async def test_empty_origin_asns_falls_back_to_member_asn(db_session, ixp):
    """Al reves que prefixes: aca el lado seguro es restringir al ASN propio,
    porque un allas vacio marcaria todas las rutas del miembro como filtradas
    """
    from ixforge.services.config_generation import build_peers

    rs = await _setup_route_server(db_session, ixp)
    member = await _setup_member_peer(db_session, ixp, rs, asn=273973, ipv4="192.0.2.11")
    db_session.add(
        MemberPrefixFilter(ixp_id=ixp.id, member_id=member.id, af=4, origin_asns=[])
    )
    await db_session.flush()

    peers = await build_peers(db_session, rs.id, af=4)

    assert peers[0].origin_asns == (273973,)


async def test_all_peer_ips_covers_every_connection_of_the_member(db_session, ixp):
    """allips tiene que traer todas las IPs del miembro en la VLAN, no solo la de
    la sesion, o el chequeo de next hop marca como hijack su propio segundo puerto
    """
    from ixforge.services.config_generation import build_peers

    rs = await _setup_route_server(db_session, ixp)
    member = await _setup_member_peer(db_session, ixp, rs, asn=273973, ipv4="192.0.2.11")
    await _add_second_connection(db_session, ixp, rs, member, ipv4="192.0.2.12")

    peers = await build_peers(db_session, rs.id, af=4)

    for peer in peers:
        assert set(peer.all_peer_ips) == {"192.0.2.11", "192.0.2.12"}


async def test_peer_context_carries_member_type_community(db_session, ixp):
    from ixforge.services.config_generation import build_peers

    rs = await _setup_route_server(db_session, ixp)
    await _setup_member_peer(
        db_session,
        ixp,
        rs,
        asn=25152,
        ipv4="192.0.2.10",
        member_type=MemberType.infraestructura_critica,
    )

    peers = await build_peers(db_session, rs.id, af=4)

    assert peers[0].member_type_community == 270


async def test_generated_config_names_every_protocol(db_session, ixp):
    """Un atributo que no existe en el contexto se renderea vacio y produce
    'protocol bgp  {', que BIRD rechaza. Ningun test lo cubria
    """
    from ixforge.services.config_generation import build_peers, generate_config

    rs = await _setup_route_server(db_session, ixp)
    await _setup_member_peer(db_session, ixp, rs, asn=273973, ipv4="192.0.2.11")
    cv = await generate_config(db_session, rs.id, ixp.id)

    slug = (await build_peers(db_session, rs.id, af=4))[0].slug
    assert slug
    assert f"protocol bgp {slug} " in cv.content
    assert "protocol bgp  " not in cv.content
