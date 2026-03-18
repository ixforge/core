"""Enums centralizados del dominio IXForge"""

from enum import StrEnum

__all__ = [
    "BGPAdminState",
    "BGPOperState",
    "ConnectionState",
    "ConnectionType",
    "ContactRole",
    "ContractType",
    "CustomFieldEntityType",
    "CustomFieldType",
    "MemberState",
    "MemberType",
    "PeeringPolicy",
    "TrunkState",
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


class MemberType(StrEnum):
    isp = "isp"
    cdn = "cdn"
    ixp = "ixp"
    academico = "academico"
    gobierno = "gobierno"
    corporativo = "corporativo"
    infraestructura_critica = "infraestructura_critica"
    otro = "otro"


class ContractType(StrEnum):
    free = "free"
    standard = "standard"


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


# -- Trunks --


class TrunkState(StrEnum):
    draft = "draft"
    provisioning = "provisioning"
    active = "active"
    disabled = "disabled"
    decommissioned = "decommissioned"


# -- VLANs --


class VLANType(StrEnum):
    production = "production"
    quarantine = "quarantine"
    management = "management"
    private = "private"
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
    trunk = "trunk"
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
