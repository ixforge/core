"""los prefijos tambien pueden colgar de un peer del route server

Revision ID: f3c81a4d267e
Revises: e7b3d95c14a2
Create Date: 2026-09-13

El upstream no tiene sesion de miembro, pero sus prefijos se muestran igual que
los de cualquiera. Cada fila cuelga de una sesion o de un peer, nunca de las dos.

"""

import sqlalchemy as sa
from alembic import op

revision: str = "f3c81a4d267e"
down_revision: str | None = "e7b3d95c14a2"
branch_labels: str | None = None
depends_on: str | None = None

_TABLAS = ("bgp_session_prefixes", "bgp_prefix_events")


def upgrade() -> None:
    for tabla in _TABLAS:
        op.add_column(tabla, sa.Column("route_server_peer_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"fk_{tabla}_route_server_peer_id", tabla,
            "route_server_peers", ["route_server_peer_id"], ["id"], ondelete="CASCADE",
        )
        op.create_index(f"ix_{tabla}_route_server_peer_id", tabla, ["route_server_peer_id"])
        op.alter_column(tabla, "bgp_session_id", existing_type=sa.Uuid(), nullable=True)
        op.create_check_constraint(
            f"ck_{tabla}_una_sola_fuente",
            tabla,
            "(bgp_session_id IS NULL) <> (route_server_peer_id IS NULL)",
        )

    op.create_unique_constraint(
        "uq_bgp_session_prefixes_peer_prefijo",
        "bgp_session_prefixes",
        ["route_server_peer_id", "prefix"],
    )
    op.create_index(
        "ix_bgp_prefix_events_peer_fecha",
        "bgp_prefix_events",
        ["route_server_peer_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_bgp_prefix_events_peer_fecha", "bgp_prefix_events")
    op.drop_constraint("uq_bgp_session_prefixes_peer_prefijo", "bgp_session_prefixes")
    for tabla in _TABLAS:
        op.execute(f"DELETE FROM {tabla} WHERE bgp_session_id IS NULL")  # noqa: S608
        op.drop_constraint(f"ck_{tabla}_una_sola_fuente", tabla)
        op.alter_column(tabla, "bgp_session_id", existing_type=sa.Uuid(), nullable=False)
        op.drop_index(f"ix_{tabla}_route_server_peer_id", tabla)
        op.drop_constraint(f"fk_{tabla}_route_server_peer_id", tabla)
        op.drop_column(tabla, "route_server_peer_id")
