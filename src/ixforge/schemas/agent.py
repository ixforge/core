"""Agent communication schemas."""

import ipaddress
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class AgentConfigResponse(BaseModel):
    """Response for agent config polling."""

    config_hash: str
    content: str
    generated_at: datetime

    model_config = {"from_attributes": True}


class BGPSessionState(BaseModel):
    """Single BGP session state reported by the agent."""

    peer_ip: str
    oper_state: str = Field(pattern=r"^(up|down|unknown)$")
    af: int
    # Ausentes cuando la sesion no esta establecida, y ausente no es cero. El
    # tope es el maximo de un u32, que es lo que el agente puede mandar
    prefixes_imported: int | None = Field(default=None, ge=0, le=4294967295)
    prefixes_exported: int | None = Field(default=None, ge=0, le=4294967295)


class AgentStatusReport(BaseModel):
    """Agent bulk BGP session status report."""

    sessions: list[BGPSessionState] = Field(max_length=10000)


class ReportedPrefix(BaseModel):
    """Un prefijo que el peer anuncia, tal como el agente lo leyo de BIRD"""

    prefix: str = Field(min_length=1, max_length=43)
    as_path: list[int] = Field(default_factory=list, max_length=256)

    @field_validator("prefix")
    @classmethod
    def validar_prefijo(cls, v: str) -> str:
        """Tiene que ser una red de verdad: entra a la base y sale al sitio"""
        try:
            ipaddress.ip_network(v, strict=True)
        except ValueError as exc:
            raise ValueError(f"Prefijo invalido: {v}") from exc
        return v

    @field_validator("as_path")
    @classmethod
    def validar_as_path(cls, v: list[int]) -> list[int]:
        for asn in v:
            if not (1 <= asn <= 4294967295):
                raise ValueError(f"ASN fuera de rango en el AS path: {asn}")
        return v


class SessionPrefixes(BaseModel):
    peer_ip: str
    af: int
    # El tope del agente es 1000 por sesion. Aca va mas alto para que un cambio
    # de ese lado no rebote como 422, pero acotado: sin limite un reporte
    # manipulado seria una escritura sin fondo
    prefixes: list[ReportedPrefix] = Field(max_length=10000)


class AgentPrefixReport(BaseModel):
    """Prefijos por sesion. Va aparte del reporte de estado porque tiene su
    propio ciclo, mas lento
    """

    sessions: list[SessionPrefixes] = Field(max_length=1000)


class AgentPrefixReportResponse(BaseModel):
    sessions_updated: int
    prefixes_added: int
    prefixes_removed: int


class AgentStatusResponse(BaseModel):
    """Response after processing agent status report."""

    updated: int
    unchanged: int
    not_found: int


class BirdInstanceStatus(BaseModel):
    """Status of a single BIRD instance."""

    name: str
    running: bool
    uptime_seconds: float | None = None


class AgentHeartbeat(BaseModel):
    """Agent heartbeat payload."""

    version: str = Field(min_length=1, max_length=50)
    uptime_seconds: float = Field(ge=0)
    current_config_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    bird_instances: list[BirdInstanceStatus] = Field(default_factory=list)


class AgentHeartbeatResponse(BaseModel):
    """Response after processing agent heartbeat."""

    acknowledged: bool = True
    config_hash_match: bool


class AgentConfigApplied(BaseModel):
    """Agent confirmation that a config was applied."""

    config_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class AgentConfigFailed(BaseModel):
    """Agent report that a config could not be applied (e.g. bird -p failed)."""

    config_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    error: str = Field(min_length=1, max_length=4000)
