"""Tests for Port CRUD plus assign/release endpoints."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import ConnectionState, ConnectionType, MemberState, PeeringPolicy, PortType
from ixforge.models.connection import Connection
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.models.port import Port
from ixforge.models.switch import Switch


async def _create_switch(db: AsyncSession, ixp: IXP) -> Switch:
    sw = Switch(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name=f"sw-port-{uuid.uuid4().hex[:6]}",
        hostname="sw-port.example.net",
        is_active=True,
    )
    db.add(sw)
    await db.flush()
    return sw


async def _create_member(db: AsyncSession, ixp: IXP) -> Member:
    m = Member(
        id=uuid.uuid4(),
        ixp_id=ixp.id,
        name=f"Port Test Net {uuid.uuid4().hex[:6]}",
        short_name=f"PT{uuid.uuid4().hex[:4]}",
        asn=64512 + hash(uuid.uuid4()) % 1000,
        state=MemberState.provisioning,
        peering_policy=PeeringPolicy.open,
    )
    db.add(m)
    await db.flush()
    return m


class TestPortCRUD:
    async def test_create_port(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        sw = await _create_switch(db_session, ixp)

        resp = await client.post(
            "/api/v1/ports",
            headers=auth_headers,
            json={
                "switch_id": str(sw.id),
                "name": "Ethernet1",
                "speed": 10000,
                "type": "member",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Ethernet1"
        assert body["speed"] == 10000
        assert body["type"] == "member"
        assert body["member_id"] is None

    async def test_get_port(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        sw = await _create_switch(db_session, ixp)
        port = Port(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            switch_id=sw.id,
            name="Ethernet2",
            speed=10000,
            type=PortType.member,
            is_active=True,
        )
        db_session.add(port)
        await db_session.flush()

        resp = await client.get(f"/api/v1/ports/{port.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == str(port.id)

    async def test_list_ports_by_switch(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        sw = await _create_switch(db_session, ixp)
        for i in range(3):
            p = Port(
                id=uuid.uuid4(),
                ixp_id=ixp.id,
                switch_id=sw.id,
                name=f"Ethernet{10 + i}",
                speed=10000,
                type=PortType.member,
                is_active=True,
            )
            db_session.add(p)
        await db_session.flush()

        resp = await client.get(
            "/api/v1/ports",
            headers=auth_headers,
            params={"switch_id": str(sw.id)},
        )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 3

    async def test_update_port(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        sw = await _create_switch(db_session, ixp)
        port = Port(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            switch_id=sw.id,
            name="Ethernet99",
            speed=1000,
            type=PortType.member,
            is_active=True,
        )
        db_session.add(port)
        await db_session.flush()

        resp = await client.patch(
            f"/api/v1/ports/{port.id}",
            headers=auth_headers,
            json={"speed": 10000, "type": "infra"},
        )
        assert resp.status_code == 200
        assert resp.json()["speed"] == 10000
        assert resp.json()["type"] == "infra"

    async def test_delete_port(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        sw = await _create_switch(db_session, ixp)
        port = Port(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            switch_id=sw.id,
            name="EthernetDel",
            speed=10000,
            type=PortType.member,
            is_active=True,
        )
        db_session.add(port)
        await db_session.flush()

        resp = await client.delete(f"/api/v1/ports/{port.id}", headers=auth_headers)
        assert resp.status_code == 204


class TestPortAssignment:
    async def test_assign_port_to_member(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        sw = await _create_switch(db_session, ixp)
        member = await _create_member(db_session, ixp)
        port = Port(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            switch_id=sw.id,
            name="EthernetAssign",
            speed=10000,
            type=PortType.member,
            is_active=True,
        )
        db_session.add(port)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/ports/{port.id}/assign",
            headers=auth_headers,
            json={"member_id": str(member.id)},
        )
        assert resp.status_code == 200
        assert resp.json()["member_id"] == str(member.id)

    async def test_assign_already_assigned_port_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        sw = await _create_switch(db_session, ixp)
        member1 = await _create_member(db_session, ixp)
        member2 = await _create_member(db_session, ixp)

        port = Port(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            switch_id=sw.id,
            name="EthernetBusy",
            speed=10000,
            type=PortType.member,
            member_id=member1.id,
            is_active=True,
        )
        db_session.add(port)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/ports/{port.id}/assign",
            headers=auth_headers,
            json={"member_id": str(member2.id)},
        )
        assert resp.status_code == 409

    async def test_release_port(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        sw = await _create_switch(db_session, ixp)
        member = await _create_member(db_session, ixp)
        port = Port(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            switch_id=sw.id,
            name="EthernetRelease",
            speed=10000,
            type=PortType.member,
            member_id=member.id,
            is_active=True,
        )
        db_session.add(port)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/ports/{port.id}/release",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["member_id"] is None

    async def test_assign_unused_port_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        sw = await _create_switch(db_session, ixp)
        member = await _create_member(db_session, ixp)
        port = Port(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            switch_id=sw.id,
            name="EthernetUnused",
            speed=10000,
            type=PortType.unused,
            is_active=True,
        )
        db_session.add(port)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/ports/{port.id}/assign",
            headers=auth_headers,
            json={"member_id": str(member.id)},
        )
        assert resp.status_code == 422

    async def test_update_to_unused_with_member_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        sw = await _create_switch(db_session, ixp)
        member = await _create_member(db_session, ixp)
        port = Port(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            switch_id=sw.id,
            name="EthernetBusyUnused",
            speed=10000,
            type=PortType.member,
            member_id=member.id,
            is_active=True,
        )
        db_session.add(port)
        await db_session.flush()

        resp = await client.patch(
            f"/api/v1/ports/{port.id}",
            headers=auth_headers,
            json={"type": "unused"},
        )
        assert resp.status_code == 422

    async def test_create_unused_with_member_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        sw = await _create_switch(db_session, ixp)
        member = await _create_member(db_session, ixp)

        resp = await client.post(
            "/api/v1/ports",
            headers=auth_headers,
            json={
                "switch_id": str(sw.id),
                "name": "EthernetBadCreate",
                "speed": 10000,
                "type": "unused",
                "member_id": str(member.id),
            },
        )
        assert resp.status_code == 422

    async def test_release_unassigned_port_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        sw = await _create_switch(db_session, ixp)
        port = Port(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            switch_id=sw.id,
            name="EthernetFree",
            speed=10000,
            type=PortType.member,
            is_active=True,
        )
        db_session.add(port)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/ports/{port.id}/release",
            headers=auth_headers,
        )
        assert resp.status_code == 409

    async def test_release_port_with_active_connection_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        sw = await _create_switch(db_session, ixp)
        member = await _create_member(db_session, ixp)
        port = Port(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            switch_id=sw.id,
            name="EthernetActiveConn",
            speed=10000,
            type=PortType.member,
            member_id=member.id,
            is_active=True,
        )
        db_session.add(port)
        await db_session.flush()

        conn = Connection(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            member_id=member.id,
            port_id=port.id,
            type=ConnectionType.physical,
            state=ConnectionState.active,
            speed=10000,
        )
        db_session.add(conn)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/ports/{port.id}/release",
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_assign_infra_port_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        sw = await _create_switch(db_session, ixp)
        member = await _create_member(db_session, ixp)
        port = Port(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            switch_id=sw.id,
            name="EthernetInfra",
            speed=10000,
            type=PortType.infra,
            is_active=True,
        )
        db_session.add(port)
        await db_session.flush()

        resp = await client.post(
            f"/api/v1/ports/{port.id}/assign",
            headers=auth_headers,
            json={"member_id": str(member.id)},
        )
        assert resp.status_code == 422

    async def test_create_infra_port_with_member_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        sw = await _create_switch(db_session, ixp)
        member = await _create_member(db_session, ixp)

        resp = await client.post(
            "/api/v1/ports",
            headers=auth_headers,
            json={
                "switch_id": str(sw.id),
                "name": "EthernetInfraBadCreate",
                "speed": 10000,
                "type": "infra",
                "member_id": str(member.id),
            },
        )
        assert resp.status_code == 422

    async def test_update_to_infra_with_member_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        ixp: IXP,
    ):
        sw = await _create_switch(db_session, ixp)
        member = await _create_member(db_session, ixp)
        port = Port(
            id=uuid.uuid4(),
            ixp_id=ixp.id,
            switch_id=sw.id,
            name="EthernetInfraUpdate",
            speed=10000,
            type=PortType.member,
            member_id=member.id,
            is_active=True,
        )
        db_session.add(port)
        await db_session.flush()

        resp = await client.patch(
            f"/api/v1/ports/{port.id}",
            headers=auth_headers,
            json={"type": "infra"},
        )
        assert resp.status_code == 422
