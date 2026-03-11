"""Connection and ConnectionVLAN models."""

import uuid

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ixforge.enums import ConnectionState, ConnectionType
from ixforge.models.base import Base, ExtraDataMixin, TenantMixin, TimestampMixin, UUIDPrimaryKey
from ixforge.models.types import MACADDR


class Connection(UUIDPrimaryKey, TenantMixin, TimestampMixin, ExtraDataMixin, Base):
    __tablename__ = "connections"
    __table_args__ = (
        UniqueConstraint("switch_id", "name", name="uq_connections_switch_name"),
        CheckConstraint("speed > 0", name="ck_connections_speed_positive"),
    )

    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    switch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("switches.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[ConnectionType] = mapped_column(
        Enum(ConnectionType, name="connection_type"),
        nullable=False,
    )
    state: Mapped[ConnectionState] = mapped_column(
        Enum(ConnectionState, name="connection_state"),
        nullable=False,
        default=ConnectionState.draft,
    )
    mac_address: Mapped[str | None] = mapped_column(MACADDR, nullable=True)
    speed: Mapped[int] = mapped_column(Integer, nullable=False, comment="Speed in Mbps")

    # Relationships for eager loading display names — forward refs resolved by SQLAlchemy
    member: Mapped["Member"] = relationship(lazy="raise")  # type: ignore[name-defined]  # noqa: F821


class ConnectionVLAN(UUIDPrimaryKey, TenantMixin, TimestampMixin, Base):
    __tablename__ = "connection_vlans"
    __table_args__ = (
        UniqueConstraint("connection_id", "vlan_id", name="uq_connection_vlans_conn_vlan"),
    )

    connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vlan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("vlans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
