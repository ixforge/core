"""Event model."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.models.base import Base, TenantMixin, UUIDPrimaryKey


class Event(UUIDPrimaryKey, TenantMixin, Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_type_ixp", "type", "ixp_id"),)

    type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Event type, e.g. member.created",
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
