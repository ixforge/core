"""API de metricas de interfaz.

Los datos los escribe el collector en VictoriaMetrics, que escucha solo en
localhost del Core. Ningun consumidor externo puede alcanzarla, asi que el Core
tiene que exponerlas: es la unica via, no solo la prolija
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest


def _respuesta_vm(resultados: list[dict]) -> dict:
    return {"status": "success", "data": {"resultType": "vector", "result": resultados}}


def _serie(metrica: str, valor: str, **etiquetas) -> dict:
    return {"metric": {"__name__": metrica, **etiquetas}, "value": [1757000000, valor]}


class TestMetricasDeInterfaz:
    async def test_devuelve_el_estado_actual_por_conexion(
        self, client, auth_headers, db_session, ixp
    ):
        cid = str(uuid.uuid4())
        vm = _respuesta_vm([
            _serie("ixforge_interface_traffic_in_bps", "1500000", port_id=cid),
            _serie("ixforge_interface_traffic_out_bps", "2500000", port_id=cid),
            _serie("ixforge_interface_oper_status", "1", port_id=cid),
        ])
        with patch("ixforge.services.metricas.consultar_vm", new=AsyncMock(return_value=vm)):
            resp = await client.get("/api/v1/metrics/interfaces", headers=auth_headers)

        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["connection_id"] == cid
        assert item["traffic_in_bps"] == 1500000
        assert item["traffic_out_bps"] == 2500000
        assert item["oper_status"] == "up"

    async def test_filtra_por_conexion(self, client, auth_headers, ixp):
        cid = str(uuid.uuid4())
        capturado = {}

        async def falsa(consulta, **kw):
            capturado["consulta"] = consulta
            return _respuesta_vm([])

        with patch("ixforge.services.metricas.consultar_vm", new=falsa):
            resp = await client.get(
                f"/api/v1/metrics/interfaces?connection_id={cid}", headers=auth_headers
            )

        assert resp.status_code == 200
        assert cid in capturado["consulta"]

    async def test_rechaza_un_id_que_no_es_uuid(self, client, auth_headers, ixp):
        """El id entra a una consulta PromQL: si no se valida, se inyecta"""
        resp = await client.get(
            '/api/v1/metrics/interfaces?connection_id=x"} or up{', headers=auth_headers
        )
        assert resp.status_code == 422

    async def test_oper_status_down_cuando_vale_cero(self, client, auth_headers, ixp):
        cid = str(uuid.uuid4())
        vm = _respuesta_vm([_serie("ixforge_interface_oper_status", "0", port_id=cid)])
        with patch("ixforge.services.metricas.consultar_vm", new=AsyncMock(return_value=vm)):
            resp = await client.get("/api/v1/metrics/interfaces", headers=auth_headers)

        assert resp.json()["items"][0]["oper_status"] == "down"

    async def test_si_victoriametrics_no_responde_devuelve_vacio(
        self, client, auth_headers, ixp
    ):
        """Una metrica caida no puede tumbar a quien la consulta"""
        with patch(
            "ixforge.services.metricas.consultar_vm",
            new=AsyncMock(side_effect=TimeoutError("sin respuesta")),
        ):
            resp = await client.get("/api/v1/metrics/interfaces", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["items"] == []
        assert resp.json()["disponible"] is False

    async def test_requiere_autenticacion(self, client, ixp):
        resp = await client.get("/api/v1/metrics/interfaces")
        assert resp.status_code == 401

    async def test_serie_temporal_para_graficos(self, client, auth_headers, ixp):
        cid = str(uuid.uuid4())
        vm = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [{
                    "metric": {"__name__": "ixforge_interface_traffic_in_bps", "port_id": cid},
                    "values": [[1757000000, "100"], [1757000060, "200"]],
                }],
            },
        }
        with patch("ixforge.services.metricas.consultar_vm_rango", new=AsyncMock(return_value=vm)):
            resp = await client.get(
                f"/api/v1/metrics/interfaces/series?connection_id={cid}&range=1h",
                headers=auth_headers,
            )

        assert resp.status_code == 200
        serie = resp.json()["series"][0]
        assert serie["connection_id"] == cid
        assert serie["points"][0]["value"] == 100.0

    @pytest.mark.parametrize("rango", ["1h", "6h", "24h", "7d"])
    async def test_acepta_los_rangos_previstos(self, client, auth_headers, ixp, rango):
        with patch(
            "ixforge.services.metricas.consultar_vm_rango",
            new=AsyncMock(return_value={"status": "success", "data": {"result": []}}),
        ):
            resp = await client.get(
                f"/api/v1/metrics/interfaces/series?range={rango}", headers=auth_headers
            )
        assert resp.status_code == 200

    async def test_rechaza_un_rango_inventado(self, client, auth_headers, ixp):
        """El rango va a la consulta: solo se aceptan valores de una lista"""
        resp = await client.get(
            "/api/v1/metrics/interfaces/series?range=1h)+or+up", headers=auth_headers
        )
        assert resp.status_code == 422


def test_metrics_es_un_recurso_con_scope_propio():
    """El chequeo de scopes deriva el recurso del path, asi que sin metrics en
    la lista el scope metrics:read no existe y la key no se puede otorgar"""
    from ixforge.schemas.auth import MANAGEMENT_RESOURCES, VALID_API_KEY_SCOPES

    assert "metrics" in MANAGEMENT_RESOURCES
    assert "metrics:read" in VALID_API_KEY_SCOPES
