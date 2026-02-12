"""Member model."""

from sqlalchemy import CheckConstraint, Enum, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.enums import MemberState, PeeringPolicy
from ixforge.models.base import (
    Base,
    ExtraDataMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKey,
)


class Member(UUIDPrimaryKey, TenantMixin, TimestampMixin, ExtraDataMixin, Base):
    __tablename__ = "members"
    __table_args__ = (
        UniqueConstraint("ixp_id", "asn", name="uq_members_ixp_id_asn"),
        CheckConstraint("asn > 0", name="ck_members_asn_positive"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str] = mapped_column(String(50), nullable=False)
    asn: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[MemberState] = mapped_column(
        Enum(MemberState, name="member_state"),
        nullable=False,
        default=MemberState.prospect,
    )
    peering_policy: Mapped[PeeringPolicy] = mapped_column(
        Enum(PeeringPolicy, name="peering_policy"),
        nullable=False,
        default=PeeringPolicy.open,
    )
    peering_policy_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    peeringdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
