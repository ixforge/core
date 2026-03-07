"""Procrastinate app configuration."""

from procrastinate import App, PsycopgConnector

from ixforge.config import get_settings


def _get_conninfo() -> str:
    """Convert the SQLAlchemy DATABASE_URL to a psycopg-compatible conninfo string.

    The application DATABASE_URL uses the ``postgresql+asyncpg://`` scheme that
    SQLAlchemy requires.  Procrastinate uses psycopg directly, so we need a
    plain ``postgresql://`` (or empty-scheme) connection string.
    """
    url = get_settings().database_url
    # Strip SQLAlchemy dialect prefixes so psycopg can parse the URL
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    return url


app = App(
    connector=PsycopgConnector(conninfo=_get_conninfo()),
    import_paths=[
        "ixforge.tasks.config",
        "ixforge.tasks.maintenance",
    ],
)
