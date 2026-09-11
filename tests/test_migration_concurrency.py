"""Test de que dos migraciones concurrentes no se pisan.

Los tres servicios de un deploy (core, worker, portal) arrancan a la vez desde
la misma imagen y el entrypoint de todos aplica migraciones. Sin serializacion
compiten sobre la misma base.
"""

import os
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

REPO = Path(__file__).parent.parent


@pytest.fixture
async def base_vacia() -> str:
    """Una base recien creada, para migrar desde cero"""
    admin_url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://ixforge:ixforge@localhost:5433/ixforge_test",
    )
    nombre = f"ixforge_mig_{uuid.uuid4().hex[:8]}"
    raiz = admin_url.rsplit("/", 1)[0] + "/postgres"

    engine = create_async_engine(raiz, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{nombre}"'))
    await engine.dispose()

    yield admin_url.rsplit("/", 1)[0] + "/" + nombre

    engine = create_async_engine(raiz, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{nombre}'"
            )
        )
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{nombre}"'))
    await engine.dispose()


def _migrar(url: str) -> subprocess.CompletedProcess[str]:
    entorno = {
        **os.environ,
        "IXFORGE_DATABASE_URL": url,
        "IXFORGE_SECRET_KEY": "x" * 40,
    }
    return subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=REPO,
        env=entorno,
        capture_output=True,
        text=True,
        check=False,
    )


async def test_migraciones_concurrentes_no_se_pisan(base_vacia):
    """Tres migraciones a la vez sobre una base vacia tienen que terminar todas
    bien, no una bien y dos rotas
    """
    with ThreadPoolExecutor(3) as ex:
        resultados = list(ex.map(_migrar, [base_vacia] * 3))

    fallidas = [r for r in resultados if r.returncode != 0]
    assert not fallidas, "\n\n".join(
        f"exit={r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        for r in fallidas
    )

    engine = create_async_engine(base_vacia)
    async with engine.connect() as conn:
        version = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
        tablas = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = current_schema()"
                )
            )
        ).scalar_one()
    await engine.dispose()

    assert version == "9f2c7a1b4d3e"
    assert tablas > 25


def _correr_entrypoint(*args: str) -> str:
    """Corre el entrypoint con los comandos reales reemplazados por echo

    Reemplaza las DOS invocaciones, la del upgrade y la del exec: si solo se
    cambia el exec, el test aplica migraciones de verdad contra la base que
    haya configurada
    """
    guion = (REPO / "docker" / "entrypoint.sh").read_text(encoding="utf-8")
    guion = guion.replace("uv run ixforge upgrade", "echo MIGRA")
    guion = guion.replace("exec uv run ixforge", "echo ARRANCA")

    return subprocess.run(
        ["sh", "-s", *args],
        input=guion,
        capture_output=True,
        text=True,
        env={**os.environ, "IXFORGE_AUTO_MIGRATE": "true"},
        check=False,
    ).stdout


def test_entrypoint_migra_para_la_api_y_el_worker():
    for comando in ("run", "worker"):
        salida = _correr_entrypoint(comando)
        assert "MIGRA" in salida, comando
        assert f"ARRANCA {comando}" in salida


def test_entrypoint_no_migra_para_la_ui():
    """El portal habla con la API por HTTP y no tiene credenciales de base.

    Hacerlo migrar lo obligaria a tenerlas, que es ampliar su superficie por
    comodidad. Ademas rompe: el compose no le pasa IXFORGE_DATABASE_URL y el
    contenedor muere intentando conectarse a localhost:5432
    """
    salida = _correr_entrypoint("ui")

    assert "MIGRA" not in salida
    assert "sin migrar" in salida
    assert "ARRANCA ui" in salida


def test_entrypoint_respeta_el_opt_out():
    guion = (REPO / "docker" / "entrypoint.sh").read_text(encoding="utf-8")
    guion = guion.replace("uv run ixforge upgrade", "echo MIGRA")
    guion = guion.replace("exec uv run ixforge", "echo ARRANCA")

    salida = subprocess.run(
        ["sh", "-s", "run"],
        input=guion,
        capture_output=True,
        text=True,
        env={**os.environ, "IXFORGE_AUTO_MIGRATE": "false"},
        check=False,
    ).stdout

    assert "MIGRA" not in salida
    assert "ARRANCA run" in salida
