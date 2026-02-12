"""Fix column types (enums, network types) and add missing constraints

Revision ID: b3f8a1c24e67
Revises: a2dcc3280494
Create Date: 2026-02-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b3f8a1c24e67"
down_revision: Union[str, None] = "a2dcc3280494"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Create PostgreSQL ENUM types --
    member_state = postgresql.ENUM(
        "prospect", "provisioning", "active", "suspended", "terminated",
        name="member_state", create_type=False,
    )
    peering_policy = postgresql.ENUM(
        "open", "selective", "restrictive", "no",
        name="peering_policy", create_type=False,
    )
    vlan_type = postgresql.ENUM(
        "production", "quarantine", "management", "other",
        name="vlan_type", create_type=False,
    )
    port_type = postgresql.ENUM(
        "member", "infra", "unused",
        name="port_type", create_type=False,
    )
    connection_type = postgresql.ENUM(
        "physical", "virtual",
        name="connection_type", create_type=False,
    )
    connection_state = postgresql.ENUM(
        "draft", "provisioning", "active", "disabled", "decommissioned",
        name="connection_state", create_type=False,
    )
    contact_role = postgresql.ENUM(
        "noc", "admin", "technical", "billing",
        name="contact_role", create_type=False,
    )
    custom_field_entity_type = postgresql.ENUM(
        "member", "connection", "port", "switch", "vlan",
        name="custom_field_entity_type", create_type=False,
    )
    custom_field_type = postgresql.ENUM(
        "string", "integer", "boolean", "url", "email",
        name="custom_field_type", create_type=False,
    )
    bgp_admin_state = postgresql.ENUM(
        "up", "down",
        name="bgp_admin_state", create_type=False,
    )
    bgp_oper_state = postgresql.ENUM(
        "up", "down", "unknown",
        name="bgp_oper_state", create_type=False,
    )

    # Create ENUM types in PostgreSQL
    for enum in [
        member_state, peering_policy, vlan_type, port_type,
        connection_type, connection_state, contact_role,
        custom_field_entity_type, custom_field_type,
        bgp_admin_state, bgp_oper_state,
    ]:
        enum.create(op.get_bind(), checkfirst=True)

    # -- Convert String columns to ENUM types --

    # members.state
    op.execute(
        "ALTER TABLE members ALTER COLUMN state TYPE member_state "
        "USING state::member_state"
    )
    # members.peering_policy
    op.execute(
        "ALTER TABLE members ALTER COLUMN peering_policy TYPE peering_policy "
        "USING peering_policy::peering_policy"
    )
    # vlans.type
    op.execute(
        "ALTER TABLE vlans ALTER COLUMN type TYPE vlan_type "
        "USING type::vlan_type"
    )
    # ports.type
    op.execute(
        "ALTER TABLE ports ALTER COLUMN type TYPE port_type "
        "USING type::port_type"
    )
    # connections.type
    op.execute(
        "ALTER TABLE connections ALTER COLUMN type TYPE connection_type "
        "USING type::connection_type"
    )
    # connections.state
    op.execute(
        "ALTER TABLE connections ALTER COLUMN state TYPE connection_state "
        "USING state::connection_state"
    )
    # contacts.role
    op.execute(
        "ALTER TABLE contacts ALTER COLUMN role TYPE contact_role "
        "USING role::contact_role"
    )
    # custom_field_definitions.entity_type
    op.execute(
        "ALTER TABLE custom_field_definitions ALTER COLUMN entity_type "
        "TYPE custom_field_entity_type USING entity_type::custom_field_entity_type"
    )
    # custom_field_definitions.field_type
    op.execute(
        "ALTER TABLE custom_field_definitions ALTER COLUMN field_type "
        "TYPE custom_field_type USING field_type::custom_field_type"
    )
    # bgp_sessions.admin_state
    op.execute(
        "ALTER TABLE bgp_sessions ALTER COLUMN admin_state TYPE bgp_admin_state "
        "USING admin_state::bgp_admin_state"
    )
    # bgp_sessions.oper_state
    op.execute(
        "ALTER TABLE bgp_sessions ALTER COLUMN oper_state TYPE bgp_oper_state "
        "USING oper_state::bgp_oper_state"
    )

    # -- Convert String columns to PostgreSQL network types --

    # route_servers
    op.execute("ALTER TABLE route_servers ALTER COLUMN ip_v4 TYPE inet USING ip_v4::inet")
    op.execute("ALTER TABLE route_servers ALTER COLUMN ip_v6 TYPE inet USING ip_v6::inet")

    # switches
    op.execute("ALTER TABLE switches ALTER COLUMN management_ip TYPE inet USING management_ip::inet")

    # ip_pools
    op.execute("ALTER TABLE ip_pools ALTER COLUMN network TYPE cidr USING network::cidr")
    op.execute("ALTER TABLE ip_pools ALTER COLUMN gateway TYPE inet USING gateway::inet")

    # ip_assignments
    op.execute("ALTER TABLE ip_assignments ALTER COLUMN address TYPE inet USING address::inet")

    # bgp_sessions
    op.execute("ALTER TABLE bgp_sessions ALTER COLUMN peer_ip TYPE inet USING peer_ip::inet")

    # connections
    op.execute("ALTER TABLE connections ALTER COLUMN mac_address TYPE macaddr USING mac_address::macaddr")

    # -- Add missing unique constraints --
    op.create_unique_constraint("uq_vlans_ixp_id_vid", "vlans", ["ixp_id", "vid"])
    op.create_unique_constraint("uq_switches_ixp_id_hostname", "switches", ["ixp_id", "hostname"])
    op.create_unique_constraint("uq_ports_switch_id_name", "ports", ["switch_id", "name"])

    # -- Add server_default for boolean columns --
    op.alter_column("switches", "is_active", server_default=sa.text("true"))
    op.alter_column("ports", "is_active", server_default=sa.text("true"))
    op.alter_column("route_servers", "is_active", server_default=sa.text("true"))
    op.alter_column("users", "is_active", server_default=sa.text("true"))
    op.alter_column("api_keys", "is_active", server_default=sa.text("true"))
    op.alter_column("custom_field_definitions", "is_required", server_default=sa.text("false"))


def downgrade() -> None:
    # -- Remove server_defaults --
    op.alter_column("custom_field_definitions", "is_required", server_default=None)
    op.alter_column("api_keys", "is_active", server_default=None)
    op.alter_column("users", "is_active", server_default=None)
    op.alter_column("route_servers", "is_active", server_default=None)
    op.alter_column("ports", "is_active", server_default=None)
    op.alter_column("switches", "is_active", server_default=None)

    # -- Remove unique constraints --
    op.drop_constraint("uq_ports_switch_id_name", "ports")
    op.drop_constraint("uq_switches_ixp_id_hostname", "switches")
    op.drop_constraint("uq_vlans_ixp_id_vid", "vlans")

    # -- Revert network types to String --
    op.execute("ALTER TABLE connections ALTER COLUMN mac_address TYPE varchar(17) USING mac_address::text")
    op.execute("ALTER TABLE bgp_sessions ALTER COLUMN peer_ip TYPE varchar(45) USING peer_ip::text")
    op.execute("ALTER TABLE ip_assignments ALTER COLUMN address TYPE varchar(45) USING address::text")
    op.execute("ALTER TABLE ip_pools ALTER COLUMN gateway TYPE varchar(45) USING gateway::text")
    op.execute("ALTER TABLE ip_pools ALTER COLUMN network TYPE varchar(50) USING network::text")
    op.execute("ALTER TABLE switches ALTER COLUMN management_ip TYPE varchar(45) USING management_ip::text")
    op.execute("ALTER TABLE route_servers ALTER COLUMN ip_v6 TYPE varchar(45) USING ip_v6::text")
    op.execute("ALTER TABLE route_servers ALTER COLUMN ip_v4 TYPE varchar(45) USING ip_v4::text")

    # -- Revert ENUM types to String --
    op.execute("ALTER TABLE bgp_sessions ALTER COLUMN oper_state TYPE varchar(10) USING oper_state::text")
    op.execute("ALTER TABLE bgp_sessions ALTER COLUMN admin_state TYPE varchar(10) USING admin_state::text")
    op.execute("ALTER TABLE custom_field_definitions ALTER COLUMN field_type TYPE varchar(20) USING field_type::text")
    op.execute("ALTER TABLE custom_field_definitions ALTER COLUMN entity_type TYPE varchar(20) USING entity_type::text")
    op.execute("ALTER TABLE contacts ALTER COLUMN role TYPE varchar(20) USING role::text")
    op.execute("ALTER TABLE connections ALTER COLUMN state TYPE varchar(20) USING state::text")
    op.execute("ALTER TABLE connections ALTER COLUMN type TYPE varchar(20) USING type::text")
    op.execute("ALTER TABLE ports ALTER COLUMN type TYPE varchar(20) USING type::text")
    op.execute("ALTER TABLE vlans ALTER COLUMN type TYPE varchar(20) USING type::text")
    op.execute("ALTER TABLE members ALTER COLUMN peering_policy TYPE varchar(20) USING peering_policy::text")
    op.execute("ALTER TABLE members ALTER COLUMN state TYPE varchar(20) USING state::text")

    # -- Drop ENUM types --
    for name in [
        "bgp_oper_state", "bgp_admin_state", "custom_field_type",
        "custom_field_entity_type", "contact_role", "connection_state",
        "connection_type", "port_type", "vlan_type", "peering_policy",
        "member_state",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {name}")
