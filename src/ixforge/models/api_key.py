"""API key model."""

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, CheckConstraint, DateTime, ForeignKey, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.models.base import Base, TimestampMixin, UUIDPrimaryKey


class APIKey(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND route_server_id IS NULL) OR "
            "(user_id IS NULL AND route_server_id IS NOT NULL)",
            name="ck_api_keys_owner_xor",
        ),
    )

    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default=text("'{}'")
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    route_server_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("route_servers.id", ondelete="CASCADE"),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
