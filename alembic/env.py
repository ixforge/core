"""Alembic environment configuration for async SQLAlchemy."""

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Setear secret key por defecto para que get_settings() no falle al
# importar modelos durante migraciones manuales
os.environ.setdefault(
    "IXFORGE_SECRET_KEY",
    "alembic-migrations-default-key-at-least-32-chars",
)

# Import all models so Alembic can detect them
import ixforge.models  # noqa: E402, F401
from ixforge.models.base import Base  # noqa: E402

target_metadata = Base.metadata

# Tablas y tipos manejados por procrastinate (schema aplicado por su CLI)
PROCRASTINATE_TABLES = {
    "procrastinate_jobs",
    "procrastinate_events",
    "procrastinate_periodic_defers",
    "procrastinate_workers",
}
PROCRASTINATE_TYPES = {
    "procrastinate_job_status",
    "procrastinate_job_event_type",
    "procrastinate_job_to_defer_v1",
}


def include_object(
    object: object,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: object | None,
) -> bool:
    """Excluir tablas y tipos de procrastinate del autogenerate"""
    if type_ == "table" and name in PROCRASTINATE_TABLES:
        return False
    return not (type_ == "type" and name in PROCRASTINATE_TYPES)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        from ixforge.config import get_settings
        url = get_settings().database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    from ixforge.config import get_settings
    configuration = dict(config.get_section(config.config_ini_section, {}))
    configuration["sqlalchemy.url"] = get_settings().database_url
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
