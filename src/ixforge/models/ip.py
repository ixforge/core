"""IP pool and assignment models."""

import uuid

from sqlalchemy import ForeignKey, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.models.base import Base, TimestampMixin, UUIDPrimaryKey
from ixforge.models.types import CIDR, INET


class IPPool(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "ip_pools"

    vlan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("vlans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    network: Mapped[str] = mapped_column(CIDR, nullable=False, comment="CIDR notation")
    gateway: Mapped[str] = mapped_column(INET, nullable=False, comment="Gateway address")
    af: Mapped[int] = mapped_column(Integer, nullable=False, comment="Address family: 4 or 6")


class IPAssignment(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "ip_assignments"

    pool_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ip_pools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    address: Mapped[str] = mapped_column(
        INET,
        unique=True,
        nullable=False,
        comment="IP address",
    )
