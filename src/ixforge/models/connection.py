"""Connection and ConnectionVLAN models."""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.models.base import Base, ExtraDataMixin, TimestampMixin, UUIDPrimaryKey


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
    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="physical, virtual",
    )
    state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        comment="draft, provisioning, active, disabled, decommissioned",
    )
    mac_address: Mapped[str | None] = mapped_column(String(17), nullable=True)
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
