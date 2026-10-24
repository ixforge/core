"""The general limit applies to every API route, before authentication

FastAPI includes routers lazily, so SlowAPIMiddleware cannot find the handler of
an /api/v1 route and used to skip all of them without limiting anything
"""

import pydantic
import pytest
from httpx import AsyncClient

from ixforge.config import Settings, get_settings
from ixforge.models.ixp import IXP
from tests.conftest import RATE_LIMIT_FOR_TESTS


async def test_a_route_is_limited_per_address(rate_limited_client: AsyncClient, ixp: IXP):
    responses = [
        await rate_limited_client.get("/api/v1/setup/status")
        for _ in range(RATE_LIMIT_FOR_TESTS + 1)
    ]

    assert [r.status_code for r in responses] == [200] * RATE_LIMIT_FOR_TESTS + [429]
    body = responses[-1].json()
    assert body["error"]["code"] == "RATE_LIMITED"
    assert set(body["error"]) == {"code", "message", "details"}


async def test_the_limit_runs_before_authentication(rate_limited_client: AsyncClient, ixp: IXP):
    statuses = [
        (await rate_limited_client.get("/api/v1/members")).status_code
        for _ in range(RATE_LIMIT_FOR_TESTS + 1)
    ]

    assert statuses == [401] * RATE_LIMIT_FOR_TESTS + [429]


async def test_each_path_has_its_own_counter(rate_limited_client: AsyncClient, ixp: IXP):
    for _ in range(RATE_LIMIT_FOR_TESTS):
        await rate_limited_client.get("/api/v1/setup/status")

    assert (await rate_limited_client.get("/api/v1/members")).status_code == 401


async def test_a_route_limit_answers_with_the_project_error_format(
    rate_limited_client: AsyncClient, ixp: IXP, monkeypatch: pytest.MonkeyPatch
):
    """Login keeps its own 10 per minute from the slowapi decorator"""
    monkeypatch.setattr(get_settings(), "rate_limit_per_minute", 100)

    responses = [
        await rate_limited_client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "wrong-password"},
        )
        for _ in range(11)
    ]

    assert [r.status_code for r in responses] == [401] * 10 + [429]
    body = responses[-1].json()
    assert body["error"]["code"] == "RATE_LIMITED"
    assert set(body["error"]) == {"code", "message", "details"}


def test_the_general_limit_must_be_positive():
    with pytest.raises(pydantic.ValidationError):
        Settings(rate_limit_per_minute=0)
