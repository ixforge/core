"""Tests for Agent communication endpoints: config polling, status, heartbeat, config applied."""

import hashlib
import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from prometheus_client import REGISTRY
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import (
    BGPAdminState,
    BGPOperState,
    ConnectionState,
    ConnectionType,
    MemberState,
    PeeringPolicy,
    PrefixEventType,
    TrunkState,
    VLANType,
)
from ixforge.models.api_key import APIKey
from ixforge.models.bgp_prefix import BGPPrefixEvent, BGPSessionPrefix
from ixforge.models.bgp_session import BGPSession
from ixforge.models.config import ConfigVersion
from ixforge.models.connection import Connection
from ixforge.models.ip import IPAssignment, IPPool
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


async def _setup_agent_key(db: AsyncSession, rs: RouteServer) -> str:
    """Create an agent API key scoped to the given route server. Returns raw key"""
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


async def _setup_sesion_bgp(
    db: AsyncSession,
    ixp: IXP,
    rs: RouteServer,
    *,
    asn: int,
    address: str,
    af: int = 4,
    network: str = "192.0.2.0/24",
    vid: int = 300,
    oper_state: BGPOperState = BGPOperState.up,
    prefixes_imported: int | None = None,
    prefixes_exported: int | None = None,
) -> BGPSession:
    """Arma la cadena miembro -> trunk -> vlan -> ip -> sesion de una sola vez

    El endpoint de status matchea por (peer_ip, af) resolviendo la IP del
    trunk_vlan, asi que no hay atajo: la sesion sin la cadena completa no es
    alcanzable
    """
    sufijo = uuid.uuid4().hex[:8]

    member = Member(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name=f"Net {sufijo}",
        short_name=sufijo[:6].upper(),
        asn=asn,
        state=MemberState.active,
        peering_policy=PeeringPolicy.open,
    )
    location = Location(
        id=uuid.uuid4(), ixp_id=ixp.id, name=f"DC-{sufijo}", city="Test", country="CL",
    )
    db.add_all([member, location])
    await db.flush()

    switch = Switch(id=uuid.uuid4(), ixp_id=ixp.id, name=f"sw-{sufijo}", location_id=location.id)
    trunk = Trunk(
        id=uuid.uuid4(), ixp_id=ixp.id, member_id=member.id,
        name="ae0", state=TrunkState.active,
    )
    vlan = VLAN(
        id=uuid.uuid4(), ixp_id=ixp.id, name=f"Peering {sufijo}",
        vid=vid, type=VLANType.production,
    )
    db.add_all([switch, trunk, vlan])
    await db.flush()

    trunk_vlan = TrunkVLAN(id=uuid.uuid4(), ixp_id=ixp.id, trunk_id=trunk.id, vlan_id=vlan.id)
    conn = Connection(
        id=uuid.uuid4(), ixp_id=ixp.id, trunk_id=trunk.id, switch_id=switch.id,
        name=f"eth-{sufijo}", type=ConnectionType.physical,
        state=ConnectionState.active, speed=10000,
    )
    pool = IPPool(id=uuid.uuid4(), ixp_id=ixp.id, vlan_id=vlan.id, network=network, af=af)
    db.add_all([trunk_vlan, conn, pool])
    await db.flush()

    db.add(IPAssignment(
        id=uuid.uuid4(), ixp_id=ixp.id, pool_id=pool.id,
        trunk_vlan_id=trunk_vlan.id, address=address,
    ))
    bgp = BGPSession(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        route_server_id=rs.id,
        trunk_vlan_id=trunk_vlan.id,
        admin_state=BGPAdminState.up,
        oper_state=oper_state,
        af=af,
        max_prefixes=100,
        prefixes_imported=prefixes_imported,
        prefixes_exported=prefixes_exported,
    )
    db.add(bgp)
    await db.flush()
    return bgp


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
        raw_key = await _setup_agent_key(db_session, rs)
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
        raw_key = await _setup_agent_key(db_session, rs1)

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
        raw_key = await _setup_agent_key(db_session, rs)

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
        raw_key = await _setup_agent_key(db_session, rs)

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

        pool = IPPool(
            id=uuid.uuid4(), ixp_id=ixp.id, vlan_id=vlan.id,
            network="192.0.2.0/24", af=4,
        )
        db_session.add(pool)
        await db_session.flush()

        ip = IPAssignment(
            id=uuid.uuid4(), ixp_id=ixp.id, pool_id=pool.id,
            trunk_vlan_id=trunk_vlan.id, address="192.0.2.10",
        )
        db_session.add(ip)
        await db_session.flush()

        bgp = BGPSession(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            route_server_id=rs.id,
            trunk_vlan_id=trunk_vlan.id,
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
        raw_key = await _setup_agent_key(db_session, rs)

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
        raw_key = await _setup_agent_key(db_session, rs)

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

        pool = IPPool(
            id=uuid.uuid4(), ixp_id=ixp.id, vlan_id=vlan.id,
            network="192.0.2.0/24", af=4,
        )
        db_session.add(pool)
        await db_session.flush()

        ip = IPAssignment(
            id=uuid.uuid4(), ixp_id=ixp.id, pool_id=pool.id,
            trunk_vlan_id=trunk_vlan.id, address="192.0.2.20",
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


class TestConteoDePrefijos:
    """El agente reporta cuantas rutas importo y exporto cada sesion"""

    async def test_el_conteo_se_guarda(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)
        bgp = await _setup_sesion_bgp(
            db_session, ixp, rs, asn=64570, address="192.0.2.30", vid=301,
            oper_state=BGPOperState.down,
        )

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/status",
            headers={"X-API-Key": raw_key},
            json={
                "sessions": [
                    {
                        "peer_ip": "192.0.2.30",
                        "oper_state": "up",
                        "af": 4,
                        "prefixes_imported": 1420,
                        "prefixes_exported": 73,
                    },
                ]
            },
        )

        assert resp.status_code == 200
        await db_session.refresh(bgp)
        assert bgp.prefixes_imported == 1420
        assert bgp.prefixes_exported == 73

    async def test_el_conteo_se_actualiza_aunque_el_estado_no_cambie(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        """El caso normal y el que se rompe solo: la sesion lleva dias arriba y
        lo unico que se mueve es el conteo. Si el endpoint corta temprano por
        'estado sin cambios' el numero se queda congelado para siempre
        """
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)
        bgp = await _setup_sesion_bgp(
            db_session, ixp, rs, asn=64571, address="192.0.2.31", vid=302,
            oper_state=BGPOperState.up, prefixes_imported=1000, prefixes_exported=50,
        )

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/status",
            headers={"X-API-Key": raw_key},
            json={
                "sessions": [
                    {
                        "peer_ip": "192.0.2.31",
                        "oper_state": "up",
                        "af": 4,
                        "prefixes_imported": 1337,
                        "prefixes_exported": 51,
                    },
                ]
            },
        )

        assert resp.status_code == 200
        assert resp.json()["unchanged"] == 1
        await db_session.refresh(bgp)
        assert bgp.prefixes_imported == 1337
        assert bgp.prefixes_exported == 51

    async def test_la_sesion_caida_deja_el_conteo_en_null(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        """Una sesion caida no tiene conteo, y el ultimo conocido es basura: si
        se conserva, el sitio muestra 1420 prefijos de un peer que no esta
        """
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)
        bgp = await _setup_sesion_bgp(
            db_session, ixp, rs, asn=64572, address="192.0.2.32", vid=303,
            oper_state=BGPOperState.up, prefixes_imported=1420, prefixes_exported=73,
        )

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/status",
            headers={"X-API-Key": raw_key},
            json={
                "sessions": [
                    {"peer_ip": "192.0.2.32", "oper_state": "down", "af": 4},
                ]
            },
        )

        assert resp.status_code == 200
        await db_session.refresh(bgp)
        assert bgp.prefixes_imported is None
        assert bgp.prefixes_exported is None

    async def test_el_conteo_negativo_se_rechaza(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/status",
            headers={"X-API-Key": raw_key},
            json={
                "sessions": [
                    {
                        "peer_ip": "192.0.2.33",
                        "oper_state": "up",
                        "af": 4,
                        "prefixes_imported": -1,
                    },
                ]
            },
        )

        assert resp.status_code == 422

    async def test_el_conteo_ausente_no_rompe_al_agente_viejo(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        """Durante el despliegue un route server corre el agente nuevo y el otro
        el viejo, que no manda los campos. El reporte sin conteo sigue siendo valido
        """
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)
        bgp = await _setup_sesion_bgp(
            db_session, ixp, rs, asn=64573, address="192.0.2.34", vid=304,
            oper_state=BGPOperState.down,
        )

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/status",
            headers={"X-API-Key": raw_key},
            json={
                "sessions": [
                    {"peer_ip": "192.0.2.34", "oper_state": "up", "af": 4},
                ]
            },
        )

        assert resp.status_code == 200
        assert resp.json()["updated"] == 1
        await db_session.refresh(bgp)
        assert bgp.oper_state == BGPOperState.up


    async def test_el_conteo_queda_expuesto_como_metrica(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        """Sin la metrica el conteo solo existe como valor actual y el grafico
        historico no tiene de donde salir
        """
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)
        await _setup_sesion_bgp(
            db_session, ixp, rs, asn=64580, address="192.0.2.40", vid=310,
            oper_state=BGPOperState.down,
        )

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/status",
            headers={"X-API-Key": raw_key},
            json={
                "sessions": [
                    {
                        "peer_ip": "192.0.2.40",
                        "oper_state": "up",
                        "af": 4,
                        "prefixes_imported": 1420,
                        "prefixes_exported": 73,
                    },
                ]
            },
        )

        assert resp.status_code == 200
        etiquetas = {"route_server_id": str(rs.id), "peer_asn": "64580", "af": "4"}
        assert REGISTRY.get_sample_value(
            "ixforge_bgp_session_prefixes_imported", etiquetas
        ) == 1420
        assert REGISTRY.get_sample_value(
            "ixforge_bgp_session_prefixes_exported", etiquetas
        ) == 73

    async def test_la_sesion_sin_conteo_borra_la_serie(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        """La serie se borra en vez de quedar en el ultimo valor o en cero: en
        el grafico tiene que quedar un hueco, que es lo que de verdad pasa.
        Un gauge que se queda pegado sigue reportando 1420 prefijos de un peer
        que ya no esta
        """
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)
        await _setup_sesion_bgp(
            db_session, ixp, rs, asn=64581, address="192.0.2.41", vid=311,
            oper_state=BGPOperState.down,
        )
        etiquetas = {"route_server_id": str(rs.id), "peer_asn": "64581", "af": "4"}

        async def reportar(cuerpo: dict[str, object]) -> None:
            r = await client.post(
                f"/api/v1/route-servers/{rs.id}/agent/status",
                headers={"X-API-Key": raw_key},
                json={"sessions": [cuerpo]},
            )
            assert r.status_code == 200

        await reportar({
            "peer_ip": "192.0.2.41", "oper_state": "up", "af": 4,
            "prefixes_imported": 900, "prefixes_exported": 12,
        })
        assert REGISTRY.get_sample_value(
            "ixforge_bgp_session_prefixes_imported", etiquetas
        ) == 900

        await reportar({"peer_ip": "192.0.2.41", "oper_state": "down", "af": 4})

        assert REGISTRY.get_sample_value(
            "ixforge_bgp_session_prefixes_imported", etiquetas
        ) is None
        assert REGISTRY.get_sample_value(
            "ixforge_bgp_session_prefixes_exported", etiquetas
        ) is None


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
        raw_key = await _setup_agent_key(db_session, rs)
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
        raw_key = await _setup_agent_key(db_session, rs)
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
        raw_key = await _setup_agent_key(db_session, rs)
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
        raw_key = await _setup_agent_key(db_session, rs)
        cv = await _setup_config_version(db_session, rs)
        assert cv.applied_at is None

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/config/applied",
            headers={"X-API-Key": raw_key},
            json={"config_hash": cv.config_hash},
        )
        assert resp.status_code == 204

        await db_session.refresh(cv)
        assert cv.applied_at is not None

    async def test_confirm_nonexistent_config_hash(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/config/applied",
            headers={"X-API-Key": raw_key},
            json={"config_hash": "b" * 64},
        )
        assert resp.status_code == 404

    async def test_report_config_failed(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)
        cv = await _setup_config_version(db_session, rs)

        resp = await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/config/failed",
            headers={"X-API-Key": raw_key},
            json={"config_hash": cv.config_hash, "error": "bird -p failed: line 74 syntax error"},
        )
        assert resp.status_code == 204

        await db_session.refresh(cv)
        assert cv.apply_error == "bird -p failed: line 74 syntax error"
        assert cv.apply_error_at is not None
        assert cv.applied_at is None

    async def test_applied_clears_previous_error(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        """Cuando el agente confirma que aplico, se limpia el error previo."""
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)
        cv = await _setup_config_version(db_session, rs)

        await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/config/failed",
            headers={"X-API-Key": raw_key},
            json={"config_hash": cv.config_hash, "error": "boom"},
        )
        await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/config/applied",
            headers={"X-API-Key": raw_key},
            json={"config_hash": cv.config_hash},
        )

        await db_session.refresh(cv)
        assert cv.applied_at is not None
        assert cv.apply_error is None

    async def test_report_config_failed_wrong_rs_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ixp: IXP,
        admin_user: User,
    ):
        rs1 = await _setup_route_server(db_session, ixp)
        raw_key1 = await _setup_agent_key(db_session, rs1)
        rs2 = RouteServer(
            id=uuid.uuid4(), ixp_id=ixp.id, name="rs2-fail", ip_v4="192.0.2.61", is_active=True
        )
        db_session.add(rs2)
        await db_session.flush()
        cv2 = await _setup_config_version(db_session, rs2)

        resp = await client.post(
            f"/api/v1/route-servers/{rs2.id}/agent/config/failed",
            headers={"X-API-Key": raw_key1},
            json={"config_hash": cv2.config_hash, "error": "boom"},
        )
        assert resp.status_code == 403


class TestReporteDePrefijos:
    """El agente lista que prefijos anuncia cada peer, no solo cuantos"""

    async def _sesion(self, db_session, ixp, rs, asn, address, vid):
        return await _setup_sesion_bgp(
            db_session, ixp, rs, asn=asn, address=address, vid=vid,
            oper_state=BGPOperState.up, prefixes_imported=2,
        )

    async def _reportar(self, client, rs, raw_key, peer_ip, prefijos, af=4):
        return await client.post(
            f"/api/v1/route-servers/{rs.id}/agent/prefixes",
            headers={"X-API-Key": raw_key},
            json={"sessions": [{"peer_ip": peer_ip, "af": af, "prefixes": prefijos}]},
        )

    async def test_guarda_los_prefijos_reportados(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP, admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)
        sesion = await self._sesion(db_session, ixp, rs, 64600, "192.0.2.50", 320)

        resp = await self._reportar(client, rs, raw_key, "192.0.2.50", [
            {"prefix": "45.238.179.0/24", "as_path": [64600]},
            {"prefix": "45.170.100.0/24", "as_path": [64500, 64600]},
        ])

        assert resp.status_code == 200
        assert resp.json()["prefixes_added"] == 2

        filas = (await db_session.execute(
            select(BGPSessionPrefix).where(BGPSessionPrefix.bgp_session_id == sesion.id)
        )).scalars().all()
        assert {f.prefix for f in filas} == {"45.238.179.0/24", "45.170.100.0/24"}
        assert next(f.as_path for f in filas if f.prefix == "45.170.100.0/24") == [64500, 64600]

    async def test_el_prefijo_nuevo_deja_un_evento_de_anuncio(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP, admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)
        sesion = await self._sesion(db_session, ixp, rs, 64601, "192.0.2.51", 321)

        await self._reportar(client, rs, raw_key, "192.0.2.51", [
            {"prefix": "45.238.179.0/24", "as_path": [64601]},
        ])

        eventos = (await db_session.execute(
            select(BGPPrefixEvent).where(BGPPrefixEvent.bgp_session_id == sesion.id)
        )).scalars().all()
        assert len(eventos) == 1
        assert eventos[0].event_type == PrefixEventType.announced
        assert eventos[0].prefix == "45.238.179.0/24"

    async def test_el_prefijo_que_desaparece_se_retira(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP, admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)
        sesion = await self._sesion(db_session, ixp, rs, 64602, "192.0.2.52", 322)

        await self._reportar(client, rs, raw_key, "192.0.2.52", [
            {"prefix": "45.238.179.0/24", "as_path": [64602]},
            {"prefix": "45.170.100.0/24", "as_path": [64602]},
        ])
        resp = await self._reportar(client, rs, raw_key, "192.0.2.52", [
            {"prefix": "45.238.179.0/24", "as_path": [64602]},
        ])

        assert resp.json()["prefixes_removed"] == 1
        filas = (await db_session.execute(
            select(BGPSessionPrefix).where(BGPSessionPrefix.bgp_session_id == sesion.id)
        )).scalars().all()
        assert {f.prefix for f in filas} == {"45.238.179.0/24"}

        retiros = (await db_session.execute(
            select(BGPPrefixEvent).where(
                BGPPrefixEvent.bgp_session_id == sesion.id,
                BGPPrefixEvent.event_type == PrefixEventType.withdrawn,
            )
        )).scalars().all()
        assert [e.prefix for e in retiros] == ["45.170.100.0/24"]

    async def test_el_as_path_que_cambia_deja_un_evento_de_actualizacion(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP, admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)
        sesion = await self._sesion(db_session, ixp, rs, 64603, "192.0.2.53", 323)

        await self._reportar(client, rs, raw_key, "192.0.2.53", [
            {"prefix": "45.238.179.0/24", "as_path": [64603]},
        ])
        await self._reportar(client, rs, raw_key, "192.0.2.53", [
            {"prefix": "45.238.179.0/24", "as_path": [64500, 64603]},
        ])

        eventos = (await db_session.execute(
            select(BGPPrefixEvent)
            .where(BGPPrefixEvent.bgp_session_id == sesion.id)
            .order_by(BGPPrefixEvent.occurred_at)
        )).scalars().all()
        assert [e.event_type for e in eventos] == [
            PrefixEventType.announced, PrefixEventType.updated,
        ]
        assert eventos[1].as_path == [64500, 64603]

    async def test_el_prefijo_sin_cambios_no_deja_evento(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP, admin_user: User,
    ):
        """Si cada reporte dejara un evento, el historial seria una lista de
        'sigue ahi' cada 5 minutos y no se veria ningun cambio real
        """
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)
        sesion = await self._sesion(db_session, ixp, rs, 64604, "192.0.2.54", 324)

        for _ in range(3):
            await self._reportar(client, rs, raw_key, "192.0.2.54", [
                {"prefix": "45.238.179.0/24", "as_path": [64604]},
            ])

        eventos = (await db_session.execute(
            select(BGPPrefixEvent).where(BGPPrefixEvent.bgp_session_id == sesion.id)
        )).scalars().all()
        assert len(eventos) == 1

    async def test_una_sesion_que_no_existe_no_rompe_el_reporte(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP, admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)

        resp = await self._reportar(client, rs, raw_key, "10.99.99.99", [
            {"prefix": "45.238.179.0/24", "as_path": [64605]},
        ])

        assert resp.status_code == 200
        assert resp.json()["sessions_updated"] == 0

    async def test_rechaza_un_prefijo_que_no_es_una_red(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP, admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)

        resp = await self._reportar(client, rs, raw_key, "192.0.2.55", [
            {"prefix": "no-es-un-prefijo", "as_path": []},
        ])

        assert resp.status_code == 422

    async def test_rechaza_un_asn_fuera_de_rango_en_el_path(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP, admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)

        resp = await self._reportar(client, rs, raw_key, "192.0.2.56", [
            {"prefix": "45.238.179.0/24", "as_path": [4294967296]},
        ])

        assert resp.status_code == 422

    async def test_guarda_las_communities_y_su_cambio(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP, admin_user: User,
    ):
        """Es donde el miembro ve si su prefijo validó por RPKI y como quedo
        clasificado, asi que un cambio ahi tiene que quedar registrado
        """
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)
        sesion = await self._sesion(db_session, ixp, rs, 64606, "192.0.2.57", 325)

        await self._reportar(client, rs, raw_key, "192.0.2.57", [
            {"prefix": "45.238.179.0/24", "as_path": [64606],
             "communities": ["64166:65012", "64166:65120"]},
        ])
        await self._reportar(client, rs, raw_key, "192.0.2.57", [
            {"prefix": "45.238.179.0/24", "as_path": [64606],
             "communities": ["64166:65023", "64166:65120"]},
        ])

        fila = (await db_session.execute(
            select(BGPSessionPrefix).where(BGPSessionPrefix.bgp_session_id == sesion.id)
        )).scalar_one()
        assert fila.communities == ["64166:65023", "64166:65120"]

        cambio = (await db_session.execute(
            select(BGPPrefixEvent).where(
                BGPPrefixEvent.bgp_session_id == sesion.id,
                BGPPrefixEvent.event_type == PrefixEventType.updated,
            )
        )).scalar_one()
        assert cambio.previous_communities == ["64166:65012", "64166:65120"]

    async def test_rechaza_una_community_que_no_es_numerica(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP, admin_user: User,
    ):
        rs = await _setup_route_server(db_session, ixp)
        raw_key = await _setup_agent_key(db_session, rs)

        resp = await self._reportar(client, rs, raw_key, "192.0.2.58", [
            {"prefix": "45.238.179.0/24", "as_path": [], "communities": ["drop table"]},
        ])

        assert resp.status_code == 422
