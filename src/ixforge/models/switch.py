"""Switch model."""

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.models.base import (
    Base,
    ExtraDataMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKey,
)
from ixforge.models.types import INET


class Switch(UUIDPrimaryKey, TenantMixin, TimestampMixin, ExtraDataMixin, Base):
    __tablename__ = "switches"
    __table_args__ = (UniqueConstraint("ixp_id", "name", name="uq_switches_ixp_id_name"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    management_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    snmp_community_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False
    )
