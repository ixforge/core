"""Test configuration and fixtures."""

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ixforge.models.base import Base
from ixforge.models.ixp import IXP
from ixforge.models.user import User, UserRole
from ixforge.services.auth import create_access_token, hash_password

TEST_DATABASE_URL = "postgresql+asyncpg://ixforge:ixforge@localhost:5433/ixforge_test"


@pytest.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True, scope="session")
async def _create_tables(test_engine):
    """Create all tables once per test session, drop them at the end."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession]:
    """Provide a transactional database session that rolls back after each test.

    Uses nested transactions (savepoints) so that service code calling
    ``session.flush()`` works correctly while still rolling back everything
    at the end of the test.
    """
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        session_factory = async_sessionmaker(
            bind=connection,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with session_factory() as session:
            nested = await connection.begin_nested()

            @event.listens_for(session.sync_session, "after_transaction_end")
            def _restart_savepoint(sync_session, sync_transaction):
                nonlocal nested
                if not nested.is_active:
                    nested = connection.sync_connection.begin_nested()  # type: ignore[union-attr]

            yield session

        await transaction.rollback()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """Provide an async HTTP client wired to the FastAPI app with the test DB session."""
    from ixforge.api.deps import get_db_session
    from ixforge.main import create_app

    test_app = create_app()

    async def _override_get_db_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    test_app.dependency_overrides[get_db_session] = _override_get_db_session

    transport = ASGITransport(app=test_app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    test_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def ixp(db_session: AsyncSession) -> IXP:
    """Create a default IXP for tests."""
    obj = IXP(
        id=uuid.uuid4(),
        name="Test IXP",
        short_name="TIXP",
        asn=65000,
        country="US",
        city="Testville",
    )
    db_session.add(obj)
    await db_session.flush()
    return obj


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Create an admin user."""
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        hashed_password=hash_password("adminpass123"),
        full_name="Admin User",
        role=UserRole.admin,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def member_user(db_session: AsyncSession) -> User:
    """Create a member-role user (not linked to any member yet)."""
    user = User(
        id=uuid.uuid4(),
        email="member@example.com",
        hashed_password=hash_password("memberpass123"),
        full_name="Member User",
        role=UserRole.member,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def auth_headers(admin_user: User) -> dict[str, str]:
    """Return Authorization header dict with a valid JWT for the admin user."""
    token = create_access_token(subject=str(admin_user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def member_auth_headers(member_user: User) -> dict[str, str]:
    """Return Authorization header dict with a valid JWT for the member user."""
    token = create_access_token(subject=str(member_user.id))
    return {"Authorization": f"Bearer {token}"}
