"""Member model."""

from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.models.base import (
    Base,
    ExtraDataMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKey,
)


class Member(UUIDPrimaryKey, TenantMixin, TimestampMixin, ExtraDataMixin, Base):
    __tablename__ = "members"
    __table_args__ = (UniqueConstraint("ixp_id", "asn", name="uq_members_ixp_id_asn"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str] = mapped_column(String(50), nullable=False)
    asn: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="prospect",
        comment="prospect, provisioning, active, suspended, terminated",
    )
    peering_policy: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="open",
        comment="open, selective, restrictive, no",
    )
    peering_policy_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    peeringdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
