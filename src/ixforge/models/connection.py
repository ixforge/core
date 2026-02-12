"""Connection and ConnectionVLAN models."""

import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.enums import ConnectionState, ConnectionType
from ixforge.models.base import Base, ExtraDataMixin, TimestampMixin, UUIDPrimaryKey
from ixforge.models.types import MACADDR


class Connection(UUIDPrimaryKey, TimestampMixin, ExtraDataMixin, Base):
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


class ConnectionVLAN(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "connection_vlans"

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
