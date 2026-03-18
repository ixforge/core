"""Connection model."""

import uuid

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ixforge.enums import ConnectionState, ConnectionType
from ixforge.models.base import Base, ExtraDataMixin, TenantMixin, TimestampMixin, UUIDPrimaryKey


class Connection(UUIDPrimaryKey, TenantMixin, TimestampMixin, ExtraDataMixin, Base):
    __tablename__ = "connections"
    __table_args__ = (
        UniqueConstraint("switch_id", "name", name="uq_connections_switch_name"),
        CheckConstraint("speed > 0", name="ck_connections_speed_positive"),
    )

    trunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("trunks.id", ondelete="CASCADE"),
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
    speed: Mapped[int] = mapped_column(Integer, nullable=False, comment="Speed in Mbps")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    trunk: Mapped["Trunk"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="connections", lazy="raise"
    )
