"""Factory Boy factories for IXForge models.

factory-boy does not natively support async SQLAlchemy, so these factories
build model instances in-memory (``Meta.strategy = BUILD_STRATEGY``).
Tests persist objects explicitly via ``session.add()`` + ``session.flush()``.
"""

import uuid
from datetime import UTC, datetime

import factory
from factory import fuzzy

from ixforge.enums import (
    BGPAdminState,
    BGPOperState,
    ConnectionState,
    ConnectionType,
    ContactRole,
    CustomFieldEntityType,
    CustomFieldType,
    MemberState,
    PeeringPolicy,
    PortType,
    VLANType,
)
from ixforge.models.api_key import APIKey
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
from ixforge.models.user import User, UserRole
from ixforge.models.vlan import VLAN
from ixforge.services.auth import hash_password


class _NoDBFactory(factory.Factory):
    """Base factory that builds in-memory model instances (no DB persistence)."""

    class Meta:
        abstract = True
        strategy = factory.BUILD_STRATEGY


class IXPFactory(_NoDBFactory):
    class Meta:
        model = IXP

    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"Test IXP {n}")
    short_name = factory.Sequence(lambda n: f"TIXP{n}")
    asn = fuzzy.FuzzyInteger(64512, 65534)
    website = factory.LazyAttribute(lambda o: f"https://{o.short_name.lower()}.example.net")
    country = "US"
    city = "Testville"
    peeringdb_id = None
    extra_data = None


class MemberFactory(_NoDBFactory):
    class Meta:
        model = Member

    id = factory.LazyFunction(uuid.uuid4)
    ixp_id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"Test Network {n}")
    short_name = factory.Sequence(lambda n: f"TN{n}")
    asn = factory.Sequence(lambda n: 64512 + n)
    state = MemberState.prospect
    peering_policy = PeeringPolicy.open
    peering_policy_details = None
    website = factory.LazyAttribute(lambda o: f"https://as{o.asn}.example.net")
    peeringdb_id = None
    extra_data = None


class ContactFactory(_NoDBFactory):
    class Meta:
        model = Contact

    id = factory.LazyFunction(uuid.uuid4)
    ixp_id = factory.LazyFunction(uuid.uuid4)
    member_id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"Contact Person {n}")
    email = factory.LazyAttribute(
        lambda o: f"contact{o.name.replace(' ', '').lower()}@example.net"
    )
    phone = "+1-555-0100"
    role = fuzzy.FuzzyChoice(
        [ContactRole.noc, ContactRole.admin, ContactRole.technical, ContactRole.billing]
    )


class SwitchFactory(_NoDBFactory):
    class Meta:
        model = Switch

    id = factory.LazyFunction(uuid.uuid4)
    ixp_id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"switch-{n:02d}")
    hostname = factory.LazyAttribute(lambda o: f"{o.name}.ixp.example.net")
    vendor = fuzzy.FuzzyChoice(["Arista", "Juniper", "Nokia"])
    model = "DCS-7280SR"
    management_ip = factory.Sequence(lambda n: f"10.0.0.{n + 1}")
    is_active = True
    extra_data = None


class PortFactory(_NoDBFactory):
    class Meta:
        model = Port

    id = factory.LazyFunction(uuid.uuid4)
    ixp_id = factory.LazyFunction(uuid.uuid4)
    switch_id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"Ethernet{n + 1}")
    speed = fuzzy.FuzzyChoice([1000, 10000, 100000])
    type = PortType.member
    member_id = None
    is_active = True
    extra_data = None


class VLANFactory(_NoDBFactory):
    class Meta:
        model = VLAN

    id = factory.LazyFunction(uuid.uuid4)
    ixp_id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"Peering VLAN {n}")
    vid = factory.Sequence(lambda n: 100 + n)
    type = VLANType.production
    description = "Production peering VLAN"
    extra_data = None


class IPPoolFactory(_NoDBFactory):
    class Meta:
        model = IPPool

    id = factory.LazyFunction(uuid.uuid4)
    ixp_id = factory.LazyFunction(uuid.uuid4)
    vlan_id = factory.LazyFunction(uuid.uuid4)
    network = "192.0.2.0/24"
    gateway = "192.0.2.1"
    af = 4


class IPAssignmentFactory(_NoDBFactory):
    class Meta:
        model = IPAssignment

    id = factory.LazyFunction(uuid.uuid4)
    ixp_id = factory.LazyFunction(uuid.uuid4)
    pool_id = factory.LazyFunction(uuid.uuid4)
    connection_id = factory.LazyFunction(uuid.uuid4)
    address = factory.Sequence(lambda n: f"192.0.2.{n + 2}")


class ConnectionFactory(_NoDBFactory):
    class Meta:
        model = Connection

    id = factory.LazyFunction(uuid.uuid4)
    ixp_id = factory.LazyFunction(uuid.uuid4)
    member_id = factory.LazyFunction(uuid.uuid4)
    port_id = None
    type = ConnectionType.physical
    state = ConnectionState.draft
    mac_address = factory.Sequence(lambda n: f"00:11:22:33:44:{n:02x}")
    speed = 10000
    extra_data = None


class ConnectionVLANFactory(_NoDBFactory):
    class Meta:
        model = ConnectionVLAN

    id = factory.LazyFunction(uuid.uuid4)
    ixp_id = factory.LazyFunction(uuid.uuid4)
    connection_id = factory.LazyFunction(uuid.uuid4)
    vlan_id = factory.LazyFunction(uuid.uuid4)
    tagged = False


class RouteServerFactory(_NoDBFactory):
    class Meta:
        model = RouteServer

    id = factory.LazyFunction(uuid.uuid4)
    ixp_id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"rs{n + 1}")
    hostname = factory.LazyAttribute(lambda o: f"{o.name}.ixp.example.net")
    ip_v4 = factory.Sequence(lambda n: f"192.0.2.{250 + n}")
    ip_v6 = factory.Sequence(lambda n: f"2001:db8::{250 + n}")
    asn = factory.LazyAttribute(lambda o: 65000)
    software = "bird"
    is_active = True
    last_heartbeat_at = None
    agent_version = None


class BGPSessionFactory(_NoDBFactory):
    class Meta:
        model = BGPSession

    id = factory.LazyFunction(uuid.uuid4)
    ixp_id = factory.LazyFunction(uuid.uuid4)
    route_server_id = factory.LazyFunction(uuid.uuid4)
    connection_id = factory.LazyFunction(uuid.uuid4)
    peer_ip = factory.Sequence(lambda n: f"192.0.2.{n + 2}")
    peer_asn = factory.Sequence(lambda n: 64512 + n)
    admin_state = BGPAdminState.up
    oper_state = BGPOperState.unknown
    af = 4
    max_prefixes = 100
    import_limit = None
    export_limit = None


class ConfigVersionFactory(_NoDBFactory):
    class Meta:
        model = ConfigVersion

    id = factory.LazyFunction(uuid.uuid4)
    route_server_id = factory.LazyFunction(uuid.uuid4)
    content = "# BIRD config\nrouter id 192.0.2.250;"
    config_hash = factory.LazyFunction(lambda: uuid.uuid4().hex)
    template_snapshot = None
    generated_at = factory.LazyFunction(lambda: datetime.now(UTC))
    applied_at = None
    generated_by_id = None


class EventFactory(_NoDBFactory):
    class Meta:
        model = Event

    id = factory.LazyFunction(uuid.uuid4)
    ixp_id = factory.LazyFunction(uuid.uuid4)
    type = "member.created"
    actor_id = None
    resource_type = "member"
    resource_id = factory.LazyFunction(uuid.uuid4)
    data = factory.LazyFunction(lambda: {"name": "Test Network", "asn": 64512})


class UserFactory(_NoDBFactory):
    class Meta:
        model = User

    id = factory.LazyFunction(uuid.uuid4)
    email = factory.Sequence(lambda n: f"user{n}@example.net")
    hashed_password = factory.LazyFunction(lambda: hash_password("testpass123"))
    full_name = factory.Sequence(lambda n: f"Test User {n}")
    role = UserRole.member
    member_id = None
    is_active = True


class APIKeyFactory(_NoDBFactory):
    class Meta:
        model = APIKey

    id = factory.LazyFunction(uuid.uuid4)
    key_hash = factory.LazyFunction(lambda: uuid.uuid4().hex + uuid.uuid4().hex[:32])
    prefix = "ixf_testkey_"
    name = factory.Sequence(lambda n: f"Test API Key {n}")
    scopes = factory.LazyFunction(list)
    user_id = None
    route_server_id = None
    is_active = True
    last_used_at = None


class CustomFieldDefinitionFactory(_NoDBFactory):
    class Meta:
        model = CustomFieldDefinition

    id = factory.LazyFunction(uuid.uuid4)
    ixp_id = factory.LazyFunction(uuid.uuid4)
    entity_type = CustomFieldEntityType.member
    field_name = factory.Sequence(lambda n: f"custom_field_{n}")
    field_type = CustomFieldType.string
    is_required = False
    default_value = None
    display_order = factory.Sequence(lambda n: n)
    description = "A custom test field"
