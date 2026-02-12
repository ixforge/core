"""VLAN model."""

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.models.base import (
    Base,
    ExtraDataMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKey,
)


class VLAN(UUIDPrimaryKey, TenantMixin, TimestampMixin, ExtraDataMixin, Base):
    __tablename__ = "vlans"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    vid: Mapped[int] = mapped_column(Integer, nullable=False, comment="VLAN ID")
    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="production, quarantine, management, other",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
