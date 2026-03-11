"""Move port fields to connection and drop ports table

Revision ID: c5a1e8f34d02
Revises: b79735bb9c91
Create Date: 2026-03-09
"""

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c5a1e8f34d02"
down_revision: Union[str, None] = "b79735bb9c91"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # Agregar columnas nuevas a connections (nullable temporalmente)
    op.add_column("connections", sa.Column("name", sa.String(100), nullable=True))
    op.add_column("connections", sa.Column("switch_id", sa.Uuid(), nullable=True))

    # Migrar datos desde ports
    op.execute(
        "UPDATE connections SET name = p.name, switch_id = p.switch_id, speed = p.speed "
        "FROM ports p WHERE connections.port_id = p.id"
    )

    # Fallback para connections sin port asignado (dev environment)
    op.execute(
        "UPDATE connections SET "
        "name = 'unassigned-' || LEFT(connections.id::text, 8), "
        "switch_id = COALESCE(switch_id, (SELECT id FROM switches LIMIT 1)), "
        "speed = COALESCE(speed, 1000) "
        "WHERE name IS NULL"
    )

    # Marcar columnas como NOT NULL
    op.alter_column("connections", "name", nullable=False)
    op.alter_column("connections", "speed", nullable=False)
    op.alter_column("connections", "switch_id", nullable=False)

    # FK y constraints nuevos
    op.create_foreign_key(
        "fk_connections_switch_id",
        "connections",
        "switches",
        ["switch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_connections_switch_name", "connections", ["switch_id", "name"]
    )
    op.create_check_constraint(
        "ck_connections_speed_positive", "connections", "speed > 0"
    )
    op.create_index("ix_connections_switch_id", "connections", ["switch_id"])

    # Eliminar FK y columna port_id
    op.drop_constraint("connections_port_id_fkey", "connections", type_="foreignkey")
    op.drop_index("ix_connections_port_id", table_name="connections")
    op.drop_column("connections", "port_id")

    # Eliminar tabla ports y su enum
    op.drop_table("ports")
    op.execute("DROP TYPE IF EXISTS port_type")


def downgrade() -> None:
    # Recrear enum port_type
    port_type = postgresql.ENUM(
        "member", "infra", "unused", name="port_type", create_type=False
    )
    port_type.create(op.get_bind())

    # Recrear tabla ports (estructura minima)
    op.create_table(
        "ports",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("ixp_id", sa.Uuid(), nullable=False),
        sa.Column("switch_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("speed", sa.Integer(), nullable=False),
        sa.Column("type", port_type, nullable=False, server_default="unused"),
        sa.Column("member_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("extra_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["ixp_id"], ["ixps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["switch_id"], ["switches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("switch_id", "name", name="uq_ports_switch_id_name"),
        sa.CheckConstraint("speed > 0", name="ck_ports_speed_positive"),
    )
    op.create_index("ix_ports_switch_id", "ports", ["switch_id"])
    op.create_index("ix_ports_member_id", "ports", ["member_id"])

    # Restaurar port_id en connections
    op.add_column("connections", sa.Column("port_id", sa.Uuid(), nullable=True))
    op.create_index("ix_connections_port_id", "connections", ["port_id"])
    op.create_foreign_key(
        "connections_port_id_fkey", "connections", "ports", ["port_id"], ["id"],
        ondelete="SET NULL",
    )

    # Limpiar columnas y constraints agregados en upgrade
    op.drop_constraint("ck_connections_speed_positive", "connections", type_="check")
    op.drop_constraint("uq_connections_switch_name", "connections", type_="unique")
    op.drop_index("ix_connections_switch_id", table_name="connections")
    op.drop_constraint("fk_connections_switch_id", "connections", type_="foreignkey")
    op.drop_column("connections", "switch_id")
    op.drop_column("connections", "name")
    op.alter_column("connections", "speed", nullable=True)
