"""Tests de la migracion que instala el set euro-ix en IXPs existentes.

La migracion lleva un snapshot literal de los templates a proposito: un cambio
futuro no debe cambiar lo que hizo esa revision. El riesgo de ese patron es que
el snapshot quede viejo mientras la migracion todavia no se publico, y entonces
instale una version con bugs ya corregidos en el codigo.
"""

import runpy
from pathlib import Path

import pytest

MIGRACION = (
    Path(__file__).parent.parent
    / "alembic"
    / "versions"
    / "9f2c7a1b4d3e_euroix_templates.py"
)


@pytest.fixture(scope="module")
def snapshot() -> list[dict[str, object]]:
    return runpy.run_path(str(MIGRACION))["EUROIX_TEMPLATE_SNAPSHOT"]


def test_snapshot_instala_los_once_templates(snapshot):
    from ixforge.services.default_templates import DEFAULT_TEMPLATES

    assert {t["filename"] for t in snapshot} == {
        t["filename"] for t in DEFAULT_TEMPLATES
    }


def test_snapshot_no_arrastra_el_bug_del_strip_de_communities(snapshot):
    """Regresion: el snapshot se genero antes de arreglar el filtro de export y
    quedo instalando la version que dejaba pasar las communities estandar del
    IXP hacia el miembro

    Este test verifica la propiedad, no los bytes: cuando la migracion se
    publique el snapshot se congela, pero la propiedad tiene que seguir valiendo
    """
    peer = next(t for t in snapshot if t["filename"] == "protocols/bgp_peer.j2")

    assert "bgp_large_community.delete" in peer["content"]
    assert "bgp_community.delete" in peer["content"]


def test_snapshot_emite_rs_client(snapshot):
    """Sin rs client el route server mete su ASN en el AS path: la migracion
    instalaria algo que no es un route server
    """
    rs_client = next(t for t in snapshot if t["filename"] == "protocols/rs_client.j2")

    assert "rs client;" in rs_client["content"]


def test_snapshot_no_trae_los_templates_huerfanos(snapshot):
    """static.j2 y filters/communities.j2 no los incluia nadie y se borraron"""
    nombres = {t["filename"] for t in snapshot}

    assert "protocols/static.j2" not in nombres
    assert "filters/communities.j2" not in nombres
