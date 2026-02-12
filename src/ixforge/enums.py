"""Enums centralizados del dominio IXForge"""

from enum import StrEnum

__all__ = [
    "BGPAdminState",
    "BGPOperState",
    "ConnectionState",
    "ConnectionType",
    "ContactRole",
    "CustomFieldEntityType",
    "CustomFieldType",
    "MemberState",
    "PeeringPolicy",
    "PortType",
    "UserRole",
    "VLANType",
]


# -- Members --


class MemberState(StrEnum):
    prospect = "prospect"
    provisioning = "provisioning"
    active = "active"
    suspended = "suspended"
    terminated = "terminated"


class PeeringPolicy(StrEnum):
    open = "open"
    selective = "selective"
    restrictive = "restrictive"
    no = "no"


# -- Connections --


class ConnectionType(StrEnum):
    physical = "physical"
    virtual = "virtual"


class ConnectionState(StrEnum):
    draft = "draft"
    provisioning = "provisioning"
    active = "active"
    disabled = "disabled"
    decommissioned = "decommissioned"


# -- Ports --


class PortType(StrEnum):
    member = "member"
    infra = "infra"
    unused = "unused"


# -- VLANs --


class VLANType(StrEnum):
    production = "production"
    quarantine = "quarantine"
    management = "management"
    other = "other"


# -- Contacts --


class ContactRole(StrEnum):
    noc = "noc"
    admin = "admin"
    technical = "technical"
    billing = "billing"


# -- Custom fields --


class CustomFieldEntityType(StrEnum):
    member = "member"
    connection = "connection"
    port = "port"
    switch = "switch"
    vlan = "vlan"


class CustomFieldType(StrEnum):
    string = "string"
    integer = "integer"
    boolean = "boolean"
    url = "url"
    email = "email"


# -- Users --


class UserRole(StrEnum):
    admin = "admin"
    member = "member"


# -- BGP --


class BGPAdminState(StrEnum):
    up = "up"
    down = "down"


class BGPOperState(StrEnum):
    up = "up"
    down = "down"
    unknown = "unknown"
