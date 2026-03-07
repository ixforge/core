"""Member portal tests: /users/me endpoint and role-based routing."""

from httpx import AsyncClient

from ixforge.models.user import User


class TestUsersMe:
    async def test_get_me_admin(
        self,
        client: AsyncClient,
        admin_user: User,
        auth_headers: dict[str, str],
    ) -> None:
        resp = await client.get("/api/v1/users/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(admin_user.id)
        assert data["role"] == "admin"

    async def test_get_me_member(
        self,
        client: AsyncClient,
        member_user: User,
        member_auth_headers: dict[str, str],
    ) -> None:
        resp = await client.get("/api/v1/users/me", headers=member_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(member_user.id)
        assert data["role"] == "member"

    async def test_get_me_unauthenticated(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/users/me")
        assert resp.status_code == 401
