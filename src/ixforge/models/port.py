"""Port model."""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.enums import PortType
from ixforge.models.base import Base, ExtraDataMixin, TenantMixin, TimestampMixin, UUIDPrimaryKey


class Port(UUIDPrimaryKey, TenantMixin, TimestampMixin, ExtraDataMixin, Base):
    __tablename__ = "ports"
    __table_args__ = (
        UniqueConstraint("switch_id", "name", name="uq_ports_switch_id_name"),
        CheckConstraint("speed > 0", name="ck_ports_speed_positive"),
    )

    switch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("switches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    speed: Mapped[int] = mapped_column(Integer, nullable=False, comment="Speed in Mbps")
    type: Mapped[PortType] = mapped_column(
        Enum(PortType, name="port_type"),
        nullable=False,
    )
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("members.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
