"""Add apply_error to config_versions

Revision ID: b8c1d2e3f4a5
Revises: a3b4c5d6e7f8
Create Date: 2026-07-31
"""


import sqlalchemy as sa

from alembic import op

revision: str = "b8c1d2e3f4a5"
down_revision: str | None = "a3b4c5d6e7f8"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("config_versions", sa.Column("apply_error", sa.Text(), nullable=True))
    op.add_column(
        "config_versions",
        sa.Column("apply_error_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("config_versions", "apply_error_at")
    op.drop_column("config_versions", "apply_error")
