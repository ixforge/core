"""El core escribe los logos y el portal los sirve, desde contenedores distintos

Los dos tienen que montar el mismo volumen en media: el core decide si hay logo
mirando su disco y el portal responde con el suyo. La suite no levanta
contenedores, asi que se verifica leyendo los compose
"""

from pathlib import Path

import pytest
import yaml

from ixforge.config import Settings

_DOCKER = Path(__file__).resolve().parent.parent / "docker"
_COMPOSES = ["docker-compose.yml", "docker-compose.dev.yml"]


def _destino_media() -> str:
    """Donde espera la app encontrar media dentro del contenedor

    media_root es relativo al cwd, y el WORKDIR de la imagen es /app
    """
    raiz = Settings.model_fields["media_root"].default
    return str(Path("/app") / raiz)


def _volumen_en(servicio: dict, destino: str) -> str | None:
    for v in servicio.get("volumes", []) or []:
        if isinstance(v, str):
            origen, _, resto = v.partition(":")
            if resto.split(":")[0] == destino:
                return origen
    return None


@pytest.mark.parametrize("archivo", _COMPOSES)
def test_core_y_portal_comparten_media(archivo):
    compose = yaml.safe_load((_DOCKER / archivo).read_text())
    servicios = compose["services"]
    destino = _destino_media()

    del_core = _volumen_en(servicios["core"], destino)
    del_portal = _volumen_en(servicios["portal"], destino)

    assert del_core is not None, f"{archivo}: el core no monta nada en {destino}"
    assert del_portal is not None, f"{archivo}: el portal no monta nada en {destino}"
    assert del_core == del_portal, (
        f"{archivo}: core monta {del_core} y portal {del_portal}, no ven lo mismo"
    )


@pytest.mark.parametrize("archivo", _COMPOSES)
def test_media_es_un_volumen_nombrado_que_sobrevive_al_rebuild(archivo):
    compose = yaml.safe_load((_DOCKER / archivo).read_text())
    origen = _volumen_en(compose["services"]["core"], _destino_media())

    # Un volumen nombrado aparece declarado arriba; una ruta del host empezaria
    # con . o /. Cualquiera de las dos sobrevive a recrear el contenedor, lo que
    # no sobrevive es no montar nada
    assert origen is not None
    es_ruta = origen.startswith((".", "/"))
    assert es_ruta or origen in (compose.get("volumes") or {}), (
        f"{archivo}: {origen} no esta declarado en volumes"
    )


def test_la_imagen_crea_media_antes_de_darsela_al_usuario():
    """Un volumen nombrado nuevo hereda el duenio del directorio de la imagen.
    Si la imagen no lo crea, nace de root y el core no puede escribir
    """
    dockerfile = (_DOCKER / "Dockerfile").read_text()
    linea_chown = next(
        (i for i, linea in enumerate(dockerfile.splitlines()) if "chown" in linea and "/app" in linea),
        None,
    )
    assert linea_chown is not None
    previas = "\n".join(dockerfile.splitlines()[: linea_chown + 1])
    assert "/app/media" in previas, "la imagen no crea /app/media antes del chown"
