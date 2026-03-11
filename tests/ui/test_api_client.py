"""Tests for the UI API client."""

import httpx
import pytest

from ixforge.ui.api_client import APIClient, APIError, AuthenticationError


@pytest.fixture
def api_client():
    return APIClient(base_url="http://core:8000")


class TestAPIClient:
    def _mock_client(self, handler) -> httpx.AsyncClient:
        """Return an AsyncClient backed by a MockTransport with the correct base_url."""
        return httpx.AsyncClient(
            base_url="http://core:8000",
            transport=httpx.MockTransport(handler),
        )

    async def test_get_success(self, api_client):
        """GET returns parsed JSON on 200."""
        api_client._client = self._mock_client(
            lambda req: httpx.Response(200, json={"items": [], "has_more": False})
        )
        result = await api_client.get("/api/v1/members", token="fake-jwt")
        assert result == {"items": [], "has_more": False}

    async def test_post_success(self, api_client):
        """POST returns parsed JSON on 201."""
        api_client._client = self._mock_client(
            lambda req: httpx.Response(201, json={"id": "abc", "name": "Test"})
        )
        result = await api_client.post("/api/v1/members", token="fake-jwt", json={"name": "Test"})
        assert result == {"id": "abc", "name": "Test"}

    async def test_401_raises_authentication_error(self, api_client):
        """401 from API raises AuthenticationError."""
        api_client._client = self._mock_client(
            lambda req: httpx.Response(401, json={"error": {"code": "UNAUTHORIZED", "message": "bad token", "details": {}}})
        )
        with pytest.raises(AuthenticationError):
            await api_client.get("/api/v1/members", token="expired")

    async def test_422_raises_api_error_with_details(self, api_client):
        """422 from API raises APIError with validation details."""
        body = {"error": {"code": "VALIDATION_ERROR", "message": "Validation error", "details": [{"loc": ["body", "name"], "msg": "required", "type": "missing"}]}}
        api_client._client = self._mock_client(
            lambda req: httpx.Response(422, json=body)
        )
        with pytest.raises(APIError) as exc_info:
            await api_client.post("/api/v1/members", token="jwt", json={})
        assert exc_info.value.status_code == 422

    async def test_404_raises_api_error(self, api_client):
        """404 from API raises APIError."""
        api_client._client = self._mock_client(
            lambda req: httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "not found", "details": {}}})
        )
        with pytest.raises(APIError) as exc_info:
            await api_client.get("/api/v1/members/bad-id", token="jwt")
        assert exc_info.value.status_code == 404

    async def test_login_returns_token(self, api_client):
        """login() returns access_token string."""
        api_client._client = self._mock_client(
            lambda req: httpx.Response(200, json={"access_token": "jwt123", "token_type": "bearer"})
        )
        token = await api_client.login("user@test.com", "pass123")
        assert token == "jwt123"

    async def test_delete_success(self, api_client):
        """DELETE returns None on 204."""
        api_client._client = self._mock_client(
            lambda req: httpx.Response(204)
        )
        result = await api_client.delete("/api/v1/vlans/123", token="jwt")
        assert result is None
