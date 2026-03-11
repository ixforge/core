"""Remove contract_start and contract_renewal columns from members

Revision ID: c34ccb1c469f
Revises: 39b82a42fac5
Create Date: 2026-03-09
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "c34ccb1c469f"
down_revision: Union[str, None] = "39b82a42fac5"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.drop_column("members", "contract_start")
    op.drop_column("members", "contract_renewal")


def downgrade() -> None:
    op.add_column("members", sa.Column("contract_renewal", sa.Date(), nullable=True))
    op.add_column("members", sa.Column("contract_start", sa.Date(), nullable=True))
