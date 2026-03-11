"""Make switch location_id required and change ondelete to RESTRICT

Revision ID: e1465e3b85c1
Revises: c34ccb1c469f
Create Date: 2026-03-09
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "e1465e3b85c1"
down_revision: Union[str, None] = "c34ccb1c469f"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # Delete switches without location (dev environment, data loss acceptable)
    op.execute("DELETE FROM switches WHERE location_id IS NULL")

    op.alter_column("switches", "location_id", nullable=False)

    # Replace FK to change ondelete from SET NULL to RESTRICT
    op.drop_constraint("switches_location_id_fkey", "switches", type_="foreignkey")
    op.create_foreign_key(
        "switches_location_id_fkey",
        "switches",
        "locations",
        ["location_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("switches_location_id_fkey", "switches", type_="foreignkey")
    op.create_foreign_key(
        "switches_location_id_fkey",
        "switches",
        "locations",
        ["location_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("switches", "location_id", nullable=True)
