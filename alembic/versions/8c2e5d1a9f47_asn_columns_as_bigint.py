"""ASN columns hold the full unsigned 32-bit range

Revision ID: 8c2e5d1a9f47
Revises: f3c81a4d267e
Create Date: 2026-10-16

ASNs go up to 4294967295, beyond what a signed INTEGER stores. The type change
rewrites each table, so bgp_session_prefixes takes longer on route servers that
mirror full upstream tables

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "8c2e5d1a9f47"
down_revision: str | None = "f3c81a4d267e"
branch_labels: str | None = None
depends_on: str | None = None

_SCALAR_COLUMNS = (
    ("ixps", "asn"),
    ("asn_cache", "asn"),
    ("members", "asn"),
    ("route_server_peers", "peer_asn"),
    ("route_server_peers", "local_asn"),
)
_ARRAY_COLUMNS = (
    ("bgp_session_prefixes", "as_path"),
    ("bgp_prefix_events", "as_path"),
    ("bgp_prefix_events", "previous_as_path"),
)


def upgrade() -> None:
    for table, column in _SCALAR_COLUMNS:
        op.alter_column(table, column, type_=sa.BigInteger(), existing_type=sa.Integer())
    for table, column in _ARRAY_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=postgresql.ARRAY(sa.BigInteger()),
            existing_type=postgresql.ARRAY(sa.Integer()),
        )


def downgrade() -> None:
    for table, column in _ARRAY_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=postgresql.ARRAY(sa.Integer()),
            existing_type=postgresql.ARRAY(sa.BigInteger()),
        )
    for table, column in _SCALAR_COLUMNS:
        op.alter_column(table, column, type_=sa.Integer(), existing_type=sa.BigInteger())
