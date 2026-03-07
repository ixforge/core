"""VLANMember model: members associated to a private VLAN."""

import uuid

from sqlalchemy import ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKey


class VLANMember(UUIDPrimaryKey, TenantMixin, TimestampMixin, Base):
    __tablename__ = "vlan_members"
    __table_args__ = (
        UniqueConstraint("vlan_id", "member_id", name="uq_vlan_members"),
    )

    vlan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("vlans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True
    )
