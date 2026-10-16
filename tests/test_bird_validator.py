"""CI no puede omitir la validacion BIRD si faltan sus requisitos"""

import subprocess

import pytest

from tests import bird_validator


@pytest.mark.parametrize("required", [False, True])
def test_available_image_allows_validation(monkeypatch, required):
    monkeypatch.setenv("IXFORGE_REQUIRE_BIRD", "1" if required else "0")
    monkeypatch.setattr(bird_validator.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(
        bird_validator.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0),
    )

    assert bird_validator.bird_available() is True


@pytest.mark.parametrize("docker_exists", [False, True])
def test_optional_validation_can_skip_missing_dependency(monkeypatch, docker_exists):
    monkeypatch.delenv("IXFORGE_REQUIRE_BIRD", raising=False)
    monkeypatch.setattr(
        bird_validator.shutil, "which", lambda _: "/usr/bin/docker" if docker_exists else None
    )
    monkeypatch.setattr(
        bird_validator.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1),
    )

    assert bird_validator.bird_available() is False


@pytest.mark.parametrize("docker_exists", [False, True])
def test_required_validation_fails_when_dependency_is_missing(monkeypatch, docker_exists):
    monkeypatch.setenv("IXFORGE_REQUIRE_BIRD", "1")
    monkeypatch.setattr(
        bird_validator.shutil, "which", lambda _: "/usr/bin/docker" if docker_exists else None
    )
    monkeypatch.setattr(
        bird_validator.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1),
    )

    with pytest.raises(RuntimeError, match="IXFORGE_REQUIRE_BIRD"):
        bird_validator.bird_available()
