"""La migracion de communities acepta cabeceras descriptivas anteriores"""

import runpy
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text

MIGRATION = runpy.run_path(
    str(
        Path(__file__).parent.parent
        / "alembic/versions/f1d3a86b40c2_communities_pit_y_rpki_sin_modo.py"
    )
)


@pytest.mark.parametrize("desde,hasta", [(0, 1), (1, 0)])
@pytest.mark.parametrize("cabecera_anterior", [False, True])
async def test_migracion_actualiza_solo_templates_sin_cambios_funcionales(
    db_session,
    desde,
    hasta,
    cabecera_anterior,
):
    original, destino = (
        MIGRATION["CAMBIOS"]["functions/communities.j2"][i] for i in (desde, hasta)
    )
    if cabecera_anterior:
        original = (
            "# Communities del esquema anterior\n"
            "# https://example.org/communities\n\n" + original.partition("\n\n")[2]
        )
    personalizado = original + "\ndefine CUSTOM_COMMUNITY = (65000, 1101, 99);\n"
    await db_session.execute(
        text(
            "CREATE TEMP TABLE route_server_templates "
            "(id integer, filename text, content text, updated_at timestamptz) "
            "ON COMMIT DROP"
        )
    )
    for ident, content in [(1, original), (2, personalizado)]:
        await db_session.execute(
            text(
                "INSERT INTO route_server_templates (id, filename, content) "
                "VALUES (:id, 'functions/communities.j2', :content)"
            ),
            {"id": ident, "content": content},
        )

    connection = await db_session.connection()

    def aplicar(sync_connection):
        with patch.object(MIGRATION["op"], "get_bind", return_value=sync_connection):
            MIGRATION["_aplicar"](desde, hasta)

    await connection.run_sync(aplicar)
    contents = dict(
        (
            await db_session.execute(
                text("SELECT id, content FROM route_server_templates ORDER BY id")
            )
        ).all()
    )
    assert contents == {1: destino, 2: personalizado}
