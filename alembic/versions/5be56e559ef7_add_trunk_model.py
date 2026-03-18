"""add_trunk_model

Revision ID: 5be56e559ef7
Revises: a2c4e6f8b0d1
Create Date: 2026-03-17 15:58:43.171775

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

import ixforge.models.types
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5be56e559ef7'
down_revision: Union[str, None] = 'a2c4e6f8b0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop tables that depend on connections/connection_vlans (FK order)
    op.drop_table('bgp_sessions')
    op.drop_table('ip_assignments')
    op.drop_table('connection_vlans')
    op.drop_table('connections')

    # Create trunks table
    op.create_table(
        'trunks',
        sa.Column('member_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('state', sa.Enum('draft', 'provisioning', 'active', 'disabled', 'decommissioned', name='trunk_state'), nullable=False),
        sa.Column('mac_address', ixforge.models.types.MACADDR(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('ixp_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('extra_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['ixp_id'], ['ixps.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ixp_id', 'member_id', 'name', name='uq_trunks_ixp_member_name'),
    )
    op.create_index(op.f('ix_trunks_ixp_id'), 'trunks', ['ixp_id'], unique=False)
    op.create_index(op.f('ix_trunks_member_id'), 'trunks', ['member_id'], unique=False)

    # Create trunk_vlans table
    op.create_table(
        'trunk_vlans',
        sa.Column('trunk_id', sa.Uuid(), nullable=False),
        sa.Column('vlan_id', sa.Uuid(), nullable=False),
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('ixp_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['ixp_id'], ['ixps.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['trunk_id'], ['trunks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['vlan_id'], ['vlans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('trunk_id', 'vlan_id', name='uq_trunk_vlans_trunk_vlan'),
    )
    op.create_index(op.f('ix_trunk_vlans_ixp_id'), 'trunk_vlans', ['ixp_id'], unique=False)
    op.create_index(op.f('ix_trunk_vlans_trunk_id'), 'trunk_vlans', ['trunk_id'], unique=False)
    op.create_index(op.f('ix_trunk_vlans_vlan_id'), 'trunk_vlans', ['vlan_id'], unique=False)

    # Recreate connections with trunk_id instead of member_id/mac_address, add notes
    op.create_table(
        'connections',
        sa.Column('trunk_id', sa.Uuid(), nullable=False),
        sa.Column('switch_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('type', postgresql.ENUM('physical', 'virtual', name='connection_type', create_type=False), nullable=False),
        sa.Column('state', postgresql.ENUM('draft', 'provisioning', 'active', 'disabled', 'decommissioned', name='connection_state', create_type=False), nullable=False),
        sa.Column('speed', sa.Integer(), nullable=False, comment='Speed in Mbps'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('ixp_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('extra_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint('speed > 0', name='ck_connections_speed_positive'),
        sa.ForeignKeyConstraint(['ixp_id'], ['ixps.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['switch_id'], ['switches.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['trunk_id'], ['trunks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('switch_id', 'name', name='uq_connections_switch_name'),
    )
    op.create_index(op.f('ix_connections_ixp_id'), 'connections', ['ixp_id'], unique=False)
    op.create_index(op.f('ix_connections_switch_id'), 'connections', ['switch_id'], unique=False)
    op.create_index(op.f('ix_connections_trunk_id'), 'connections', ['trunk_id'], unique=False)

    # Recreate ip_assignments with trunk_vlan_id instead of connection_id
    op.create_table(
        'ip_assignments',
        sa.Column('pool_id', sa.Uuid(), nullable=False),
        sa.Column('trunk_vlan_id', sa.Uuid(), nullable=False),
        sa.Column('address', ixforge.models.types.INET(), nullable=False, comment='IP address'),
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('ixp_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['ixp_id'], ['ixps.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['pool_id'], ['ip_pools.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['trunk_vlan_id'], ['trunk_vlans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('address'),
    )
    op.create_index(op.f('ix_ip_assignments_ixp_id'), 'ip_assignments', ['ixp_id'], unique=False)
    op.create_index(op.f('ix_ip_assignments_pool_id'), 'ip_assignments', ['pool_id'], unique=False)
    op.create_index(op.f('ix_ip_assignments_trunk_vlan_id'), 'ip_assignments', ['trunk_vlan_id'], unique=False)

    # Recreate bgp_sessions with trunk_vlan_id instead of connection_id
    op.create_table(
        'bgp_sessions',
        sa.Column('route_server_id', sa.Uuid(), nullable=False),
        sa.Column('trunk_vlan_id', sa.Uuid(), nullable=False),
        sa.Column('peer_ip', ixforge.models.types.INET(), nullable=False),
        sa.Column('peer_asn', sa.Integer(), nullable=False),
        sa.Column('admin_state', postgresql.ENUM('up', 'down', name='bgp_admin_state', create_type=False), nullable=False),
        sa.Column('oper_state', postgresql.ENUM('up', 'down', 'unknown', name='bgp_oper_state', create_type=False), nullable=False),
        sa.Column('af', sa.Integer(), nullable=False, comment='Address family: 4 or 6'),
        sa.Column('max_prefixes', sa.Integer(), nullable=True),
        sa.Column('import_limit', sa.Integer(), nullable=True),
        sa.Column('export_limit', sa.Integer(), nullable=True),
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('ixp_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('af IN (4, 6)', name='ck_bgp_sessions_af_valid'),
        sa.CheckConstraint('peer_asn > 0', name='ck_bgp_sessions_peer_asn_positive'),
        sa.ForeignKeyConstraint(['ixp_id'], ['ixps.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['route_server_id'], ['route_servers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['trunk_vlan_id'], ['trunk_vlans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('route_server_id', 'trunk_vlan_id', 'af', name='uq_bgp_sessions_rs_trunk_vlan_af'),
    )
    op.create_index(op.f('ix_bgp_sessions_ixp_id'), 'bgp_sessions', ['ixp_id'], unique=False)
    op.create_index(op.f('ix_bgp_sessions_route_server_id'), 'bgp_sessions', ['route_server_id'], unique=False)
    op.create_index(op.f('ix_bgp_sessions_trunk_vlan_id'), 'bgp_sessions', ['trunk_vlan_id'], unique=False)
    op.create_index('ix_bgp_sessions_rs_trunk_vlan', 'bgp_sessions', ['route_server_id', 'trunk_vlan_id'], unique=False)

    # Add 'trunk' to custom_field_entity_type enum (must be outside transaction)
    op.execute("COMMIT")
    op.execute("ALTER TYPE custom_field_entity_type ADD VALUE IF NOT EXISTS 'trunk' AFTER 'connection'")
    op.execute("BEGIN")


def downgrade() -> None:
    op.drop_table('bgp_sessions')
    op.drop_table('ip_assignments')
    op.drop_table('connections')
    op.drop_table('trunk_vlans')
    op.drop_table('trunks')
    op.execute("DROP TYPE IF EXISTS trunk_state")

    op.create_table(
        'connections',
        sa.Column('member_id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('switch_id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('name', sa.String(length=100), autoincrement=False, nullable=False),
        sa.Column('type', postgresql.ENUM('physical', 'virtual', name='connection_type'), autoincrement=False, nullable=False),
        sa.Column('state', postgresql.ENUM('draft', 'provisioning', 'active', 'disabled', 'decommissioned', name='connection_state'), autoincrement=False, nullable=False),
        sa.Column('mac_address', postgresql.MACADDR(), autoincrement=False, nullable=True),
        sa.Column('speed', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), autoincrement=False, nullable=False),
        sa.Column('ixp_id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.Column('extra_data', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True),
        sa.CheckConstraint('speed > 0', name='ck_connections_speed_positive'),
        sa.ForeignKeyConstraint(['ixp_id'], ['ixps.id'], name=op.f('fk_connections_ixp_id'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], name=op.f('connections_member_id_fkey'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['switch_id'], ['switches.id'], name=op.f('connections_switch_id_fkey'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('connections_pkey')),
        sa.UniqueConstraint('switch_id', 'name', name=op.f('uq_connections_switch_name'), postgresql_include=[], postgresql_nulls_not_distinct=False),
    )
    op.create_index(op.f('ix_connections_ixp_id'), 'connections', ['ixp_id'], unique=False)
    op.create_index(op.f('ix_connections_member_id'), 'connections', ['member_id'], unique=False)
    op.create_index(op.f('ix_connections_switch_id'), 'connections', ['switch_id'], unique=False)

    op.create_table(
        'connection_vlans',
        sa.Column('connection_id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('vlan_id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), autoincrement=False, nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.Column('ixp_id', sa.UUID(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], name=op.f('connection_vlans_connection_id_fkey'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['ixp_id'], ['ixps.id'], name=op.f('fk_connection_vlans_ixp_id'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['vlan_id'], ['vlans.id'], name=op.f('connection_vlans_vlan_id_fkey'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('connection_vlans_pkey')),
        sa.UniqueConstraint('connection_id', 'vlan_id', name=op.f('uq_connection_vlans_conn_vlan'), postgresql_include=[], postgresql_nulls_not_distinct=False),
    )
    op.create_index(op.f('ix_connection_vlans_connection_id'), 'connection_vlans', ['connection_id'], unique=False)
    op.create_index(op.f('ix_connection_vlans_ixp_id'), 'connection_vlans', ['ixp_id'], unique=False)
    op.create_index(op.f('ix_connection_vlans_vlan_id'), 'connection_vlans', ['vlan_id'], unique=False)

    op.create_table(
        'ip_assignments',
        sa.Column('pool_id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('connection_id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('address', postgresql.INET(), autoincrement=False, nullable=False),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), autoincrement=False, nullable=False),
        sa.Column('ixp_id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], name=op.f('ip_assignments_connection_id_fkey'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['ixp_id'], ['ixps.id'], name=op.f('fk_ip_assignments_ixp_id'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['pool_id'], ['ip_pools.id'], name=op.f('ip_assignments_pool_id_fkey'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('ip_assignments_pkey')),
        sa.UniqueConstraint('address', name=op.f('ip_assignments_address_key'), postgresql_include=[], postgresql_nulls_not_distinct=False),
    )
    op.create_index(op.f('ix_ip_assignments_connection_id'), 'ip_assignments', ['connection_id'], unique=False)
    op.create_index(op.f('ix_ip_assignments_ixp_id'), 'ip_assignments', ['ixp_id'], unique=False)
    op.create_index(op.f('ix_ip_assignments_pool_id'), 'ip_assignments', ['pool_id'], unique=False)

    op.create_table(
        'bgp_sessions',
        sa.Column('route_server_id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('connection_id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('peer_ip', postgresql.INET(), autoincrement=False, nullable=False),
        sa.Column('peer_asn', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('admin_state', postgresql.ENUM('up', 'down', name='bgp_admin_state'), autoincrement=False, nullable=False),
        sa.Column('oper_state', postgresql.ENUM('up', 'down', 'unknown', name='bgp_oper_state'), autoincrement=False, nullable=False),
        sa.Column('af', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('max_prefixes', sa.Integer(), autoincrement=False, nullable=True),
        sa.Column('import_limit', sa.Integer(), autoincrement=False, nullable=True),
        sa.Column('export_limit', sa.Integer(), autoincrement=False, nullable=True),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), autoincrement=False, nullable=False),
        sa.Column('ixp_id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.CheckConstraint('af IN (4, 6)', name='ck_bgp_sessions_af_valid'),
        sa.CheckConstraint('peer_asn > 0', name='ck_bgp_sessions_peer_asn_positive'),
        sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], name=op.f('bgp_sessions_connection_id_fkey'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['ixp_id'], ['ixps.id'], name=op.f('fk_bgp_sessions_ixp_id'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['route_server_id'], ['route_servers.id'], name=op.f('bgp_sessions_route_server_id_fkey'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('bgp_sessions_pkey')),
        sa.UniqueConstraint('route_server_id', 'connection_id', 'af', name=op.f('uq_bgp_sessions_rs_conn_af'), postgresql_include=[], postgresql_nulls_not_distinct=False),
    )
    op.create_index(op.f('ix_bgp_sessions_connection_id'), 'bgp_sessions', ['connection_id'], unique=False)
    op.create_index(op.f('ix_bgp_sessions_ixp_id'), 'bgp_sessions', ['ixp_id'], unique=False)
    op.create_index(op.f('ix_bgp_sessions_route_server_id'), 'bgp_sessions', ['route_server_id'], unique=False)
    op.create_index('ix_bgp_sessions_rs_conn', 'bgp_sessions', ['route_server_id', 'connection_id'], unique=False)
