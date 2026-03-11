"""Location model."""

from sqlalchemy import CheckConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKey


class Location(UUIDPrimaryKey, TenantMixin, TimestampMixin, Base):
    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("ixp_id", "name", name="uq_locations_ixp_id_name"),
        CheckConstraint("country ~ '^[A-Z]{2}$'", name="ck_locations_country_iso"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
