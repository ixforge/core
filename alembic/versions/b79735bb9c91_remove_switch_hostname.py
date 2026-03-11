"""Remove hostname column from switches, use name as unique key

Revision ID: b79735bb9c91
Revises: d67f97e3a57c
Create Date: 2026-03-09
"""


import sqlalchemy as sa

from alembic import op

revision: str = "b79735bb9c91"
down_revision: str | None = "d67f97e3a57c"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_constraint("uq_switches_ixp_id_hostname", "switches", type_="unique")
    op.drop_column("switches", "hostname")
    op.create_unique_constraint("uq_switches_ixp_id_name", "switches", ["ixp_id", "name"])


def downgrade() -> None:
    op.drop_constraint("uq_switches_ixp_id_name", "switches", type_="unique")
    op.add_column("switches", sa.Column("hostname", sa.String(255), nullable=True))
    op.execute("UPDATE switches SET hostname = name")
    op.alter_column("switches", "hostname", nullable=False)
    op.create_unique_constraint("uq_switches_ixp_id_hostname", "switches", ["ixp_id", "hostname"])
