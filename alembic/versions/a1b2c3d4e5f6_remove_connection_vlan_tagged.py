"""Remove tagged column from connection_vlans

Revision ID: a1b2c3d4e5f6
Revises: c5a1e8f34d02
Create Date: 2026-03-11
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c5a1e8f34d02"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.drop_column("connection_vlans", "tagged")


def downgrade() -> None:
    op.add_column(
        "connection_vlans",
        sa.Column("tagged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
