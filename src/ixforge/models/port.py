"""Port model."""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.models.base import Base, ExtraDataMixin, TimestampMixin, UUIDPrimaryKey


class Port(UUIDPrimaryKey, TimestampMixin, ExtraDataMixin, Base):
    __tablename__ = "ports"

    switch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("switches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    speed: Mapped[int] = mapped_column(Integer, nullable=False, comment="Speed in Mbps")
    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="member, infra, unused",
    )
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("members.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
