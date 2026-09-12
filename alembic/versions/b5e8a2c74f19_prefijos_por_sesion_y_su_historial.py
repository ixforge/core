"""prefijos por sesion bgp y su historial

Revision ID: b5e8a2c74f19
Revises: a2f6c91d4e73
Create Date: 2026-09-12

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b5e8a2c74f19"
down_revision: str | None = "a2f6c91d4e73"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "bgp_session_prefixes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ixp_id", sa.Uuid(), nullable=False),
        sa.Column("bgp_session_id", sa.Uuid(), nullable=False),
        sa.Column("prefix", sa.String(length=43), nullable=False),
        sa.Column(
            "as_path",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            comment="Vacio si la ruta no trae el atributo, que no es lo mismo que no anunciarla",
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["bgp_session_id"], ["bgp_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ixp_id"], ["ixps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bgp_session_id", "prefix", name="uq_bgp_session_prefixes_sesion_prefijo"),
    )
    op.create_index("ix_bgp_session_prefixes_bgp_session_id", "bgp_session_prefixes", ["bgp_session_id"])
    op.create_index("ix_bgp_session_prefixes_ixp_id", "bgp_session_prefixes", ["ixp_id"])
    op.create_index("ix_bgp_session_prefixes_prefix", "bgp_session_prefixes", ["prefix"])

    op.create_table(
        "bgp_prefix_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ixp_id", sa.Uuid(), nullable=False),
        sa.Column("bgp_session_id", sa.Uuid(), nullable=False),
        sa.Column("prefix", sa.String(length=43), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum("announced", "withdrawn", "updated", name="prefix_event_type"),
            nullable=False,
        ),
        sa.Column("as_path", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column(
            "previous_as_path",
            postgresql.ARRAY(sa.Integer()),
            nullable=True,
            comment="Solo en updated: con que camino venia antes",
        ),
        # Sin created_at: occurred_at ya es cuando paso, y un evento no se edita
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["bgp_session_id"], ["bgp_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ixp_id"], ["ixps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bgp_prefix_events_bgp_session_id", "bgp_prefix_events", ["bgp_session_id"])
    op.create_index("ix_bgp_prefix_events_ixp_id", "bgp_prefix_events", ["ixp_id"])
    op.create_index("ix_bgp_prefix_events_occurred_at", "bgp_prefix_events", ["occurred_at"])
    op.create_index("ix_bgp_prefix_events_prefix", "bgp_prefix_events", ["prefix"])
    op.create_index(
        "ix_bgp_prefix_events_sesion_fecha", "bgp_prefix_events", ["bgp_session_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_table("bgp_prefix_events")
    op.drop_table("bgp_session_prefixes")
    sa.Enum(name="prefix_event_type").drop(op.get_bind(), checkfirst=True)
