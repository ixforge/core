"""Drop hostname and asn from route_servers, add notes

Revision ID: f7e8d9c0b1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-03-11
"""

import sqlalchemy as sa

from alembic import op

revision: str = "f7e8d9c0b1a2"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_constraint("uq_route_servers_ixp_id_hostname", "route_servers", type_="unique")
    op.drop_constraint("ck_route_servers_asn_positive", "route_servers", type_="check")
    op.drop_column("route_servers", "hostname")
    op.drop_column("route_servers", "asn")
    op.add_column(
        "route_servers",
        sa.Column("notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("route_servers", "notes")
    op.add_column(
        "route_servers",
        sa.Column("asn", sa.Integer(), nullable=False, server_default=sa.text("65000")),
    )
    op.add_column(
        "route_servers",
        sa.Column("hostname", sa.String(255), nullable=False, server_default=sa.text("'unknown'")),
    )
    op.create_check_constraint(
        "ck_route_servers_asn_positive", "route_servers", "asn > 0"
    )
    op.create_unique_constraint(
        "uq_route_servers_ixp_id_hostname", "route_servers", ["ixp_id", "hostname"]
    )
