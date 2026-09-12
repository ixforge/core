"""el id de las tablas de prefijos se genera solo

Revision ID: d1a4e63b92f5
Revises: c9f2b41e70d8
Create Date: 2026-09-12

Las dos tablas se crearon sin el server_default de gen_random_uuid() que el
mixin declara, asi que todo INSERT que no trajera el id explicito violaba el
not null. La suite no lo vio porque arma el schema desde los modelos.

"""

import sqlalchemy as sa
from alembic import op

revision: str = "d1a4e63b92f5"
down_revision: str | None = "c9f2b41e70d8"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    for tabla in ("bgp_session_prefixes", "bgp_prefix_events"):
        op.alter_column(
            tabla, "id",
            existing_type=sa.Uuid(),
            existing_nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        )


def downgrade() -> None:
    for tabla in ("bgp_session_prefixes", "bgp_prefix_events"):
        op.alter_column(
            tabla, "id",
            existing_type=sa.Uuid(),
            existing_nullable=False,
            server_default=None,
        )
