"""Agent communication schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


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


class AgentStatusReport(BaseModel):
    """Agent bulk BGP session status report."""

    sessions: list[BGPSessionState] = Field(max_length=10000)


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
