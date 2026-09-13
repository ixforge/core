"""Lectura de los prefijos que anuncia un miembro y de su historial.

Los escribe el agente en /agent/prefixes. Aca se prueba como salen: es lo que
consume la ficha publica del miembro
"""

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import BGPOperState, PrefixEventType
from ixforge.models.bgp_prefix import BGPPrefixEvent, BGPSessionPrefix
from ixforge.models.ixp import IXP
from ixforge.models.user import User
from tests.test_agent import _setup_route_server, _setup_sesion_bgp


async def _miembro_con_prefijos(db_session, ixp, asn=64700, address="192.0.2.60", vid=400):
    rs = await _setup_route_server(db_session, ixp)
    sesion = await _setup_sesion_bgp(
        db_session, ixp, rs, asn=asn, address=address, vid=vid,
        oper_state=BGPOperState.up, prefixes_imported=2,
    )
    ahora = datetime.now(UTC)

    db_session.add_all([
        BGPSessionPrefix(
            id=uuid.uuid4(), ixp_id=ixp.id, bgp_session_id=sesion.id,
            prefix="45.238.179.0/24", as_path=[asn],
            first_seen_at=ahora, last_seen_at=ahora,
        ),
        BGPSessionPrefix(
            id=uuid.uuid4(), ixp_id=ixp.id, bgp_session_id=sesion.id,
            prefix="2803:30d0:4958::/48", as_path=[64500, asn],
            first_seen_at=ahora, last_seen_at=ahora,
        ),
    ])
    db_session.add_all([
        BGPPrefixEvent(
            id=uuid.uuid4(), ixp_id=ixp.id, bgp_session_id=sesion.id,
            prefix="45.238.179.0/24", event_type=PrefixEventType.announced,
            as_path=[asn], occurred_at=ahora - timedelta(hours=2),
        ),
        BGPPrefixEvent(
            id=uuid.uuid4(), ixp_id=ixp.id, bgp_session_id=sesion.id,
            prefix="45.170.100.0/24", event_type=PrefixEventType.withdrawn,
            as_path=[asn], occurred_at=ahora - timedelta(minutes=5),
        ),
    ])
    await db_session.flush()
    return sesion


class TestPrefijosDeUnMiembro:
    async def test_lista_los_prefijos_que_anuncia(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP,
        admin_user: User, auth_headers,
    ):
        sesion = await _miembro_con_prefijos(db_session, ixp)
        member_id = await _member_id_de(db_session, sesion)

        resp = await client.get(
            f"/api/v1/members/{member_id}/prefixes", headers=auth_headers
        )

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert {i["prefix"] for i in items} == {"45.238.179.0/24", "2803:30d0:4958::/48"}
        v6 = next(i for i in items if i["prefix"] == "2803:30d0:4958::/48")
        assert v6["as_path"] == [64500, 64700]

    async def test_filtra_por_prefijo(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP,
        admin_user: User, auth_headers,
    ):
        sesion = await _miembro_con_prefijos(db_session, ixp, asn=64701, address="192.0.2.61", vid=401)
        member_id = await _member_id_de(db_session, sesion)

        resp = await client.get(
            f"/api/v1/members/{member_id}/prefixes?prefix=45.238", headers=auth_headers
        )

        assert resp.status_code == 200
        assert [i["prefix"] for i in resp.json()["items"]] == ["45.238.179.0/24"]

    async def test_el_comodin_del_filtro_se_escapa(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP,
        admin_user: User, auth_headers,
    ):
        """Un % en el filtro traeria todo. Es entrada de usuario y va a un LIKE"""
        sesion = await _miembro_con_prefijos(db_session, ixp, asn=64702, address="192.0.2.62", vid=402)
        member_id = await _member_id_de(db_session, sesion)

        resp = await client.get(
            f"/api/v1/members/{member_id}/prefixes?prefix=%25", headers=auth_headers
        )

        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_un_miembro_que_no_existe_da_404(
        self, client: AsyncClient, ixp: IXP, admin_user: User, auth_headers,
    ):
        resp = await client.get(
            f"/api/v1/members/{uuid.uuid4()}/prefixes", headers=auth_headers
        )
        assert resp.status_code == 404


class TestHistorialDePrefijos:
    async def test_devuelve_los_eventos_mas_nuevos_primero(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP,
        admin_user: User, auth_headers,
    ):
        sesion = await _miembro_con_prefijos(db_session, ixp, asn=64703, address="192.0.2.63", vid=403)
        member_id = await _member_id_de(db_session, sesion)

        resp = await client.get(
            f"/api/v1/members/{member_id}/prefix-events", headers=auth_headers
        )

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert [i["event_type"] for i in items] == ["withdrawn", "announced"]
        assert items[0]["prefix"] == "45.170.100.0/24"

    async def test_filtra_por_prefijo(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP,
        admin_user: User, auth_headers,
    ):
        sesion = await _miembro_con_prefijos(db_session, ixp, asn=64704, address="192.0.2.64", vid=404)
        member_id = await _member_id_de(db_session, sesion)

        resp = await client.get(
            f"/api/v1/members/{member_id}/prefix-events?prefix=45.170.100.0/24",
            headers=auth_headers,
        )

        assert resp.status_code == 200
        assert [i["prefix"] for i in resp.json()["items"]] == ["45.170.100.0/24"]


async def _member_id_de(db_session, sesion) -> uuid.UUID:
    from sqlalchemy import select

    from ixforge.models.trunk import Trunk, TrunkVLAN

    return await db_session.scalar(
        select(Trunk.member_id)
        .join(TrunkVLAN, TrunkVLAN.trunk_id == Trunk.id)
        .where(TrunkVLAN.id == sesion.trunk_vlan_id)
    )


class TestRetencionDeEventos:
    async def test_borra_los_eventos_viejos_y_deja_los_recientes(
        self, db_session: AsyncSession, ixp: IXP,
    ):
        """Sin retencion la tabla crece para siempre. El corte es por fecha del
        evento, no por cuando se inserto: son la misma cosa aca, pero occurred_at
        es lo que significa
        """
        from ixforge.tasks.maintenance import _borrar_eventos_de_prefijos

        rs = await _setup_route_server(db_session, ixp)
        sesion = await _setup_sesion_bgp(
            db_session, ixp, rs, asn=64710, address="192.0.2.70", vid=410,
            oper_state=BGPOperState.up,
        )
        ahora = datetime.now(UTC)
        db_session.add_all([
            BGPPrefixEvent(
                id=uuid.uuid4(), ixp_id=ixp.id, bgp_session_id=sesion.id,
                prefix="45.238.179.0/24", event_type=PrefixEventType.announced,
                as_path=[64710], occurred_at=ahora - timedelta(days=120),
            ),
            BGPPrefixEvent(
                id=uuid.uuid4(), ixp_id=ixp.id, bgp_session_id=sesion.id,
                prefix="45.170.100.0/24", event_type=PrefixEventType.announced,
                as_path=[64710], occurred_at=ahora - timedelta(days=5),
            ),
        ])
        await db_session.flush()

        borrados = await _borrar_eventos_de_prefijos(db_session, retention_days=90)

        assert borrados == 1
        quedan = (await db_session.execute(
            select(BGPPrefixEvent).where(BGPPrefixEvent.bgp_session_id == sesion.id)
        )).scalars().all()
        assert [e.prefix for e in quedan] == ["45.170.100.0/24"]


class TestOrigenDeLosEventos:
    async def test_cada_evento_dice_de_que_route_server_vino(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP,
        admin_user: User, auth_headers,
    ):
        """Los dos route servers ven el mismo anuncio, asi que el historial trae
        el hecho dos veces. Sin decir de cual vino cada fila, se lee como un
        duplicado sin sentido en vez de como lo que es
        """
        sesion = await _miembro_con_prefijos(db_session, ixp, asn=64720, address="192.0.2.80", vid=420)
        member_id = await _member_id_de(db_session, sesion)

        resp = await client.get(
            f"/api/v1/members/{member_id}/prefix-events", headers=auth_headers
        )

        assert resp.status_code == 200
        assert all(i["route_server"] for i in resp.json()["items"])


class TestPrefijosDelUpstream:
    """El upstream tiene prefijos como cualquiera, solo que cuelgan de su peer"""

    async def _con_peer(self, db_session, ixp, asn=64800, address="192.0.2.100", vid=430):
        from ixforge.enums import RouteServerPeerType
        from ixforge.models.route_server_peer import RouteServerPeer

        rs = await _setup_route_server(db_session, ixp)
        sesion = await _setup_sesion_bgp(
            db_session, ixp, rs, asn=asn, address=address, vid=vid,
            oper_state=BGPOperState.up,
        )
        peer = RouteServerPeer(
            id=uuid.uuid4(), ixp_id=ixp.id, route_server_id=rs.id,
            name="Upstream", peer_ip=address, peer_asn=asn,
            peer_type=RouteServerPeerType.upstream,
        )
        db_session.add(peer)
        await db_session.flush()

        ahora = datetime.now(UTC)
        db_session.add(BGPSessionPrefix(
            id=uuid.uuid4(), ixp_id=ixp.id, route_server_peer_id=peer.id,
            prefix="181.123.200.0/22", as_path=[61522, 23201],
            communities=["61522:65012"], first_seen_at=ahora, last_seen_at=ahora,
        ))
        db_session.add(BGPPrefixEvent(
            id=uuid.uuid4(), ixp_id=ixp.id, route_server_peer_id=peer.id,
            prefix="181.123.200.0/22", event_type=PrefixEventType.announced,
            as_path=[61522, 23201], communities=["61522:65012"], occurred_at=ahora,
        ))
        await db_session.flush()
        return sesion

    async def test_lista_los_prefijos_que_llegan_por_el_peer(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP,
        admin_user: User, auth_headers,
    ):
        sesion = await self._con_peer(db_session, ixp)
        member_id = await _member_id_de(db_session, sesion)

        resp = await client.get(
            f"/api/v1/members/{member_id}/prefixes", headers=auth_headers
        )

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert [i["prefix"] for i in items] == ["181.123.200.0/22"]
        assert items[0]["as_path"] == [61522, 23201]

    async def test_el_historial_del_peer_tambien_sale(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP,
        admin_user: User, auth_headers,
    ):
        sesion = await self._con_peer(db_session, ixp, asn=64801, address="192.0.2.101", vid=431)
        member_id = await _member_id_de(db_session, sesion)

        resp = await client.get(
            f"/api/v1/members/{member_id}/prefix-events", headers=auth_headers
        )

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert [i["prefix"] for i in items] == ["181.123.200.0/22"]
        assert items[0]["route_server"]

    async def test_el_limite_se_aplica_en_la_base(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP,
        admin_user: User, auth_headers,
    ):
        """Con la tabla del upstream son cientos de miles de filas: traerlas
        todas para quedarse con 25 tarda medio minuto
        """
        sesion = await self._con_peer(db_session, ixp, asn=64802, address="192.0.2.102", vid=432)
        member_id = await _member_id_de(db_session, sesion)
        peer_id = (await db_session.execute(
            select(BGPSessionPrefix.route_server_peer_id).where(
                BGPSessionPrefix.route_server_peer_id.is_not(None)
            ).limit(1)
        )).scalar_one()

        ahora = datetime.now(UTC)
        db_session.add_all([
            BGPSessionPrefix(
                id=uuid.uuid4(), ixp_id=ixp.id, route_server_peer_id=peer_id,
                prefix=f"10.{a}.{b}.0/24", as_path=[61522], communities=[],
                first_seen_at=ahora, last_seen_at=ahora,
            )
            for a in range(8) for b in range(256)
        ])
        await db_session.flush()

        resp = await client.get(
            f"/api/v1/members/{member_id}/prefixes?limit=25", headers=auth_headers
        )

        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 25

    async def test_el_mismo_prefijo_de_dos_route_servers_sale_una_vez(
        self, client: AsyncClient, db_session: AsyncSession, ixp: IXP,
        admin_user: User, auth_headers,
    ):
        """Y conserva el primer avistaje mas viejo y el ultimo mas nuevo, que es
        lo que significan esas dos fechas cuando hay dos observadores
        """
        from ixforge.enums import RouteServerPeerType
        from ixforge.models.route_server_peer import RouteServerPeer

        sesion = await self._con_peer(db_session, ixp, asn=64803, address="192.0.2.103", vid=433)
        member_id = await _member_id_de(db_session, sesion)

        rs2 = await _setup_route_server(db_session, ixp)
        otro = RouteServerPeer(
            id=uuid.uuid4(), ixp_id=ixp.id, route_server_id=rs2.id,
            name="Upstream rs2", peer_ip="192.0.2.103", peer_asn=64803,
            peer_type=RouteServerPeerType.upstream,
        )
        db_session.add(otro)
        await db_session.flush()

        viejo = datetime.now(UTC) - timedelta(days=3)
        nuevo = datetime.now(UTC)
        db_session.add(BGPSessionPrefix(
            id=uuid.uuid4(), ixp_id=ixp.id, route_server_peer_id=otro.id,
            prefix="181.123.200.0/22", as_path=[61522, 23201], communities=[],
            first_seen_at=viejo, last_seen_at=nuevo,
        ))
        await db_session.flush()

        resp = await client.get(
            f"/api/v1/members/{member_id}/prefixes", headers=auth_headers
        )

        items = resp.json()["items"]
        assert [i["prefix"] for i in items] == ["181.123.200.0/22"]
        assert items[0]["first_seen_at"].startswith(viejo.strftime("%Y-%m-%d"))
