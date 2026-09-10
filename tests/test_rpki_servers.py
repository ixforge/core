"""Tests de la API de servidores RTR y de la politica RPKI del route server."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.models.ixp import IXP
from ixforge.models.route_server import RouteServer


@pytest.fixture
async def route_server(db_session: AsyncSession, ixp: IXP) -> RouteServer:
    rs = RouteServer(ixp_id=ixp.id, name="rs1", ip_v4="192.0.2.250")
    db_session.add(rs)
    await db_session.flush()
    return rs


async def test_create_rpki_server(client: AsyncClient, auth_headers: dict, ixp: IXP):
    resp = await client.post(
        "/api/v1/rpki-servers",
        headers=auth_headers,
        json={"name": "routinator", "host": "10.20.30.65"},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["port"] == 3323
    assert body["transport"] == "tcp"
    assert body["route_server_id"] is None


async def test_rpki_server_rejects_ssh_transport(
    client: AsyncClient, auth_headers: dict, ixp: IXP
):
    """El generador solo emite TCP: configurar ssh renderearia un config
    incorrecto en silencio
    """
    resp = await client.post(
        "/api/v1/rpki-servers",
        headers=auth_headers,
        json={"name": "x", "host": "10.0.0.1", "transport": "ssh"},
    )

    assert resp.status_code == 422
    assert "ssh" in str(resp.json()["error"]).lower()


async def test_rpki_server_rejects_duplicate_name(
    client: AsyncClient, auth_headers: dict, ixp: IXP
):
    body = {"name": "routinator", "host": "10.0.0.1"}
    await client.post("/api/v1/rpki-servers", headers=auth_headers, json=body)

    resp = await client.post("/api/v1/rpki-servers", headers=auth_headers, json=body)

    assert resp.status_code == 409


async def test_member_user_cannot_create_rpki_server(
    client: AsyncClient, member_auth_headers: dict, ixp: IXP
):
    resp = await client.post(
        "/api/v1/rpki-servers",
        headers=member_auth_headers,
        json={"name": "x", "host": "10.0.0.1"},
    )

    assert resp.status_code == 403


async def test_route_server_read_exposes_rpki_fields(
    client: AsyncClient, auth_headers: dict, route_server: RouteServer
):
    resp = await client.get(
        f"/api/v1/route-servers/{route_server.id}", headers=auth_headers
    )

    body = resp.json()
    assert body["passive_sessions"] is True
    assert body["rpki_enabled"] is False
    assert body["rpki_policy"] == "info_only"


async def test_enabling_rpki_triggers_regeneration(
    client: AsyncClient, auth_headers: dict, route_server: RouteServer, monkeypatch
):
    calls = []

    async def _fake_defer(rs_id, triggered_by):
        calls.append((rs_id, triggered_by))

    monkeypatch.setattr(
        "ixforge.tasks.config.defer_rs_config_regeneration", _fake_defer
    )

    resp = await client.patch(
        f"/api/v1/route-servers/{route_server.id}",
        headers=auth_headers,
        json={"rpki_enabled": True, "rpki_policy": "reject_invalid"},
    )

    assert resp.status_code == 200
    assert resp.json()["rpki_policy"] == "reject_invalid"
    assert calls == [(route_server.id, "route_server.updated")]


async def test_rpki_server_scoped_to_one_route_server(
    client: AsyncClient, auth_headers: dict, route_server: RouteServer, monkeypatch
):
    """Un servidor con route_server_id solo regenera ese route server"""
    calls = []

    async def _fake_defer(rs_id, triggered_by):
        calls.append(rs_id)

    monkeypatch.setattr(
        "ixforge.tasks.config.defer_rs_config_regeneration", _fake_defer
    )

    resp = await client.post(
        "/api/v1/rpki-servers",
        headers=auth_headers,
        json={
            "name": "solo-rs1",
            "host": "10.0.0.1",
            "route_server_id": str(route_server.id),
        },
    )

    assert resp.status_code == 201
    assert calls == [route_server.id]
