"""Metricas de interfaz por conexion y por miembro.

VictoriaMetrics escucha solo en localhost del Core, asi que este router es la
unica via para un consumidor externo, incluido el sitio publico
"""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query

from ixforge.api.deps import CurrentUser
from ixforge.services import metricas

metricas_router = APIRouter(prefix="/metrics", tags=["metrics"])


@metricas_router.get("/interfaces")
async def estado_de_interfaces(
    _user: CurrentUser,
    connection_id: uuid.UUID | None = Query(default=None),
    member_id: uuid.UUID | None = Query(default=None),
) -> dict[str, Any]:
    """Valores actuales por conexion: trafico, paquetes, errores y estado"""
    items, disponible = await metricas.estado_de_interfaces(connection_id, member_id)
    return {"items": items, "disponible": disponible}


@metricas_router.get("/interfaces/series")
async def series_de_interfaces(
    _user: CurrentUser,
    connection_id: uuid.UUID | None = Query(default=None),
    member_id: uuid.UUID | None = Query(default=None),
    # lista blanca y no patron: el valor entra a la consulta
    range: Annotated[Literal["1h", "6h", "24h", "7d"], Query()] = "1h",
    metric: Annotated[
        Literal[
            "ixforge_interface_traffic_in_bps",
            "ixforge_interface_traffic_out_bps",
            "ixforge_interface_packets_in_pps",
            "ixforge_interface_packets_out_pps",
        ],
        Query(),
    ] = "ixforge_interface_traffic_in_bps",
) -> dict[str, Any]:
    """Serie temporal de una metrica, para graficos"""
    series, disponible = await metricas.series_de_interfaces(
        range, connection_id, member_id, metric
    )
    return {"series": series, "disponible": disponible}


@metricas_router.get("/icmp/series")
async def series_icmp(
    _user: CurrentUser,
    member_id: uuid.UUID | None = Query(default=None),
    range: Annotated[Literal["1h", "6h", "24h", "7d"], Query()] = "1h",
    metric: Annotated[
        Literal["rtt", "rtt_min", "rtt_max", "packet_loss"], Query()
    ] = "rtt",
) -> dict[str, Any]:
    """Latencia y perdida de paquetes por IP de miembro"""
    series, disponible = await metricas.series_icmp(range, metric, member_id)
    return {"series": series, "disponible": disponible}


@metricas_router.get("/aggregate/series")
async def series_agregadas(
    _user: CurrentUser,
    range: Annotated[Literal["1h", "6h", "24h", "7d"], Query()] = "1h",
) -> dict[str, Any]:
    """Trafico total del IXP en el tiempo"""
    entrada, salida, disponible = await metricas.series_agregadas(range)
    return {"entrada": entrada, "salida": salida, "disponible": disponible}


@metricas_router.get("/aggregate/peak")
async def pico_agregado(
    _user: CurrentUser,
    range: Annotated[Literal["1h", "6h", "24h", "7d"], Query()] = "24h",
) -> dict[str, Any]:
    """Pico de trafico del IXP en la ventana"""
    entrada, salida, disponible = await metricas.pico_agregado(range)
    return {"entrada": entrada, "salida": salida, "disponible": disponible}
