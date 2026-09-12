"""Consulta de metricas de interfaz a VictoriaMetrics.

El collector escribe las series y VictoriaMetrics escucha solo en localhost del
Core, asi que ningun consumidor externo puede alcanzarla. El Core las expone.

Todo lo que entra a una consulta PromQL se valida antes: un id sin validar se
inyecta en la expresion y devuelve series de otro miembro, o peor
"""

import uuid
from typing import Any

import httpx
import structlog

from ixforge.config import get_settings

logger = structlog.get_logger()

# Rangos permitidos. Es lista blanca y no validacion de formato: el valor entra
# a la consulta y un patron laxo deja pasar expresiones
RANGOS: dict[str, tuple[str, str]] = {
    "1h": ("1h", "60s"),
    "6h": ("6h", "300s"),
    "24h": ("24h", "900s"),
    "7d": ("7d", "3600s"),
}

# Las ICMP se miden por IP de miembro, no por puerto
METRICAS_ICMP: dict[str, str] = {
    "rtt": "ixforge_icmp_rtt_seconds",
    "rtt_min": "ixforge_icmp_rtt_min_seconds",
    "rtt_max": "ixforge_icmp_rtt_max_seconds",
    "packet_loss": "ixforge_icmp_packet_loss_ratio",
}

METRICAS = (
    "ixforge_interface_traffic_in_bps",
    "ixforge_interface_traffic_out_bps",
    "ixforge_interface_packets_in_pps",
    "ixforge_interface_packets_out_pps",
    "ixforge_interface_errors_in",
    "ixforge_interface_errors_out",
    "ixforge_interface_oper_status",
)


async def consultar_vm(consulta: str) -> dict[str, Any]:
    """Query instantanea. Separada para poder sustituirla en tests"""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.victoriametrics_timeout) as cliente:
        resp = await cliente.get(
            f"{settings.victoriametrics_url.rstrip('/')}/api/v1/query",
            params={"query": consulta},
        )
        resp.raise_for_status()
        datos: dict[str, Any] = resp.json()
        return datos


async def consultar_vm_rango(consulta: str, rango: str, paso: str) -> dict[str, Any]:
    """Query de rango, para graficos"""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.victoriametrics_timeout) as cliente:
        resp = await cliente.get(
            f"{settings.victoriametrics_url.rstrip('/')}/api/v1/query_range",
            params={"query": consulta, "start": f"-{rango}", "end": "now", "step": paso},
        )
        resp.raise_for_status()
        datos: dict[str, Any] = resp.json()
        return datos


def _selector(connection_id: uuid.UUID | None, member_id: uuid.UUID | None) -> str:
    """Filtro de etiquetas. Los ids llegan ya validados como UUID por FastAPI,
    que es lo que impide inyectar en la expresion"""
    partes = [f'__name__=~"{"|".join(METRICAS)}"']
    if connection_id is not None:
        partes.append(f'port_id="{connection_id}"')
    if member_id is not None:
        partes.append(f'member_id="{member_id}"')
    return "{" + ",".join(partes) + "}"


def _agrupar(resultados: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """De una lista plana de series a un dict por conexion"""
    por_conexion: dict[str, dict[str, Any]] = {}
    for serie in resultados:
        etiquetas = serie.get("metric", {})
        cid = etiquetas.get("port_id") or ""
        if not cid:
            continue
        valor = serie.get("value", [None, None])[1]
        entrada = por_conexion.setdefault(
            cid,
            {
                "connection_id": cid,
                "member_id": etiquetas.get("member_id") or None,
                "ifname": etiquetas.get("ifname") or None,
                "switch_name": etiquetas.get("switch_name") or None,
                "oper_status": "unknown",
            },
        )
        nombre = etiquetas.get("__name__", "")
        if nombre == "ixforge_interface_oper_status":
            entrada["oper_status"] = "up" if str(valor) == "1" else "down"
        elif nombre.startswith("ixforge_interface_"):
            entrada[nombre.removeprefix("ixforge_interface_")] = float(valor or 0)
    return por_conexion


async def estado_de_interfaces(
    connection_id: uuid.UUID | None = None,
    member_id: uuid.UUID | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Valores actuales por conexion.

    Devuelve (items, disponible). Una metrica caida no puede tumbar a quien la
    consulta: se loguea y se responde vacio con disponible en false
    """
    try:
        crudo = await consultar_vm(_selector(connection_id, member_id))
    except Exception as e:
        logger.warning("victoriametrics no responde", error=str(e))
        return [], False

    items = list(_agrupar(crudo.get("data", {}).get("result", [])).values())
    items.sort(key=lambda x: (x.get("switch_name") or "", x.get("ifname") or ""))
    return items, True


async def series_de_interfaces(
    rango: str,
    connection_id: uuid.UUID | None = None,
    member_id: uuid.UUID | None = None,
    metrica: str = "ixforge_interface_traffic_in_bps",
) -> tuple[list[dict[str, Any]], bool]:
    """Serie temporal de una metrica, para graficos"""
    if rango not in RANGOS:
        return [], True
    ventana, paso = RANGOS[rango]

    partes = [f'__name__="{metrica}"']
    if connection_id is not None:
        partes.append(f'port_id="{connection_id}"')
    if member_id is not None:
        partes.append(f'member_id="{member_id}"')
    consulta = "{" + ",".join(partes) + "}"

    try:
        crudo = await consultar_vm_rango(consulta, ventana, paso)
    except Exception as e:
        logger.warning("victoriametrics no responde", error=str(e))
        return [], False

    series = []
    for serie in crudo.get("data", {}).get("result", []):
        etiquetas = serie.get("metric", {})
        series.append({
            "connection_id": etiquetas.get("port_id") or None,
            "member_id": etiquetas.get("member_id") or None,
            "ifname": etiquetas.get("ifname") or None,
            "points": [
                {"timestamp": int(t), "value": float(v)}
                for t, v in serie.get("values", [])
            ],
        })
    return series, True


async def series_icmp(
    rango: str,
    metrica: str,
    member_id: uuid.UUID | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Latencia y perdida de paquetes por IP de miembro"""
    if rango not in RANGOS or metrica not in METRICAS_ICMP:
        return [], True
    ventana, paso = RANGOS[rango]

    partes = [f'__name__="{METRICAS_ICMP[metrica]}"']
    if member_id is not None:
        partes.append(f'member_id="{member_id}"')
    consulta = "{" + ",".join(partes) + "}"

    try:
        crudo = await consultar_vm_rango(consulta, ventana, paso)
    except Exception as e:
        logger.warning("victoriametrics no responde", error=str(e))
        return [], False

    series = []
    for serie in crudo.get("data", {}).get("result", []):
        etiquetas = serie.get("metric", {})
        version = etiquetas.get("ip_version")
        series.append({
            "member_id": etiquetas.get("member_id") or None,
            "ip": etiquetas.get("ip") or None,
            "ip_version": int(version) if version else None,
            "points": [
                {"timestamp": int(t), "value": float(v)}
                for t, v in serie.get("values", [])
            ],
        })
    return series, True


# Solo las interfaces que mapean a una conexion de miembro. El switch reporta
# ademas el Eth-Trunk que envuelve a cada puerto fisico, asi que sumar todo
# contaria a cada miembro dos veces
SELECTOR_MIEMBROS = 'member_id!=""'


async def series_agregadas(rango: str) -> tuple[list[Any], list[Any], bool]:
    """Trafico total del IXP, entrada y salida"""
    if rango not in RANGOS:
        return [], [], True
    ventana, paso = RANGOS[rango]

    salidas = []
    for metrica in ("ixforge_interface_traffic_in_bps", "ixforge_interface_traffic_out_bps"):
        consulta = f'sum({metrica}{{{SELECTOR_MIEMBROS}}})'
        try:
            crudo = await consultar_vm_rango(consulta, ventana, paso)
        except Exception as e:
            logger.warning("victoriametrics no responde", error=str(e))
            return [], [], False

        puntos = []
        for serie in crudo.get("data", {}).get("result", []):
            for t, v in serie.get("values", []):
                puntos.append({"timestamp": int(t), "value": float(v)})
        salidas.append(puntos)

    return salidas[0], salidas[1], True


async def pico_agregado(rango: str) -> tuple[float | None, float | None, bool]:
    """Pico de trafico en la ventana, entrada y salida"""
    if rango not in RANGOS:
        return None, None, True
    ventana, _ = RANGOS[rango]

    picos: list[float | None] = []
    for metrica in ("ixforge_interface_traffic_in_bps", "ixforge_interface_traffic_out_bps"):
        consulta = f'max_over_time(sum({metrica}{{{SELECTOR_MIEMBROS}}})[{ventana}:])'
        try:
            crudo = await consultar_vm(consulta)
        except Exception as e:
            logger.warning("victoriametrics no responde", error=str(e))
            return None, None, False

        resultado = crudo.get("data", {}).get("result", [])
        picos.append(float(resultado[0]["value"][1]) if resultado else None)

    return picos[0], picos[1], True
