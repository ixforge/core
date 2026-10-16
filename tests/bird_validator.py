"""Validacion de configs BIRD con bird -p en docker.

En desarrollo los tests se saltean si docker o la imagen no estan disponibles.
Con IXFORGE_REQUIRE_BIRD=1 la falta del validador aborta la suite. Construir la imagen:

    docker build -t ixforge-bird-validator:2 docker/bird-validator/
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

BIRD_IMAGE = "ixforge-bird-validator:2"


def bird_available() -> bool:
    """Comprueba el validador y exige su presencia cuando CI lo requiere"""
    available = False
    if shutil.which("docker") is not None:
        result = subprocess.run(
            ["docker", "image", "inspect", BIRD_IMAGE],
            capture_output=True,
            check=False,
        )
        available = result.returncode == 0
    if not available and os.environ.get("IXFORGE_REQUIRE_BIRD") == "1":
        raise RuntimeError(
            f"IXFORGE_REQUIRE_BIRD=1 requiere Docker accesible y la imagen {BIRD_IMAGE}; "
            f"construir con docker build -t {BIRD_IMAGE} docker/bird-validator/"
        )
    return available


def assert_bird_parses(config: str) -> None:
    """Corre bird -p sobre el config y falla con la salida real si lo rechaza

    El mensaje incluye el config numerado porque el error de BIRD trae linea y
    columna, y sin el texto al lado no sirven de nada
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        conf_path = Path(tmpdir) / "bird.conf"
        conf_path.write_text(config, encoding="utf-8")
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{tmpdir}:/conf:ro",
                BIRD_IMAGE,
                "-p",
                "-c",
                "/conf/bird.conf",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode != 0:
        numbered = "\n".join(
            f"{i:4d}  {line}" for i, line in enumerate(config.splitlines(), start=1)
        )
        raise AssertionError(
            f"bird -p rechazo el config:\n{result.stdout}{result.stderr}\n\n{numbered}"
        )
