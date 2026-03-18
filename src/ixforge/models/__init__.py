"""Import all models for Alembic autogenerate."""

from ixforge.models.api_key import APIKey
from ixforge.models.asn_cache import ASNCache
from ixforge.models.base import Base
from ixforge.models.bgp_session import BGPSession
from ixforge.models.config import ConfigVersion
from ixforge.models.connection import Connection
from ixforge.models.contact import Contact
from ixforge.models.custom_field import CustomFieldDefinition
from ixforge.models.event import Event
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.ixp import IXP
from ixforge.models.location import Location
from ixforge.models.member import Member
from ixforge.models.route_server import RouteServer
from ixforge.models.route_server_vlan import RouteServerVLAN
from ixforge.models.rs_ip_assignment import RSIPAssignment
from ixforge.models.switch import Switch
from ixforge.models.trunk import Trunk, TrunkVLAN
from ixforge.models.user import User
from ixforge.models.vlan import VLAN
from ixforge.models.vlan_member import VLANMember

__all__ = [
    "IXP",
    "VLAN",
    "APIKey",
    "ASNCache",
    "BGPSession",
    "Base",
    "ConfigVersion",
    "Connection",
    "Contact",
    "CustomFieldDefinition",
    "Event",
    "IPAssignment",
    "IPPool",
    "Location",
    "Member",
    "RSIPAssignment",
    "RouteServer",
    "RouteServerVLAN",
    "Switch",
    "Trunk",
    "TrunkVLAN",
    "User",
    "VLANMember",
]
