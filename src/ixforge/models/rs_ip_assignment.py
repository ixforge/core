"""RSIPAssignment model: route server IPs allocated from an IP pool."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKey
from ixforge.models.types import INET


class RSIPAssignment(UUIDPrimaryKey, TenantMixin, TimestampMixin, Base):
    __tablename__ = "rs_ip_assignments"
    __table_args__ = (
        UniqueConstraint("route_server_id", "af", name="uq_rs_ip_assignments_rs_af"),
        CheckConstraint("af IN (4, 6)", name="ck_rs_ip_assignments_af_valid"),
    )

    route_server_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("route_servers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pool_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ip_pools.id", ondelete="RESTRICT"),  # pool deletion blocked while RS IPs exist
        nullable=False,
        index=True,
    )
    address: Mapped[str] = mapped_column(INET, unique=True, nullable=False)
    af: Mapped[int] = mapped_column(Integer, nullable=False, comment="Address family: 4 or 6")
