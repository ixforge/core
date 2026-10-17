"""An IXP installed before the templates existed ends up with the current default set

Templates live in the database, so a change to services/default_templates.py only
reaches existing IXPs through a data migration. This replays the whole chain from
the revision that first seeded them and compares against the canonical set
"""

import asyncio
import os

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from ixforge.config import get_settings
from ixforge.services.default_templates import DEFAULT_TEMPLATES

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://ixforge:ixforge@localhost:5433/ixforge_test",
)
_BASE_URL = TEST_DATABASE_URL.rsplit("/", 1)[0]
_DB_NAME = "template_migrations"
_BEFORE_TEMPLATE_SEED = "ebae9caa1810"


async def _admin_sql(*statements: str) -> None:
    admin = create_async_engine(f"{_BASE_URL}/postgres", isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        for statement in statements:
            await conn.execute(text(statement))
    await admin.dispose()


async def _execute(url: str, statement: str) -> list[tuple]:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        result = await conn.execute(text(statement))
        rows = [tuple(row) for row in result] if result.returns_rows else []
    await engine.dispose()
    return rows


def _upgrade(url: str, revision: str) -> None:
    # env.py reads the database URL from the app settings, not from alembic.ini
    previous = os.environ.get("IXFORGE_DATABASE_URL")
    os.environ["IXFORGE_DATABASE_URL"] = url
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), revision)
    finally:
        if previous is None:
            os.environ.pop("IXFORGE_DATABASE_URL", None)
        else:
            os.environ["IXFORGE_DATABASE_URL"] = previous
        get_settings.cache_clear()


# Synchronous on purpose: command.upgrade runs its own event loop because env.py is async
def test_migration_chain_leaves_unedited_templates_equal_to_the_default_set():
    asyncio.run(_admin_sql(f"DROP DATABASE IF EXISTS {_DB_NAME}", f"CREATE DATABASE {_DB_NAME}"))
    url = f"{_BASE_URL}/{_DB_NAME}"
    try:
        _upgrade(url, _BEFORE_TEMPLATE_SEED)
        asyncio.run(
            _execute(
                url, "INSERT INTO ixps (name, short_name, asn) VALUES ('Old IXP', 'OLD', 64500)"
            )
        )
        _upgrade(url, "head")

        rows = asyncio.run(_execute(url, "SELECT filename, content FROM route_server_templates"))
    finally:
        asyncio.run(_admin_sql(f"DROP DATABASE IF EXISTS {_DB_NAME}"))

    assert dict(rows) == {t["filename"]: t["content"] for t in DEFAULT_TEMPLATES}
