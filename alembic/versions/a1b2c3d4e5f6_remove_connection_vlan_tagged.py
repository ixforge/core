"""Remove tagged column from connection_vlans

Revision ID: a1b2c3d4e5f6
Revises: c5a1e8f34d02
Create Date: 2026-03-11
"""


import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "c5a1e8f34d02"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_column("connection_vlans", "tagged")


def downgrade() -> None:
    op.add_column(
        "connection_vlans",
        sa.Column("tagged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
