"""Tests de la API de peers que no pertenecen a un miembro."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.models.ixp import IXP
from ixforge.models.route_server import RouteServer


@pytest.fixture
async def route_server(db_session: AsyncSession, ixp: IXP) -> RouteServer:
    rs = RouteServer(
        ixp_id=ixp.id, name="rs1", ip_v4="192.0.2.250", ip_v6="2001:db8::250"
    )
    db_session.add(rs)
    await db_session.flush()
    return rs


def _body(**overrides) -> dict:
    base = {
        "name": "PIT Chile v4",
        "peer_ip": "192.0.2.5",
        "peer_asn": 64166,
        "peer_type": "upstream",
    }
    base.update(overrides)
    return base


async def test_create_peer_returns_201(
    client: AsyncClient, auth_headers: dict, route_server: RouteServer
):
    resp = await client.post(
        f"/api/v1/route-servers/{route_server.id}/peers",
        headers=auth_headers,
        json=_body(mark_community="64166:9999"),
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["peer_type"] == "upstream"
    assert body["passive"] is True
    assert body["mark_community"] == "64166:9999"


async def test_create_peer_rejects_duplicate_ip(
    client: AsyncClient, auth_headers: dict, route_server: RouteServer
):
    url = f"/api/v1/route-servers/{route_server.id}/peers"
    await client.post(url, headers=auth_headers, json=_body())

    resp = await client.post(url, headers=auth_headers, json=_body(name="otro"))

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


async def test_create_peer_rejects_bad_community(
    client: AsyncClient, auth_headers: dict, route_server: RouteServer
):
    resp = await client.post(
        f"/api/v1/route-servers/{route_server.id}/peers",
        headers=auth_headers,
        json=_body(mark_community="no-es-una-community"),
    )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_create_peer_rejects_four_byte_asn_community(
    client: AsyncClient, auth_headers: dict, route_server: RouteServer
):
    """Una community estandar son 16:16 bits: BIRD rechazaria el config entero"""
    resp = await client.post(
        f"/api/v1/route-servers/{route_server.id}/peers",
        headers=auth_headers,
        json=_body(mark_community="273973:9999"),
    )

    assert resp.status_code == 422


async def test_create_peer_rejects_invalid_ip(
    client: AsyncClient, auth_headers: dict, route_server: RouteServer
):
    resp = await client.post(
        f"/api/v1/route-servers/{route_server.id}/peers",
        headers=auth_headers,
        json=_body(peer_ip="no.es.una.ip"),
    )

    assert resp.status_code == 422


async def test_member_user_cannot_create_peer(
    client: AsyncClient, member_auth_headers: dict, route_server: RouteServer
):
    resp = await client.post(
        f"/api/v1/route-servers/{route_server.id}/peers",
        headers=member_auth_headers,
        json=_body(),
    )

    assert resp.status_code == 403


async def test_peer_of_another_ixp_is_not_found(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    """El route server tiene que pertenecer al IXP del request"""
    import uuid

    resp = await client.post(
        f"/api/v1/route-servers/{uuid.uuid4()}/peers",
        headers=auth_headers,
        json=_body(),
    )

    assert resp.status_code == 404


async def test_list_and_get_peer(
    client: AsyncClient, auth_headers: dict, route_server: RouteServer
):
    url = f"/api/v1/route-servers/{route_server.id}/peers"
    created = await client.post(url, headers=auth_headers, json=_body())
    peer_id = created.json()["id"]

    listed = await client.get(url, headers=auth_headers)
    fetched = await client.get(f"{url}/{peer_id}", headers=auth_headers)

    assert listed.status_code == 200
    assert [p["id"] for p in listed.json()["items"]] == [peer_id]
    assert fetched.json()["peer_ip"] == "192.0.2.5"


async def test_create_peer_triggers_regeneration(
    client: AsyncClient, auth_headers: dict, route_server: RouteServer, monkeypatch
):
    """Sin el defer, la plataforma parece funcionar y el RS nunca recibe la config"""
    calls = []

    async def _fake_defer(rs_id, triggered_by):
        calls.append((rs_id, triggered_by))

    monkeypatch.setattr(
        "ixforge.tasks.config.defer_rs_config_regeneration", _fake_defer
    )

    await client.post(
        f"/api/v1/route-servers/{route_server.id}/peers",
        headers=auth_headers,
        json=_body(),
    )

    assert calls == [(route_server.id, "route_server_peer.created")]


async def test_update_and_delete_trigger_regeneration(
    client: AsyncClient, auth_headers: dict, route_server: RouteServer, monkeypatch
):
    url = f"/api/v1/route-servers/{route_server.id}/peers"
    created = await client.post(url, headers=auth_headers, json=_body())
    peer_id = created.json()["id"]

    calls = []

    async def _fake_defer(rs_id, triggered_by):
        calls.append(triggered_by)

    monkeypatch.setattr(
        "ixforge.tasks.config.defer_rs_config_regeneration", _fake_defer
    )

    patched = await client.patch(
        f"{url}/{peer_id}", headers=auth_headers, json={"max_prefixes": 100}
    )
    deleted = await client.delete(f"{url}/{peer_id}", headers=auth_headers)

    assert patched.status_code == 200
    assert patched.json()["max_prefixes"] == 100
    assert deleted.status_code == 204
    assert calls == ["route_server_peer.updated", "route_server_peer.deleted"]
