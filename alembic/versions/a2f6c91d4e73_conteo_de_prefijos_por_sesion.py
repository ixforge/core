"""conteo de prefijos por sesion bgp

Revision ID: a2f6c91d4e73
Revises: f1d3a86b40c2
Create Date: 2026-09-12

"""

import sqlalchemy as sa
from alembic import op

revision: str = "a2f6c91d4e73"
down_revision: str | None = "f1d3a86b40c2"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "bgp_sessions",
        sa.Column(
            "prefixes_imported",
            sa.Integer(),
            nullable=True,
            comment="Rutas recibidas del peer segun el ultimo reporte",
        ),
    )
    op.add_column(
        "bgp_sessions",
        sa.Column(
            "prefixes_exported",
            sa.Integer(),
            nullable=True,
            comment="Rutas anunciadas al peer segun el ultimo reporte",
        ),
    )
    # Nullable a proposito y sin default: hasta que el agente de cada route
    # server se actualice, el conteo no existe, y eso es distinto de cero
    op.create_check_constraint(
        "ck_bgp_sessions_prefixes_imported_no_negativo",
        "bgp_sessions",
        "prefixes_imported IS NULL OR prefixes_imported >= 0",
    )
    op.create_check_constraint(
        "ck_bgp_sessions_prefixes_exported_no_negativo",
        "bgp_sessions",
        "prefixes_exported IS NULL OR prefixes_exported >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_bgp_sessions_prefixes_exported_no_negativo", "bgp_sessions")
    op.drop_constraint("ck_bgp_sessions_prefixes_imported_no_negativo", "bgp_sessions")
    op.drop_column("bgp_sessions", "prefixes_exported")
    op.drop_column("bgp_sessions", "prefixes_imported")
