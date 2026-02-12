"""Base model, mixins, and type annotation map."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantMixin:
    ixp_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ixps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class ExtraDataMixin:
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, default=None)
