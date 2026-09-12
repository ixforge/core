"""BGP session model."""

import uuid

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.enums import BGPAdminState, BGPOperState
from ixforge.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKey


class BGPSession(UUIDPrimaryKey, TenantMixin, TimestampMixin, Base):
    __tablename__ = "bgp_sessions"
    __table_args__ = (
        UniqueConstraint(
            "route_server_id", "trunk_vlan_id", "af",
            name="uq_bgp_sessions_rs_trunk_vlan_af",
        ),
        Index("ix_bgp_sessions_rs_trunk_vlan", "route_server_id", "trunk_vlan_id"),
        CheckConstraint("af IN (4, 6)", name="ck_bgp_sessions_af_valid"),
        CheckConstraint(
            "prefixes_imported IS NULL OR prefixes_imported >= 0",
            name="ck_bgp_sessions_prefixes_imported_no_negativo",
        ),
        CheckConstraint(
            "prefixes_exported IS NULL OR prefixes_exported >= 0",
            name="ck_bgp_sessions_prefixes_exported_no_negativo",
        ),
    )

    route_server_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("route_servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trunk_vlan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("trunk_vlans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    admin_state: Mapped[BGPAdminState] = mapped_column(
        Enum(BGPAdminState, name="bgp_admin_state"),
        nullable=False,
        default=BGPAdminState.up,
    )
    oper_state: Mapped[BGPOperState] = mapped_column(
        Enum(BGPOperState, name="bgp_oper_state"),
        nullable=False,
        default=BGPOperState.unknown,
    )
    af: Mapped[int] = mapped_column(Integer, nullable=False, comment="Address family: 4 or 6")
    max_prefixes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Lo ultimo que reporto el agente. Null y no cero cuando la sesion no esta
    # arriba: de un peer caido no se sabe cuantas rutas tiene, y un cero se lee
    # como "conectado sin anunciar nada", que es un problema distinto
    prefixes_imported: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Rutas recibidas del peer segun el ultimo reporte",
    )
    prefixes_exported: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Rutas anunciadas al peer segun el ultimo reporte",
    )
