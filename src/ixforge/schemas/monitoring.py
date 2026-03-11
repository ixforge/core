"""Monitoring target schemas."""

import uuid

from pydantic import BaseModel


class MonitoringSwitchTarget(BaseModel):
    """Switch target for the Collector agent.

    ``snmp_community`` is intentionally exposed here in plaintext because the
    Collector needs it to poll switches via SNMP.  This endpoint is protected
    by the ``monitoring:read`` API-key scope, so only authorised Collector
    keys can access these values
    """

    id: uuid.UUID
    name: str
    management_ip: str | None
    snmp_community: str | None

    model_config = {"from_attributes": True}


class MonitoringPortTarget(BaseModel):
    id: uuid.UUID
    switch_id: uuid.UUID
    name: str
    speed: int
    member_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class MonitoringMemberIP(BaseModel):
    member_id: uuid.UUID
    member_name: str
    address: str
    af: int

    model_config = {"from_attributes": True}


class MonitoringTargets(BaseModel):
    switches: list[MonitoringSwitchTarget]
    ports: list[MonitoringPortTarget]
    member_ips: list[MonitoringMemberIP]
