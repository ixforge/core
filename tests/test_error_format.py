"""Tests for unified error response format.

All API errors must return {"error": {"code": "...", "message": "...", "details": ...}}
regardless of the error source (custom exceptions, Pydantic validation, unhandled).
"""

from httpx import AsyncClient

from ixforge.models.ixp import IXP


class TestValidationErrorFormat:
    """RequestValidationError (422) must use unified error format"""

    async def test_invalid_body_returns_unified_format(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict[str, str]
    ):
        # POST login with malformed JSON triggers RequestValidationError
        resp = await client.post(
            "/api/v1/auth/login",
            content=b"not json",
            headers={**auth_headers, "Content-Type": "application/json"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert isinstance(body["error"]["message"], str)
        assert isinstance(body["error"]["details"], list)
        # Should not have top-level "detail" key (old FastAPI format)
        assert "detail" not in body

    async def test_missing_required_field_returns_unified_format(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict[str, str]
    ):
        resp = await client.post(
            "/api/v1/auth/login", json={}, headers=auth_headers
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert isinstance(body["error"]["details"], list)
        assert len(body["error"]["details"]) > 0
        assert "detail" not in body

    async def test_validation_details_contain_field_info(
        self, client: AsyncClient, ixp: IXP, auth_headers: dict[str, str]
    ):
        resp = await client.post(
            "/api/v1/auth/login", json={}, headers=auth_headers
        )
        assert resp.status_code == 422
        details = resp.json()["error"]["details"]
        # Each detail should have msg and type from Pydantic
        for item in details:
            assert "msg" in item
            assert "type" in item
