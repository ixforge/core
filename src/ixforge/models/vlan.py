"""VLAN model."""

from sqlalchemy import Enum, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.enums import VLANType
from ixforge.models.base import (
    Base,
    ExtraDataMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKey,
)


class VLAN(UUIDPrimaryKey, TenantMixin, TimestampMixin, ExtraDataMixin, Base):
    __tablename__ = "vlans"
    __table_args__ = (UniqueConstraint("ixp_id", "vid", name="uq_vlans_ixp_id_vid"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    vid: Mapped[int] = mapped_column(Integer, nullable=False, comment="VLAN ID")
    type: Mapped[VLANType] = mapped_column(
        Enum(VLANType, name="vlan_type"),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
