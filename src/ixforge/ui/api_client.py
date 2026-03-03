"""Thin httpx wrapper for consuming the Core REST API."""

from __future__ import annotations

from typing import Any

import httpx


class APIError(Exception):
    """Non-auth error from the Core API."""

    def __init__(self, status_code: int, detail: Any = None) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"API error {status_code}")


class AuthenticationError(Exception):
    """401 from Core API — JWT expired or invalid."""


class APIClient:
    """HTTP client that talks to the Core REST API."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    def _headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _check(self, resp: httpx.Response) -> None:
        if resp.status_code == 401:
            raise AuthenticationError()
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise APIError(resp.status_code, detail)

    async def get(self, path: str, token: str, params: dict[str, Any] | None = None) -> Any:
        resp = await self._client.get(path, headers=self._headers(token), params=params)
        self._check(resp)
        return resp.json()

    async def post(self, path: str, token: str, json: dict[str, Any] | None = None) -> Any:
        resp = await self._client.post(path, headers=self._headers(token), json=json)
        self._check(resp)
        if resp.status_code == 204:
            return None
        return resp.json()

    async def patch(self, path: str, token: str, json: dict[str, Any] | None = None) -> Any:
        resp = await self._client.patch(path, headers=self._headers(token), json=json)
        self._check(resp)
        return resp.json()

    async def delete(self, path: str, token: str) -> None:
        resp = await self._client.delete(path, headers=self._headers(token))
        self._check(resp)

    async def login(self, email: str, password: str) -> str:
        """POST /api/v1/auth/login and return the access_token."""
        resp = await self._client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        if resp.status_code == 401:
            raise AuthenticationError()
        self._check(resp)
        token: str = resp.json()["access_token"]
        return token

    async def close(self) -> None:
        await self._client.aclose()
