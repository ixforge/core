"""Prueba Core -> Agent -> BIRD con procesos reales y una base desechable

Requiere Core iniciado sobre una base migrada SIN setup, Docker con la imagen
del validador y IXFORGE_AGENT_BINARY apuntando al binario compilado del Agent.
Ejecutar explicitamente: uv run pytest tests/pipeline_runner.py -v -s
"""

import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import pytest

from tests.bird_validator import BIRD_IMAGE, bird_available


def _request(client, method, path, data=None):
    response = client.request(method, path, json=data)
    response.raise_for_status()
    return response.json()


def _wait_for(description, check, processes=(), timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for process in processes:
            assert process.poll() is None, f"Proceso terminado esperando {description}"
        result = check()
        if result:
            return result
        time.sleep(0.5)
    pytest.fail(f"Timeout esperando {description}")


def _stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_core_agent_bird_rejects_invalid_config_and_recovers(tmp_path):
    """Una config rechazada no reemplaza la activa y una posterior valida converge"""
    agent_binary = Path(os.environ["IXFORGE_AGENT_BINARY"]).resolve(strict=True)
    assert bird_available(), "Construir la imagen BIRD antes de ejecutar el pipeline"
    base_url = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8000/api/v1")
    container = f"ixforge-pipeline-{uuid.uuid4().hex}"
    config_path = tmp_path / "bird.conf"
    socket_path = tmp_path / "bird.ctl"
    agent_config = tmp_path / "agent.toml"
    validator = tmp_path / "validate-bird"
    password = uuid.uuid4().hex
    processes = []

    with httpx.Client(base_url=base_url + "/", timeout=5, trust_env=False) as client:
        assert not _request(client, "GET", "setup/status")["configured"], (
            "El pipeline requiere una base desechable sin setup; no modifica IXPs existentes"
        )
        _request(
            client,
            "POST",
            "setup",
            {
                "ixp": {
                    "name": "Pipeline IXP",
                    "short_name": "PIPE",
                    "asn": 64500,
                    "country": "CL",
                    "city": "Santiago",
                },
                "admin": {
                    "full_name": "Pipeline",
                    "email": "pipeline@example.com",
                    "password": password,
                },
            },
        )
        token = _request(
            client,
            "POST",
            "auth/login",
            {
                "email": "pipeline@example.com",
                "password": password,
            },
        )["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        rs = _request(
            client,
            "POST",
            "route-servers",
            {
                "name": "pipeline-rs",
                "ip_v4": "192.0.2.1",
                "ip_v6": "2001:db8::1",
            },
        )
        route = f"route-servers/{rs['id']}"
        key = _request(client, "POST", f"{route}/api-keys", {"name": "pipeline"})
        template = next(
            t for t in _request(client, "GET", "rs-templates") if t["filename"] == "bird.conf.j2"
        )
        template_route = f"rs-templates/{template['id']}"
        initial = _request(client, "POST", f"{route}/config/generate")

        config_path.write_text("router id 192.0.2.254;\nprotocol device {}\n")
        validator.write_text(f'#!/bin/sh\nexec docker exec {container} bird "$@"\n')
        validator.chmod(0o700)
        agent_config.write_text(
            "[core]\n"
            f"url = {json.dumps(base_url.removesuffix('/api/v1'))}\n"
            f"api_key = {json.dumps(key['raw_key'])}\n"
            f"route_server_id = {json.dumps(rs['id'])}\n"
            "poll_interval_secs = 1\n"
            "[bird]\n"
            f"socket_path = {json.dumps(str(socket_path))}\n"
            f"config_path = {json.dumps(str(config_path))}\n"
            f"bird_binary = {json.dumps(str(validator))}\n"
            "socket_timeout_secs = 5\n"
            '[metrics]\nlisten = "127.0.0.1:0"\n'
            '[logging]\nlevel = "info"\nformat = "json"\n'
        )
        agent_config.chmod(0o600)

        def status():
            return subprocess.run(
                ["docker", "exec", container, "birdc", "-s", str(socket_path), "show", "status"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout

        def applied(version):
            current = _request(client, "GET", f"{route}/config/{version['id']}")
            return current["applied_at"] and current["config_hash"] == version["config_hash"]

        with (
            (tmp_path / "bird.log").open("w") as bird_log,
            (tmp_path / "agent.log").open("w") as agent_log,
        ):
            try:
                bird = subprocess.Popen(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--name",
                        container,
                        "--network",
                        "none",
                        "--user",
                        f"{os.getuid()}:{os.getgid()}",
                        "-v",
                        f"{tmp_path}:{tmp_path}",
                        BIRD_IMAGE,
                        "-f",
                        "-c",
                        str(config_path),
                        "-s",
                        str(socket_path),
                        "-P",
                        str(tmp_path / "bird.pid"),
                    ],
                    stdout=bird_log,
                    stderr=subprocess.STDOUT,
                )
                processes.append(bird)
                _wait_for("socket BIRD", socket_path.exists, processes)
                assert "192.0.2.254" in status()
                agent = subprocess.Popen(
                    [str(agent_binary), "--config", str(agent_config)],
                    stdout=agent_log,
                    stderr=subprocess.STDOUT,
                )
                processes.append(agent)
                _wait_for("primera configuracion aplicada", lambda: applied(initial), processes)
                assert config_path.read_text() == initial["content"]
                assert "192.0.2.1" in status()
                _wait_for(
                    "heartbeat",
                    lambda: _request(client, "GET", route)["last_heartbeat_at"],
                    processes,
                )

                _request(
                    client,
                    "PATCH",
                    template_route,
                    {
                        "content": template["content"] + "\ninvalid_bird_directive;\n",
                    },
                )
                invalid = _request(client, "POST", f"{route}/config/generate")
                _wait_for(
                    "rechazo reportado al Core",
                    lambda: _request(client, "GET", f"{route}/config/{invalid['id']}")[
                        "apply_error"
                    ],
                    processes,
                )
                assert not applied(invalid)
                assert config_path.read_text() == initial["content"]
                assert "192.0.2.1" in status()

                _request(client, "PATCH", template_route, {"content": template["content"]})
                _request(client, "PATCH", route, {"ip_v4": "192.0.2.2"})
                recovered = _request(client, "POST", f"{route}/config/generate")
                _wait_for("recuperacion", lambda: applied(recovered), processes)
                assert config_path.read_text() == recovered["content"]
                assert "192.0.2.2" in status()
            finally:
                for process in reversed(processes):
                    _stop(process)
                subprocess.run(
                    ["docker", "rm", "-f", container],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                agent_config.unlink(missing_ok=True)
                for log in ("bird.log", "agent.log"):
                    print(f"\n--- {log} ---\n{(tmp_path / log).read_text()}")
