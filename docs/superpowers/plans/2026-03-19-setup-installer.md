# Setup / Installer Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a setup page that creates the initial IXP and admin user when the database is empty.

**Architecture:** New `POST /api/v1/setup` and `GET /api/v1/setup/status` endpoints (no auth). UI middleware redirects all routes to `/setup` when no IXP exists. Setup page uses `layouts/auth.html` (same as login).

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, Starlette middleware, Jinja2, TailwindCSS

**Spec:** `docs/superpowers/specs/2026-03-19-setup-installer-design.md`

---

### Task 1: Setup schemas

**Files:**
- Create: `src/ixforge/schemas/setup.py`

- [ ] **Step 1: Create the setup schemas**

```python
"""Setup schemas."""

from pydantic import BaseModel, EmailStr, Field, field_validator

from ixforge.schemas.common import validate_country_code


class SetupIXP(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    short_name: str = Field(min_length=1, max_length=50)
    asn: int = Field(gt=0)
    website: str | None = Field(default=None, max_length=512)
    country: str = Field(min_length=2, max_length=2)
    city: str = Field(min_length=1, max_length=255)

    @field_validator("country")
    @classmethod
    def country_must_be_uppercase(cls, v: str) -> str:
        return validate_country_code(v)


class SetupAdmin(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8)


class SetupRequest(BaseModel):
    ixp: SetupIXP
    admin: SetupAdmin


class SetupStatusResponse(BaseModel):
    configured: bool
```

- [ ] **Step 2: Commit**

```bash
git add src/ixforge/schemas/setup.py
git commit -m "feat(setup): add setup request/response schemas"
```

---

### Task 2: Setup service and API route

**Files:**
- Create: `src/ixforge/services/setup.py`
- Create: `src/ixforge/api/v1/setup.py`
- Modify: `src/ixforge/api/v1/router.py`
- Create: `tests/test_setup.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for setup service and endpoint."""

import pytest
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
        # Verify no IXP was created
        result = await db_session.execute(
            select(IXP).where(IXP.short_name == "ATOM")
        )
        assert result.scalar_one_or_none() is None


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/kr105/repos/ixforge/core && source .venv/bin/activate && pytest tests/test_setup.py -v`
Expected: FAIL (imports/routes not found)

- [ ] **Step 3: Create the setup service**

```python
"""Setup service: initial IXP and admin user creation."""

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import ConflictError
from ixforge.models.ixp import IXP
from ixforge.models.user import User, UserRole
from ixforge.schemas.setup import SetupRequest
from ixforge.services.auth import hash_password


async def run_setup(session: AsyncSession, data: SetupRequest) -> None:
    """Create the initial IXP and admin user.

    Uses an advisory lock to prevent concurrent setup calls.
    Raises ConflictError if an IXP already exists.
    """
    # Advisory lock to serialize concurrent setup attempts
    await session.execute(text("SELECT pg_advisory_xact_lock(1)"))

    # Guard: check no IXP exists
    count = await session.scalar(select(func.count()).select_from(IXP))
    if count and count > 0:
        raise ConflictError("IXP already configured")

    # Create IXP
    ixp = IXP(
        id=uuid.uuid4(),
        name=data.ixp.name,
        short_name=data.ixp.short_name,
        asn=data.ixp.asn,
        website=data.ixp.website,
        country=data.ixp.country,
        city=data.ixp.city,
    )
    session.add(ixp)
    await session.flush()

    # Create admin user
    user = User(
        id=uuid.uuid4(),
        email=data.admin.email,
        hashed_password=hash_password(data.admin.password),
        full_name=data.admin.full_name,
        role=UserRole.admin,
        is_active=True,
    )
    session.add(user)
    await session.flush()


async def is_configured(session: AsyncSession) -> bool:
    """Return True if at least one IXP exists."""
    count = await session.scalar(select(func.count()).select_from(IXP))
    return bool(count and count > 0)
```

- [ ] **Step 4: Create the API route**

```python
"""Setup endpoints: initial platform configuration."""

from fastapi import APIRouter

from ixforge.api.deps import DBSession
from ixforge.schemas.setup import SetupRequest, SetupStatusResponse
from ixforge.services import setup as setup_service

setup_router = APIRouter(prefix="/setup", tags=["setup"])


@setup_router.get("/status", response_model=SetupStatusResponse)
async def setup_status(db: DBSession) -> dict[str, bool]:
    configured = await setup_service.is_configured(db)
    return {"configured": configured}


@setup_router.post("", status_code=201)
async def run_setup(body: SetupRequest, db: DBSession) -> dict[str, str]:
    await setup_service.run_setup(db, body)
    return {"message": "Setup completed"}
```

- [ ] **Step 5: Register the route in router.py**

Modify: `src/ixforge/api/v1/router.py`

Add import:
```python
from ixforge.api.v1.setup import setup_router
```

Add registration (after `health_router`):
```python
v1_router.include_router(setup_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /home/kr105/repos/ixforge/core && source .venv/bin/activate && pytest tests/test_setup.py -v`
Expected: ALL PASS

- [ ] **Step 7: Run full test suite to verify no regressions**

Run: `cd /home/kr105/repos/ixforge/core && source .venv/bin/activate && pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add src/ixforge/services/setup.py src/ixforge/api/v1/setup.py src/ixforge/api/v1/router.py tests/test_setup.py
git commit -m "feat(setup): add setup endpoint and service with tests"
```

---

### Task 3: APIClient public methods

**Files:**
- Modify: `src/ixforge/ui/api_client.py`

- [ ] **Step 1: Add `get_public` and `post_public` methods**

Add these methods to the `APIClient` class in `src/ixforge/ui/api_client.py`, after the existing `login` method:

```python
    async def get_public(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET without authentication (for public endpoints like setup/status)."""
        resp = await self._client.get(path, params=params)
        self._check(resp)
        return resp.json()

    async def post_public(self, path: str, json: dict[str, Any] | None = None) -> Any:
        """POST without authentication (for public endpoints like setup)."""
        resp = await self._client.post(path, json=json)
        self._check(resp)
        if resp.status_code == 204:
            return None
        return resp.json()
```

- [ ] **Step 2: Commit**

```bash
git add src/ixforge/ui/api_client.py
git commit -m "feat(setup): add public GET/POST methods to APIClient"
```

---

### Task 4: UI setup route

**Files:**
- Create: `src/ixforge/ui/routes/setup.py`

- [ ] **Step 1: Create the setup route handlers**

```python
"""Setup route: initial platform configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.responses import RedirectResponse, Response

from ixforge.ui.api_client import APIError
from ixforge.ui.session import add_flash
from ixforge.ui.templating import render

if TYPE_CHECKING:
    from starlette.requests import Request


async def setup_page(request: Request) -> Response:
    """GET /setup — show the setup form, or redirect to login if already configured."""
    api = request.app.state.api
    try:
        status = await api.get_public("/api/v1/setup/status")
        if status.get("configured"):
            return RedirectResponse("/login", status_code=302)
    except Exception:
        pass
    return render(request, "setup.html", {"errors": {}})


async def setup_submit(request: Request) -> Response:
    """POST /setup — submit setup form to the API."""
    form = await request.form()

    password = str(form.get("password", ""))
    password_confirm = str(form.get("password_confirm", ""))

    if password != password_confirm:
        return render(request, "setup.html", {
            "errors": {"error": {"message": "Las contraseñas no coinciden"}},
            "form": dict(form),
        })

    payload = {
        "ixp": {
            "name": str(form.get("name", "")),
            "short_name": str(form.get("short_name", "")),
            "asn": int(form.get("asn", 0)) if form.get("asn") else 0,
            "website": str(form.get("website", "")) or None,
            "country": str(form.get("country", "")),
            "city": str(form.get("city", "")),
        },
        "admin": {
            "full_name": str(form.get("full_name", "")),
            "email": str(form.get("email", "")),
            "password": password,
        },
    }

    api = request.app.state.api
    try:
        await api.post_public("/api/v1/setup", json=payload)
    except APIError as exc:
        if exc.status_code == 409:
            add_flash(request, "El sistema ya fue configurado", "info")
            return RedirectResponse("/login", status_code=302)
        return render(request, "setup.html", {
            "errors": exc.detail if isinstance(exc.detail, dict) else {"error": {"message": str(exc.detail)}},
            "form": dict(form),
        })

    # Mark as configured in app state cache
    request.app.state.ixp_configured = True
    add_flash(request, "Instalacion completada", "success")
    return RedirectResponse("/login", status_code=302)
```

- [ ] **Step 2: Commit**

```bash
git add src/ixforge/ui/routes/setup.py
git commit -m "feat(setup): add UI setup route handlers"
```

---

### Task 5: Setup template

**Files:**
- Create: `src/ixforge/ui/templates/setup.html`

- [ ] **Step 1: Create the setup template**

```html
{% extends "layouts/auth.html" %}
{% block title %}Setup - IXForge{% endblock %}
{% block content %}
<div class="w-full max-w-lg">
  <div class="text-center mb-8">
    <h1 class="text-3xl font-bold text-gray-900 dark:text-white">Bienvenido a IXForge</h1>
    <p class="mt-2 text-gray-600 dark:text-gray-400">Configura tu IXP para comenzar</p>
  </div>
  <div class="card">
    {% if errors and errors.error is defined %}
    <div class="mb-4 p-3 rounded-lg bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300 text-sm">
      <p>{{ errors.error.message }}</p>
      {% if errors.error.details is defined and errors.error.details is iterable and errors.error.details is not string %}
        {% for err in errors.error.details %}
          <p>{{ err.msg if err.msg is defined else err }}</p>
        {% endfor %}
      {% endif %}
    </div>
    {% endif %}
    <form method="post" class="space-y-6">
      <div>
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">Datos del IXP</h3>
        <div class="space-y-3">
          <div>
            <label for="name" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Nombre</label>
            <input type="text" name="name" id="name" required class="input-field" placeholder="ej: PatagoniaIX" value="{{ form.name if form else '' }}">
          </div>
          <div>
            <label for="short_name" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Nombre corto</label>
            <input type="text" name="short_name" id="short_name" required class="input-field" placeholder="ej: PTGIX" maxlength="50" value="{{ form.short_name if form else '' }}">
          </div>
          <div>
            <label for="asn" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">ASN</label>
            <input type="number" name="asn" id="asn" required class="input-field" placeholder="ej: 65000" min="1" value="{{ form.asn if form else '' }}">
          </div>
          <div>
            <label for="website" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Sitio web <span class="text-gray-400">(opcional)</span></label>
            <input type="url" name="website" id="website" class="input-field" placeholder="ej: https://patagoniaix.net" value="{{ form.website if form else '' }}">
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label for="country" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Pais</label>
              <input type="text" name="country" id="country" required class="input-field" placeholder="ej: CL" maxlength="2" value="{{ form.country if form else '' }}">
            </div>
            <div>
              <label for="city" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Ciudad</label>
              <input type="text" name="city" id="city" required class="input-field" placeholder="ej: Santiago" value="{{ form.city if form else '' }}">
            </div>
          </div>
        </div>
      </div>
      <div>
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">Cuenta de Administrador</h3>
        <div class="space-y-3">
          <div>
            <label for="full_name" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Nombre completo</label>
            <input type="text" name="full_name" id="full_name" required class="input-field" value="{{ form.full_name if form else '' }}">
          </div>
          <div>
            <label for="email" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Email</label>
            <input type="email" name="email" id="email" required class="input-field" value="{{ form.email if form else '' }}">
          </div>
          <div>
            <label for="password" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Contraseña</label>
            <input type="password" name="password" id="password" required class="input-field" minlength="8">
          </div>
          <div>
            <label for="password_confirm" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Confirmar contraseña</label>
            <input type="password" name="password_confirm" id="password_confirm" required class="input-field" minlength="8">
          </div>
        </div>
      </div>
      <button type="submit" class="btn-primary w-full">Iniciar IXForge</button>
    </form>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add src/ixforge/ui/templates/setup.html
git commit -m "feat(setup): add setup page template"
```

---

### Task 6: Register UI route and add middleware

**Files:**
- Modify: `src/ixforge/ui/app.py`

- [ ] **Step 1: Add setup route import and routes**

In `src/ixforge/ui/app.py`, add the import of the setup module alongside the other route imports:

```python
from ixforge.ui.routes import (
    auth,
    # ... existing imports ...
    setup,
)
```

Add the setup routes right after the auth routes in the `routes` list:

```python
        # Setup
        Route("/setup", setup.setup_page, methods=["GET"]),
        Route("/setup", setup.setup_submit, methods=["POST"]),
```

- [ ] **Step 2: Add the SetupRedirectMiddleware**

Add this middleware class before the `create_ui_app` function in `src/ixforge/ui/app.py`:

```python
from starlette.types import ASGIApp, Receive, Scope, Send


class SetupRedirectMiddleware:
    """Redirect all routes to /setup when no IXP is configured."""

    _EXEMPT_PREFIXES = ("/setup", "/static", "/media")

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if any(path.startswith(p) for p in self._EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        # Check cache first
        app = scope.get("app")
        if app and getattr(app.state, "ixp_configured", False):
            await self.app(scope, receive, send)
            return

        # Check via API
        try:
            api = app.state.api if app else None
            if api:
                status = await api.get_public("/api/v1/setup/status")
                if status.get("configured"):
                    if app:
                        app.state.ixp_configured = True
                    await self.app(scope, receive, send)
                    return
        except Exception:
            # Fail open: let the request through
            await self.app(scope, receive, send)
            return

        # Not configured: redirect to /setup
        response = RedirectResponse("/setup", status_code=302)
        await response(scope, receive, send)
```

Register the middleware in `create_ui_app()`, after `SessionMiddleware`:

```python
    app.add_middleware(SetupRedirectMiddleware)
```

Note: Starlette executes middleware in reverse order of `add_middleware` calls, so `SetupRedirectMiddleware` (added second) runs first, then `SessionMiddleware`. This is correct because the setup redirect doesn't need session data.

- [ ] **Step 3: Run the full test suite**

Run: `cd /home/kr105/repos/ixforge/core && source .venv/bin/activate && pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add src/ixforge/ui/app.py
git commit -m "feat(setup): register setup routes and redirect middleware"
```

---

### Task 7: CLI cleanup

**Files:**
- Modify: `src/ixforge/cli.py`

- [ ] **Step 1: Remove `seed` command and add IXP check to `createsuperuser`**

In `src/ixforge/cli.py`:

1. Remove the `_seed_data()` async function entirely
2. Remove the `_run_seed()` function entirely
3. Remove `"seed": "Seed database with sample development data"` from `_COMMANDS`
4. Remove the `elif command == "seed":` block from `main()`

5. Add IXP existence check to `_create_admin_user()`:

```python
async def _create_admin_user(email: str, password: str, full_name: str) -> None:
    """Insert the admin user into the database."""
    from sqlalchemy import func, select

    from ixforge.database import get_session_factory
    from ixforge.models.ixp import IXP
    from ixforge.models.user import User, UserRole
    from ixforge.services.auth import hash_password

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Verify at least one IXP exists
        ixp_count = await session.scalar(select(func.count()).select_from(IXP))
        if not ixp_count:
            print("Error: no IXP configured. Run setup via the web UI first.")
            sys.exit(1)

        result = await session.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()
        if existing is not None:
            print(f"Error: user with email '{email}' already exists")
            sys.exit(1)

        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=UserRole.admin,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        print(f"Admin user '{email}' created successfully.")
```

- [ ] **Step 2: Run the full test suite**

Run: `cd /home/kr105/repos/ixforge/core && source .venv/bin/activate && pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add src/ixforge/cli.py
git commit -m "feat(setup): remove seed command, add IXP check to createsuperuser"
```

---

### Task 8: Manual verification

- [ ] **Step 1: Clean the database and test the full flow**

```bash
docker exec ixforge-pg psql -U ixforge -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" ixforge
source .venv/bin/activate && ixforge upgrade
```

- [ ] **Step 2: Start the API and UI**

```bash
nohup ixforge run > /tmp/ixforge-api.log 2>&1 &
nohup ixforge ui > /tmp/ixforge-ui.log 2>&1 &
```

- [ ] **Step 3: Verify the setup flow**

1. Open http://localhost:8001 in the browser → should redirect to `/setup`
2. Fill in the form and submit
3. Should redirect to `/login` with flash "Instalacion completada"
4. Login with the admin credentials just created
5. Visit http://localhost:8001/setup again → should redirect to `/login`

- [ ] **Step 4: Run linting and type checks**

```bash
cd /home/kr105/repos/ixforge/core && source .venv/bin/activate
ruff check src/ixforge/schemas/setup.py src/ixforge/services/setup.py src/ixforge/api/v1/setup.py src/ixforge/ui/routes/setup.py
mypy src/ixforge/schemas/setup.py src/ixforge/services/setup.py src/ixforge/api/v1/setup.py src/ixforge/ui/routes/setup.py
```
