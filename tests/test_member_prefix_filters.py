"""Tests de la API de filtros de prefijos por miembro y familia."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import MemberState, PeeringPolicy
from ixforge.models.ixp import IXP
from ixforge.models.member import Member


@pytest.fixture
async def member(db_session: AsyncSession, ixp: IXP) -> Member:
    m = Member(
        ixp_id=ixp.id,
        name="Apoapsis",
        short_name="APO",
        asn=273973,
        state=MemberState.active,
        peering_policy=PeeringPolicy.open,
    )
    db_session.add(m)
    await db_session.flush()
    return m


async def test_put_prefix_filter_is_idempotent(
    client: AsyncClient, auth_headers: dict, member: Member
):
    body = {
        "origin_asns": [273973],
        "prefixes": ["45.170.100.0/24"],
        "as_set": "AS-APOAPSIS",
    }
    url = f"/api/v1/members/{member.id}/prefix-filters/4"

    first = await client.put(url, headers=auth_headers, json=body)
    second = await client.put(url, headers=auth_headers, json=body)

    assert first.status_code in (200, 201)
    assert second.status_code == 200
    assert second.json()["origin_asns"] == [273973]
    assert second.json()["as_set"] == "AS-APOAPSIS"


async def test_prefix_filter_rejects_wrong_family(
    client: AsyncClient, auth_headers: dict, member: Member
):
    """Un prefijo v6 en el filtro v4 es un error del operador, no algo a ignorar"""
    resp = await client.put(
        f"/api/v1/members/{member.id}/prefix-filters/4",
        headers=auth_headers,
        json={"prefixes": ["2001:db8::/32"]},
    )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_prefix_filter_rejects_invalid_af(
    client: AsyncClient, auth_headers: dict, member: Member
):
    resp = await client.put(
        f"/api/v1/members/{member.id}/prefix-filters/5", headers=auth_headers, json={}
    )

    assert resp.status_code == 422


async def test_prefix_filter_rejects_bad_asn(
    client: AsyncClient, auth_headers: dict, member: Member
):
    resp = await client.put(
        f"/api/v1/members/{member.id}/prefix-filters/4",
        headers=auth_headers,
        json={"origin_asns": [0]},
    )

    assert resp.status_code == 422


async def test_prefix_filter_acepta_lista_vacia(
    client: AsyncClient, auth_headers: dict, member: Member
):
    """Lista vacia significa "no autorizar ningun prefijo", y es un caso real:
    un colector de rutas que recibe y no anuncia debe tener lista blanca vacia,
    no ausente. Es distinto de null, que desactiva el filtro
    """
    resp = await client.put(
        f"/api/v1/members/{member.id}/prefix-filters/4",
        headers=auth_headers,
        json={"prefixes": [], "origin_asns": [273973]},
    )

    assert resp.status_code in (200, 201), resp.text
    assert resp.json()["prefixes"] == []


async def test_prefix_filter_null_disables_the_filter(
    client: AsyncClient, auth_headers: dict, member: Member
):
    resp = await client.put(
        f"/api/v1/members/{member.id}/prefix-filters/4",
        headers=auth_headers,
        json={"prefixes": None, "origin_asns": [273973]},
    )

    assert resp.status_code in (200, 201)
    assert resp.json()["prefixes"] is None


async def test_get_and_delete_prefix_filter(
    client: AsyncClient, auth_headers: dict, member: Member
):
    url = f"/api/v1/members/{member.id}/prefix-filters/4"
    await client.put(url, headers=auth_headers, json={"origin_asns": [273973]})

    fetched = await client.get(url, headers=auth_headers)
    deleted = await client.delete(url, headers=auth_headers)
    gone = await client.get(url, headers=auth_headers)

    assert fetched.status_code == 200
    assert deleted.status_code == 204
    assert gone.status_code == 404


async def test_member_user_cannot_write_prefix_filter(
    client: AsyncClient, member_auth_headers: dict, member: Member
):
    resp = await client.put(
        f"/api/v1/members/{member.id}/prefix-filters/4",
        headers=member_auth_headers,
        json={"origin_asns": [273973]},
    )

    assert resp.status_code == 403
