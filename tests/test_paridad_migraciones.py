"""Las migraciones tienen que dejar el mismo schema que los modelos

La suite arma las tablas con Base.metadata.create_all, o sea desde los modelos.
Produccion las arma corriendo las migraciones. Una migracion a la que le falte
algo que el modelo declara pasa todos los tests y revienta al desplegar, por
ejemplo un server_default: sin el, un insert que no trae el valor viola el not
null
"""

import asyncio
import os

import pytest
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from ixforge.config import get_settings
from ixforge.models.base import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://ixforge:ixforge@localhost:5433/ixforge_test",
)
_BASE_URL = TEST_DATABASE_URL.rsplit("/", 1)[0]
_NOMBRE = "paridad_migraciones"


async def _sql_de_admin(*sentencias: str) -> None:
    admin = create_async_engine(f"{_BASE_URL}/postgres", isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        for s in sentencias:
            await conn.execute(text(s))
    await admin.dispose()


async def _leer_schema(url: str) -> dict[str, dict[str, dict]]:
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        radiografia = await conn.run_sync(lambda c: _radiografia(inspect(c)))
    await engine.dispose()
    return radiografia


# Sincrona a proposito: command.upgrade abre su propio event loop porque el
# env.py del proyecto es async, y no se puede anidar en uno ya corriendo
@pytest.fixture(scope="module")
def schema_de_migraciones():
    """Una base aparte con las migraciones aplicadas de cero"""
    asyncio.run(_sql_de_admin(
        f"DROP DATABASE IF EXISTS {_NOMBRE}",
        f"CREATE DATABASE {_NOMBRE}",
    ))

    url = f"{_BASE_URL}/{_NOMBRE}"

    # env.py ignora sqlalchemy.url en modo online y usa la config de la app, asi
    # que la unica forma de apuntarlo a otra base es por la variable de entorno
    previo = os.environ.get("IXFORGE_DATABASE_URL")
    os.environ["IXFORGE_DATABASE_URL"] = url
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        if previo is None:
            os.environ.pop("IXFORGE_DATABASE_URL", None)
        else:
            os.environ["IXFORGE_DATABASE_URL"] = previo
        get_settings.cache_clear()

    yield asyncio.run(_leer_schema(url))

    asyncio.run(_sql_de_admin(f"DROP DATABASE IF EXISTS {_NOMBRE}"))


def _radiografia(inspector) -> dict[str, dict[str, dict]]:
    """Tablas y columnas tal como quedaron, para comparar sin la conexion abierta"""
    return {
        tabla: {c["name"]: c for c in inspector.get_columns(tabla)}
        for tabla in inspector.get_table_names()
    }


def test_las_tablas_de_los_modelos_existen_en_las_migraciones(schema_de_migraciones):
    faltantes = set(Base.metadata.tables) - set(schema_de_migraciones)

    assert not faltantes, f"tablas que ninguna migracion crea: {sorted(faltantes)}"


def test_las_columnas_coinciden(schema_de_migraciones):
    problemas = []
    for nombre, tabla in Base.metadata.tables.items():
        reales = schema_de_migraciones.get(nombre)
        if reales is None:
            continue
        faltantes = {c.name for c in tabla.columns} - set(reales)
        if faltantes:
            problemas.append(f"{nombre}: faltan {sorted(faltantes)}")

    assert not problemas, "columnas declaradas que la migracion no crea: " + "; ".join(problemas)


def test_las_columnas_con_server_default_lo_tienen(schema_de_migraciones):
    """Una columna con server_default en el modelo tiene que tenerlo en la base"""
    problemas = []
    for nombre, tabla in Base.metadata.tables.items():
        reales = schema_de_migraciones.get(nombre)
        if reales is None:
            continue
        for col in tabla.columns:
            if col.server_default is None or col.name not in reales:
                continue
            if reales[col.name]["default"] is None:
                problemas.append(f"{nombre}.{col.name}")

    assert not problemas, (
        "columnas que el modelo declara con server_default y la migracion deja sin default: "
        + ", ".join(sorted(problemas))
    )
