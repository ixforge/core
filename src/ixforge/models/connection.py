"""Connection and ConnectionVLAN models."""

import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ixforge.enums import ConnectionState, ConnectionType
from ixforge.models.base import Base, ExtraDataMixin, TenantMixin, TimestampMixin, UUIDPrimaryKey
from ixforge.models.types import MACADDR


class Connection(UUIDPrimaryKey, TenantMixin, TimestampMixin, ExtraDataMixin, Base):
    __tablename__ = "connections"

    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    port_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
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
    speed: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Speed in Mbps",
    )

    # Relationships for eager loading display names
    member: Mapped["Member"] = relationship(lazy="raise")  # type: ignore[name-defined]
    port: Mapped["Port | None"] = relationship(lazy="raise")  # type: ignore[name-defined]


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
    tagged: Mapped[bool] = mapped_column(Boolean, nullable=False)
