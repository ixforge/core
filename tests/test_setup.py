"""Tests for setup service and endpoint."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.models.ixp import IXP
from ixforge.models.user import User, UserRole


class TestSetupEndpoint:
    """Tests for POST /api/v1/setup."""

    async def test_setup_creates_ixp_and_admin(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/setup",
            json={
                "ixp": {
                    "name": "Test IXP",
                    "short_name": "TIXP",
                    "asn": 65000,
                    "country": "CL",
                    "city": "Santiago",
                },
                "admin": {
                    "full_name": "Admin User",
                    "email": "admin@test.com",
                    "password": "securepass123",
                },
            },
        )
        assert resp.status_code == 201
        assert resp.json() == {"message": "Setup completed"}

    async def test_setup_creates_ixp_in_db(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        await client.post(
            "/api/v1/setup",
            json={
                "ixp": {
                    "name": "My IXP",
                    "short_name": "MIXP",
                    "asn": 65001,
                    "country": "CL",
                    "city": "Santiago",
                },
                "admin": {
                    "full_name": "Admin",
                    "email": "admin@myixp.com",
                    "password": "securepass123",
                },
            },
        )
        result = await db_session.execute(select(IXP).where(IXP.short_name == "MIXP"))
        ixp = result.scalar_one_or_none()
        assert ixp is not None
        assert ixp.name == "My IXP"
        assert ixp.asn == 65001

    async def test_setup_creates_admin_user_in_db(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        await client.post(
            "/api/v1/setup",
            json={
                "ixp": {
                    "name": "Admin Test IXP",
                    "short_name": "ATIXP",
                    "asn": 65002,
                    "country": "CL",
                    "city": "Santiago",
                },
                "admin": {
                    "full_name": "Super Admin",
                    "email": "super@test.com",
                    "password": "securepass123",
                },
            },
        )
        result = await db_session.execute(
            select(User).where(User.email == "super@test.com")
        )
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.full_name == "Super Admin"
        assert user.role == UserRole.admin
        assert user.is_active is True

    async def test_setup_rejects_when_ixp_exists(
        self, client: AsyncClient, ixp: IXP
    ):
        resp = await client.post(
            "/api/v1/setup",
            json={
                "ixp": {
                    "name": "Another IXP",
                    "short_name": "AIXP",
                    "asn": 65003,
                    "country": "CL",
                    "city": "Santiago",
                },
                "admin": {
                    "full_name": "Admin",
                    "email": "admin@another.com",
                    "password": "securepass123",
                },
            },
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["error"]["code"] == "CONFLICT"

    async def test_setup_validates_required_fields(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/setup",
            json={"ixp": {}, "admin": {}},
        )
        assert resp.status_code == 422

    async def test_setup_validates_password_min_length(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/setup",
            json={
                "ixp": {
                    "name": "Test IXP",
                    "short_name": "TIXP",
                    "asn": 65000,
                    "country": "CL",
                    "city": "Santiago",
                },
                "admin": {
                    "full_name": "Admin",
                    "email": "admin@test.com",
                    "password": "short",
                },
            },
        )
        assert resp.status_code == 422

    async def test_setup_website_is_optional(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/setup",
            json={
                "ixp": {
                    "name": "No Website IXP",
                    "short_name": "NWIXP",
                    "asn": 65004,
                    "country": "CL",
                    "city": "Santiago",
                },
                "admin": {
                    "full_name": "Admin",
                    "email": "admin@nw.com",
                    "password": "securepass123",
                },
            },
        )
        assert resp.status_code == 201

    async def test_setup_is_atomic_on_invalid_email(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """If admin creation fails, IXP should not be created either."""
        resp = await client.post(
            "/api/v1/setup",
            json={
                "ixp": {
                    "name": "Atomic IXP",
                    "short_name": "ATOM",
                    "asn": 65005,
                    "country": "CL",
                    "city": "Santiago",
                },
                "admin": {
                    "full_name": "Admin",
                    "email": "not-an-email",
                    "password": "securepass123",
                },
            },
        )
        assert resp.status_code == 422
        result = await db_session.execute(
            select(IXP).where(IXP.short_name == "ATOM")
        )
        assert result.scalar_one_or_none() is None


class TestSetupDefaultTemplates:
    """El setup debe instalar los templates BIRD default para el nuevo IXP."""

    async def test_setup_installs_default_templates(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        await client.post(
            "/api/v1/setup",
            json={
                "ixp": {
                    "name": "Template IXP",
                    "short_name": "TPLX",
                    "asn": 65010,
                    "country": "CL",
                    "city": "Santiago",
                },
                "admin": {
                    "full_name": "Admin",
                    "email": "admin@tplx.com",
                    "password": "securepass123",
                },
            },
        )
        result = await db_session.execute(select(IXP).where(IXP.short_name == "TPLX"))
        ixp = result.scalar_one()

        from ixforge.models.rs_template import RouteServerTemplate
        from ixforge.services.default_templates import DEFAULT_TEMPLATES

        tpl_result = await db_session.execute(
            select(RouteServerTemplate).where(RouteServerTemplate.ixp_id == ixp.id)
        )
        templates = {t.filename: t for t in tpl_result.scalars()}

        assert set(templates) == {t["filename"] for t in DEFAULT_TEMPLATES}
        assert templates["bird_v4.conf.j2"].is_protected is True
        assert templates["bird_v6.conf.j2"].is_protected is True


class TestSetupStatus:
    """Tests for GET /api/v1/setup/status."""

    async def test_status_not_configured(self, client: AsyncClient):
        resp = await client.get("/api/v1/setup/status")
        assert resp.status_code == 200
        assert resp.json() == {"configured": False}

    async def test_status_configured(self, client: AsyncClient, ixp: IXP):
        resp = await client.get("/api/v1/setup/status")
        assert resp.status_code == 200
        assert resp.json() == {"configured": True}
