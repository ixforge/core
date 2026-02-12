"""IXP model."""

from typing import Any

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.models.base import Base, TimestampMixin, UUIDPrimaryKey


class IXP(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "ixps"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    asn: Mapped[int] = mapped_column(Integer, nullable=False)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    peeringdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, default=None)
