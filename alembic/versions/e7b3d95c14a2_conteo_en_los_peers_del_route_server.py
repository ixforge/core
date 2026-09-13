"""conteo de prefijos en los peers que no son miembros

Revision ID: e7b3d95c14a2
Revises: d1a4e63b92f5
Create Date: 2026-09-13

"""

import sqlalchemy as sa
from alembic import op

revision: str = "e7b3d95c14a2"
down_revision: str | None = "d1a4e63b92f5"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    for col in ("prefixes_imported", "prefixes_exported"):
        op.add_column("route_server_peers", sa.Column(col, sa.Integer(), nullable=True))
        op.create_check_constraint(
            f"ck_route_server_peers_{col}_no_negativo",
            "route_server_peers",
            f"{col} IS NULL OR {col} >= 0",
        )


def downgrade() -> None:
    for col in ("prefixes_exported", "prefixes_imported"):
        op.drop_constraint(f"ck_route_server_peers_{col}_no_negativo", "route_server_peers")
        op.drop_column("route_server_peers", col)
