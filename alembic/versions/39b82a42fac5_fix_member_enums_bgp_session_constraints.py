"""fix: member enums, bgp session constraints

Revision ID: 39b82a42fac5
Revises: bfd548e1dcec
Create Date: 2026-03-04 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '39b82a42fac5'
down_revision: str | None = 'bfd548e1dcec'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- CAMBIO 1: Convert member_type and contract_type from varchar to enum --
    op.execute(
        "CREATE TYPE member_type AS ENUM "
        "('isp', 'cdn', 'ixp', 'academic', 'government', 'corporate', 'other')"
    )
    op.execute(
        "CREATE TYPE contract_type AS ENUM ('free', 'standard')"
    )
    op.execute(
        "ALTER TABLE members "
        "ALTER COLUMN member_type TYPE member_type USING member_type::member_type"
    )
    op.execute(
        "ALTER TABLE members "
        "ALTER COLUMN contract_type TYPE contract_type USING contract_type::contract_type"
    )

    # -- CAMBIO 2: BGP session constraints --
    op.create_unique_constraint(
        "uq_bgp_sessions_rs_conn_af",
        "bgp_sessions",
        ["route_server_id", "connection_id", "af"],
    )
    op.create_check_constraint(
        "ck_bgp_sessions_peer_asn_positive",
        "bgp_sessions",
        "peer_asn > 0",
    )

    # -- CAMBIO 3: Member country ISO constraint --
    op.create_check_constraint(
        "ck_members_country_iso",
        "members",
        "country IS NULL OR country ~ '^[A-Z]{2}$'",
    )


def downgrade() -> None:
    # -- Revert CAMBIO 3 --
    op.drop_constraint("ck_members_country_iso", "members", type_="check")

    # -- Revert CAMBIO 2 --
    op.drop_constraint("ck_bgp_sessions_peer_asn_positive", "bgp_sessions", type_="check")
    op.drop_constraint("uq_bgp_sessions_rs_conn_af", "bgp_sessions", type_="unique")

    # -- Revert CAMBIO 1 --
    op.execute(
        "ALTER TABLE members "
        "ALTER COLUMN contract_type TYPE varchar(20) USING contract_type::text"
    )
    op.execute(
        "ALTER TABLE members "
        "ALTER COLUMN member_type TYPE varchar(50) USING member_type::text"
    )
    op.execute("DROP TYPE IF EXISTS contract_type")
    op.execute("DROP TYPE IF EXISTS member_type")
