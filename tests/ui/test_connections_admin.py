"""Pantalla /admin/connections: listado y edicion.

La edicion no existia: se podia crear una conexion y cambiarle el estado, pero
corregirle el puerto o la velocidad obligaba a borrarla y rehacerla, con el
trunk pasando por disabled. El PATCH de la API ya estaba, faltaba la UI
"""

import uuid
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from ixforge.ui.api_client import APIError
from ixforge.ui.app import create_ui_app

MIEMBRO = {
    "id": str(uuid.uuid4()), "name": "Acme Networks", "short_name": "ACME",
    "asn": 64512, "state": "active",
}
TRUNK = {
    "id": str(uuid.uuid4()), "member_id": MIEMBRO["id"], "name": "ae0",
    "state": "active",
}
SWITCH = {"id": str(uuid.uuid4()), "name": "sw-peering-1"}
CONEXION = {
    "id": str(uuid.uuid4()),
    "trunk_id": TRUNK["id"],
    "switch_id": SWITCH["id"],
    "name": "Eth-Trunk2",
    "type": "physical",
    "state": "active",
    "speed": 1000,
    "notes": "alias RIPE_K_Root",
    "extra_data": None,
    "created_at": "2026-01-15T00:00:00",
    "updated_at": "2026-01-15T00:00:00",
}


@pytest.fixture
def app():
    app = create_ui_app()
    app.state.api.login = AsyncMock(return_value="test-jwt")
    app.state.api.get = AsyncMock(
        return_value={"id": "abc", "role": "admin", "member_id": None})
    return app


@pytest.fixture
def authed_client(app):
    client = TestClient(app, base_url="https://testserver")
    client.post("/login", data={"email": "a@b.com", "password": "p"},
                follow_redirects=False)
    return client


def _get_falso(path, token, params=None):
    if path == "/api/v1/members":
        return {"items": [MIEMBRO], "next_cursor": None, "has_more": False}
    if path == "/api/v1/trunks":
        return {"items": [TRUNK], "next_cursor": None, "has_more": False}
    if path == "/api/v1/switches":
        return {"items": [SWITCH], "next_cursor": None, "has_more": False}
    if path == f"/api/v1/connections/{CONEXION['id']}":
        return dict(CONEXION)
    return {}


class TestEdicionDeConexion:
    def test_el_formulario_trae_los_valores_actuales(self, authed_client, app):
        app.state.api.get = AsyncMock(side_effect=_get_falso)
        resp = authed_client.get(f"/admin/connections/{CONEXION['id']}/edit")
        assert resp.status_code == 200
        assert "Eth-Trunk2" in resp.text
        assert "alias RIPE_K_Root" in resp.text
        # la velocidad actual viene seleccionada, no el default de 10G
        assert 'value="1000" selected' in resp.text
        # y el form apunta a la edicion, no a la creacion
        assert f"/admin/connections/{CONEXION['id']}/edit" in resp.text

    def test_guardar_manda_patch_y_redirige(self, authed_client, app):
        app.state.api.get = AsyncMock(side_effect=_get_falso)
        app.state.api.patch = AsyncMock(return_value={**CONEXION, "name": "10GE1/0/5"})
        resp = authed_client.post(
            f"/admin/connections/{CONEXION['id']}/edit",
            data={"puerto": "10GE1/0/5", "type": "physical", "speed": "10000",
                  "switch_id": SWITCH["id"], "notes": "puerto del hipervisor"},
            follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/admin/connections"
        ruta, _token = app.state.api.patch.call_args[0][:2]
        assert ruta == f"/api/v1/connections/{CONEXION['id']}"
        enviado = app.state.api.patch.call_args[1]["json"]
        assert enviado["name"] == "10GE1/0/5"
        assert enviado["speed"] == 10000
        assert enviado["switch_id"] == SWITCH["id"]
        assert enviado["notes"] == "puerto del hipervisor"
        # el trunk no se puede mover de miembro por esta via
        assert "trunk_id" not in enviado

    def test_notas_vacias_se_mandan_como_null(self, authed_client, app):
        app.state.api.get = AsyncMock(side_effect=_get_falso)
        app.state.api.patch = AsyncMock(return_value=dict(CONEXION))
        authed_client.post(
            f"/admin/connections/{CONEXION['id']}/edit",
            data={"puerto": "Eth-Trunk2", "type": "physical", "speed": "1000",
                  "switch_id": SWITCH["id"], "notes": "   "},
            follow_redirects=False)
        assert app.state.api.patch.call_args[1]["json"]["notes"] is None

    def test_error_de_validacion_vuelve_al_formulario(self, authed_client, app):
        app.state.api.get = AsyncMock(side_effect=_get_falso)
        app.state.api.patch = AsyncMock(
            side_effect=APIError(422, {"error": {"message": "speed invalido"}}))
        resp = authed_client.post(
            f"/admin/connections/{CONEXION['id']}/edit",
            data={"puerto": "Eth-Trunk2", "type": "physical", "speed": "0",
                  "switch_id": SWITCH["id"], "notes": ""},
            follow_redirects=False)
        assert resp.status_code == 200
        assert "speed invalido" in resp.text

    def test_requiere_autenticacion(self, app):
        cliente = TestClient(app, base_url="https://testserver")
        resp = cliente.get(f"/admin/connections/{CONEXION['id']}/edit",
                           follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["location"]


class TestListadoDeConexiones:
    def test_el_listado_ofrece_editar(self, authed_client, app):
        def get_listado(path, token, params=None):
            if path == "/api/v1/connections":
                return {"items": [CONEXION], "next_cursor": None, "has_more": False}
            return _get_falso(path, token, params)

        app.state.api.get = AsyncMock(side_effect=get_listado)
        resp = authed_client.get("/admin/connections")
        assert resp.status_code == 200
        assert f"/admin/connections/{CONEXION['id']}/edit" in resp.text
