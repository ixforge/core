"""Import all models for Alembic autogenerate."""

from ixforge.models.api_key import APIKey
from ixforge.models.base import Base
from ixforge.models.bgp_session import BGPSession
from ixforge.models.config import ConfigVersion
from ixforge.models.connection import Connection, ConnectionVLAN
from ixforge.models.contact import Contact
from ixforge.models.custom_field import CustomFieldDefinition
from ixforge.models.event import Event
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.ixp import IXP
from ixforge.models.member import Member
from ixforge.models.port import Port
from ixforge.models.route_server import RouteServer
from ixforge.models.switch import Switch
from ixforge.models.user import User
from ixforge.models.vlan import VLAN

__all__ = [
    "IXP",
    "VLAN",
    "APIKey",
    "BGPSession",
    "Base",
    "ConfigVersion",
    "Connection",
    "ConnectionVLAN",
    "Contact",
    "CustomFieldDefinition",
    "Event",
    "IPAssignment",
    "IPPool",
    "Member",
    "Port",
    "RouteServer",
    "Switch",
    "User",
]
