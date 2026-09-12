"""communities de cada prefijo

Revision ID: c9f2b41e70d8
Revises: b5e8a2c74f19
Create Date: 2026-09-12

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9f2b41e70d8"
down_revision: str | None = "b5e8a2c74f19"
branch_labels: str | None = None
depends_on: str | None = None

_VACIO = sa.text("'{}'::varchar[]")


def upgrade() -> None:
    # server_default para que las filas que ya existan queden con lista vacia y
    # no con null: una ruta sin communities tiene cero, no "se desconoce"
    op.add_column(
        "bgp_session_prefixes",
        sa.Column("communities", postgresql.ARRAY(sa.String(length=64)),
                  nullable=False, server_default=_VACIO),
    )
    op.add_column(
        "bgp_prefix_events",
        sa.Column("communities", postgresql.ARRAY(sa.String(length=64)),
                  nullable=False, server_default=_VACIO),
    )
    op.add_column(
        "bgp_prefix_events",
        sa.Column("previous_communities", postgresql.ARRAY(sa.String(length=64)),
                  nullable=True,
                  comment="Solo en updated: con que communities venia antes"),
    )


def downgrade() -> None:
    op.drop_column("bgp_prefix_events", "previous_communities")
    op.drop_column("bgp_prefix_events", "communities")
    op.drop_column("bgp_session_prefixes", "communities")
