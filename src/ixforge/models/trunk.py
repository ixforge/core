"""Trunk and TrunkVLAN models."""

import uuid

from sqlalchemy import Enum, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ixforge.enums import TrunkState
from ixforge.models.base import Base, ExtraDataMixin, TenantMixin, TimestampMixin, UUIDPrimaryKey
from ixforge.models.types import MACADDR


class Trunk(UUIDPrimaryKey, TenantMixin, TimestampMixin, ExtraDataMixin, Base):
    __tablename__ = "trunks"
    __table_args__ = (
        UniqueConstraint("ixp_id", "member_id", "name", name="uq_trunks_ixp_member_name"),
    )

    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[TrunkState] = mapped_column(
        Enum(TrunkState, name="trunk_state"),
        nullable=False,
        default=TrunkState.draft,
    )
    mac_address: Mapped[str | None] = mapped_column(MACADDR, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    member: Mapped["Member"] = relationship(lazy="raise")  # type: ignore[name-defined]  # noqa: F821
    connections: Mapped[list["Connection"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="trunk", lazy="raise"
    )
    trunk_vlans: Mapped[list["TrunkVLAN"]] = relationship(
        back_populates="trunk", lazy="raise"
    )


class TrunkVLAN(UUIDPrimaryKey, TenantMixin, TimestampMixin, Base):
    __tablename__ = "trunk_vlans"
    __table_args__ = (
        UniqueConstraint("trunk_id", "vlan_id", name="uq_trunk_vlans_trunk_vlan"),
    )

    trunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("trunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vlan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("vlans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    trunk: Mapped["Trunk"] = relationship(back_populates="trunk_vlans", lazy="raise")
    vlan: Mapped["VLAN"] = relationship(lazy="raise")  # type: ignore[name-defined]  # noqa: F821
