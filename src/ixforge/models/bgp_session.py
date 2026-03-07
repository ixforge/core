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
from ixforge.models.types import INET


class BGPSession(UUIDPrimaryKey, TenantMixin, TimestampMixin, Base):
    __tablename__ = "bgp_sessions"
    __table_args__ = (
        UniqueConstraint(
            "route_server_id", "connection_id", "af",
            name="uq_bgp_sessions_rs_conn_af",
        ),
        CheckConstraint("peer_asn > 0", name="ck_bgp_sessions_peer_asn_positive"),
        Index("ix_bgp_sessions_rs_conn", "route_server_id", "connection_id"),
        CheckConstraint("af IN (4, 6)", name="ck_bgp_sessions_af_valid"),
    )

    route_server_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("route_servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    peer_ip: Mapped[str] = mapped_column(INET, nullable=False)
    peer_asn: Mapped[int] = mapped_column(Integer, nullable=False)
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
    import_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    export_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
