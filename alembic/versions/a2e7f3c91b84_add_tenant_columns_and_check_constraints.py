"""Add tenant ixp_id columns and CHECK constraints

Revision ID: a2e7f3c91b84
Revises: 1779b2c0243f
Create Date: 2026-02-12 16:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a2e7f3c91b84'
down_revision: str | None = '1779b2c0243f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Phase 1: Add ixp_id columns as nullable ---
    for table in (
        "ports", "contacts", "connections", "connection_vlans",
        "ip_pools", "ip_assignments", "bgp_sessions",
    ):
        op.add_column(table, sa.Column("ixp_id", sa.Uuid(), nullable=True))

    # --- Phase 2: Populate ixp_id from parent relationships ---

    # ports.ixp_id = switches.ixp_id (via switch_id)
    op.execute("""
        UPDATE ports SET ixp_id = switches.ixp_id
        FROM switches WHERE ports.switch_id = switches.id
    """)

    # contacts.ixp_id = members.ixp_id (via member_id)
    op.execute("""
        UPDATE contacts SET ixp_id = members.ixp_id
        FROM members WHERE contacts.member_id = members.id
    """)

    # connections.ixp_id = members.ixp_id (via member_id)
    op.execute("""
        UPDATE connections SET ixp_id = members.ixp_id
        FROM members WHERE connections.member_id = members.id
    """)

    # connection_vlans.ixp_id = connections.ixp_id (via connection_id)
    # Must run after connections is populated
    op.execute("""
        UPDATE connection_vlans SET ixp_id = connections.ixp_id
        FROM connections WHERE connection_vlans.connection_id = connections.id
    """)

    # ip_pools.ixp_id = vlans.ixp_id (via vlan_id)
    op.execute("""
        UPDATE ip_pools SET ixp_id = vlans.ixp_id
        FROM vlans WHERE ip_pools.vlan_id = vlans.id
    """)

    # ip_assignments.ixp_id = ip_pools.ixp_id (via pool_id)
    # Must run after ip_pools is populated
    op.execute("""
        UPDATE ip_assignments SET ixp_id = ip_pools.ixp_id
        FROM ip_pools WHERE ip_assignments.pool_id = ip_pools.id
    """)

    # bgp_sessions.ixp_id = route_servers.ixp_id (via route_server_id)
    op.execute("""
        UPDATE bgp_sessions SET ixp_id = route_servers.ixp_id
        FROM route_servers WHERE bgp_sessions.route_server_id = route_servers.id
    """)

    # --- Phase 3: Make NOT NULL, add FK and index ---
    for table in (
        "ports", "contacts", "connections", "connection_vlans",
        "ip_pools", "ip_assignments", "bgp_sessions",
    ):
        op.alter_column(table, "ixp_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_ixp_id",
            table,
            "ixps",
            ["ixp_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(f"ix_{table}_ixp_id", table, ["ixp_id"])

    # --- Phase 4: CHECK constraints ---
    op.create_check_constraint("ck_ixps_asn_positive", "ixps", "asn > 0")
    op.create_check_constraint("ck_members_asn_positive", "members", "asn > 0")
    op.create_check_constraint("ck_route_servers_asn_positive", "route_servers", "asn > 0")
    op.create_check_constraint("ck_vlans_vid_range", "vlans", "vid >= 1 AND vid <= 4094")
    op.create_check_constraint("ck_ports_speed_positive", "ports", "speed > 0")
    op.create_check_constraint("ck_ip_pools_af_valid", "ip_pools", "af IN (4, 6)")
    op.create_check_constraint("ck_bgp_sessions_af_valid", "bgp_sessions", "af IN (4, 6)")
    op.create_check_constraint(
        "ck_api_keys_owner_xor",
        "api_keys",
        "(user_id IS NOT NULL AND route_server_id IS NULL) OR "
        "(user_id IS NULL AND route_server_id IS NOT NULL)",
    )

    # --- Phase 5: api_keys.scopes server_default ---
    op.alter_column(
        "api_keys",
        "scopes",
        server_default=sa.text("'{}'"),
    )


def downgrade() -> None:
    # Remove server_default
    op.alter_column("api_keys", "scopes", server_default=None)

    # Drop CHECK constraints
    op.drop_constraint("ck_api_keys_owner_xor", "api_keys", type_="check")
    op.drop_constraint("ck_bgp_sessions_af_valid", "bgp_sessions", type_="check")
    op.drop_constraint("ck_ip_pools_af_valid", "ip_pools", type_="check")
    op.drop_constraint("ck_ports_speed_positive", "ports", type_="check")
    op.drop_constraint("ck_vlans_vid_range", "vlans", type_="check")
    op.drop_constraint("ck_route_servers_asn_positive", "route_servers", type_="check")
    op.drop_constraint("ck_members_asn_positive", "members", type_="check")
    op.drop_constraint("ck_ixps_asn_positive", "ixps", type_="check")

    # Drop ixp_id columns (FK and index go with them)
    for table in (
        "bgp_sessions", "ip_assignments", "ip_pools",
        "connection_vlans", "connections", "contacts", "ports",
    ):
        op.drop_constraint(f"fk_{table}_ixp_id", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_ixp_id", table_name=table)
        op.drop_column(table, "ixp_id")
