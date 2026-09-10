"""euroix parity

Revision ID: 3786dfba4315
Revises: b8c1d2e3f4a5
Create Date: 2026-09-10 14:17:55.395468

Tablas y campos para la paridad euro-ix: filtros de prefijos por miembro,
peers que no pertenecen a un miembro, servidores RTR y la politica RPKI del
route server
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

import ixforge.models.types
from alembic import op

revision: str = "3786dfba4315"
down_revision: str | None = "b8c1d2e3f4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Los enums nuevos se crean explicitamente para que el downgrade los pueda
# borrar. Sin eso, bajar y volver a subir falla con "type already exists"
NEW_ENUMS = (
    ("prefix_filter_source", ("manual", "irr")),
    ("route_server_peer_type", ("upstream", "collector", "special")),
    ("rpki_policy", ("info_only", "reject_invalid")),
    ("rpki_transport", ("tcp", "ssh")),
)

# Estos ya existen en la base desde migraciones anteriores: referenciarlos con
# create_type=False evita que el CREATE TYPE implicito reviente
EXISTING_ADMIN_STATE = postgresql.ENUM(
    "up", "down", name="bgp_admin_state", create_type=False
)
EXISTING_OPER_STATE = postgresql.ENUM(
    "up", "down", "unknown", name="bgp_oper_state", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in NEW_ENUMS:
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.create_table(
        "member_prefix_filters",
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("af", sa.Integer(), nullable=False, comment="Address family: 4 o 6"),
        sa.Column(
            "origin_asns",
            postgresql.ARRAY(sa.BigInteger()),
            nullable=True,
            comment="NULL o vacio significa solo el ASN del miembro",
        ),
        sa.Column(
            "prefixes",
            postgresql.ARRAY(ixforge.models.types.CIDR()),
            nullable=True,
            comment="NULL desactiva el filtro, la lista vacia no autoriza nada",
        ),
        sa.Column("as_set", sa.String(length=255), nullable=True),
        sa.Column(
            "source",
            postgresql.ENUM(
                "manual", "irr", name="prefix_filter_source", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("ixp_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("af IN (4, 6)", name="ck_member_prefix_filters_af_valid"),
        sa.ForeignKeyConstraint(["ixp_id"], ["ixps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "member_id", "af", name="uq_member_prefix_filters_member_af"
        ),
    )
    op.create_index(
        op.f("ix_member_prefix_filters_ixp_id"),
        "member_prefix_filters",
        ["ixp_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_member_prefix_filters_member_id"),
        "member_prefix_filters",
        ["member_id"],
        unique=False,
    )

    op.create_table(
        "route_server_peers",
        sa.Column("route_server_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("peer_ip", ixforge.models.types.INET(), nullable=False),
        sa.Column("peer_asn", sa.Integer(), nullable=False),
        sa.Column(
            "local_asn", sa.Integer(), nullable=True, comment="NULL usa el ASN del IXP"
        ),
        sa.Column("passive", sa.Boolean(), nullable=False),
        sa.Column(
            "peer_type",
            postgresql.ENUM(
                "upstream",
                "collector",
                "special",
                name="route_server_peer_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "mark_community",
            sa.String(length=32),
            nullable=True,
            comment="Forma asn:value",
        ),
        sa.Column("max_prefixes", sa.Integer(), nullable=True),
        sa.Column("admin_state", EXISTING_ADMIN_STATE, nullable=False),
        sa.Column("oper_state", EXISTING_OPER_STATE, nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("ixp_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ixp_id"], ["ixps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["route_server_id"], ["route_servers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "route_server_id", "peer_ip", name="uq_route_server_peers_rs_ip"
        ),
    )
    op.create_index(
        op.f("ix_route_server_peers_ixp_id"),
        "route_server_peers",
        ["ixp_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_route_server_peers_route_server_id"),
        "route_server_peers",
        ["route_server_id"],
        unique=False,
    )

    op.create_table(
        "rpki_servers",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column(
            "route_server_id",
            sa.Uuid(),
            nullable=True,
            comment="NULL aplica a todos los route servers del IXP",
        ),
        sa.Column(
            "transport",
            postgresql.ENUM("tcp", "ssh", name="rpki_transport", create_type=False),
            nullable=False,
        ),
        sa.Column("refresh_time", sa.Integer(), nullable=True),
        sa.Column("retry_time", sa.Integer(), nullable=True),
        sa.Column("expire_time", sa.Integer(), nullable=True),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("ixp_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ixp_id"], ["ixps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["route_server_id"], ["route_servers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ixp_id", "name", name="uq_rpki_servers_ixp_name"),
    )
    op.create_index(
        op.f("ix_rpki_servers_ixp_id"), "rpki_servers", ["ixp_id"], unique=False
    )
    op.create_index(
        op.f("ix_rpki_servers_route_server_id"),
        "rpki_servers",
        ["route_server_id"],
        unique=False,
    )

    # Las tres son NOT NULL sobre una tabla con filas, asi que necesitan
    # server_default para que el ALTER no falle
    op.add_column(
        "route_servers",
        sa.Column(
            "passive_sessions",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
            comment="El route server nunca inicia la conexion BGP",
        ),
    )
    op.add_column(
        "route_servers",
        sa.Column(
            "rpki_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "route_servers",
        sa.Column(
            "rpki_policy",
            postgresql.ENUM(
                "info_only", "reject_invalid", name="rpki_policy", create_type=False
            ),
            server_default="info_only",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("route_servers", "rpki_policy")
    op.drop_column("route_servers", "rpki_enabled")
    op.drop_column("route_servers", "passive_sessions")
    op.drop_index(op.f("ix_rpki_servers_route_server_id"), table_name="rpki_servers")
    op.drop_index(op.f("ix_rpki_servers_ixp_id"), table_name="rpki_servers")
    op.drop_table("rpki_servers")
    op.drop_index(
        op.f("ix_route_server_peers_route_server_id"), table_name="route_server_peers"
    )
    op.drop_index(op.f("ix_route_server_peers_ixp_id"), table_name="route_server_peers")
    op.drop_table("route_server_peers")
    op.drop_index(
        op.f("ix_member_prefix_filters_member_id"), table_name="member_prefix_filters"
    )
    op.drop_index(
        op.f("ix_member_prefix_filters_ixp_id"), table_name="member_prefix_filters"
    )
    op.drop_table("member_prefix_filters")

    bind = op.get_bind()
    for name, _values in NEW_ENUMS:
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
