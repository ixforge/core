"""Remove contract_start and contract_renewal columns from members

Revision ID: c34ccb1c469f
Revises: 39b82a42fac5
Create Date: 2026-03-09
"""


import sqlalchemy as sa

from alembic import op

revision: str = "c34ccb1c469f"
down_revision: str | None = "39b82a42fac5"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_column("members", "contract_start")
    op.drop_column("members", "contract_renewal")


def downgrade() -> None:
    op.add_column("members", sa.Column("contract_renewal", sa.Date(), nullable=True))
    op.add_column("members", sa.Column("contract_start", sa.Date(), nullable=True))
