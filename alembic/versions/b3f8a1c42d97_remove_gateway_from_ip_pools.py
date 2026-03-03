"""Remove gateway from ip_pools

Revision ID: b3f8a1c42d97
Revises: a2e7f3c91b84
Create Date: 2026-03-02

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3f8a1c42d97"
down_revision: Union[str, None] = "a2e7f3c91b84"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.drop_column("ip_pools", "gateway")


def downgrade() -> None:
    op.add_column(
        "ip_pools",
        sa.Column("gateway", sa.TEXT(), nullable=True, comment="Gateway address"),
    )
