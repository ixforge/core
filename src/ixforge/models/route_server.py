"""Route server model."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKey
from ixforge.models.types import INET


class RouteServer(UUIDPrimaryKey, TenantMixin, TimestampMixin, Base):
    __tablename__ = "route_servers"
    __table_args__ = (
        UniqueConstraint("ixp_id", "hostname", name="uq_route_servers_ixp_id_hostname"),
        CheckConstraint("asn > 0", name="ck_route_servers_asn_positive"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_v4: Mapped[str | None] = mapped_column(INET, nullable=True)
    ip_v6: Mapped[str | None] = mapped_column(INET, nullable=True)
    asn: Mapped[int] = mapped_column(Integer, nullable=False)
    software: Mapped[str] = mapped_column(String(50), nullable=False, default="bird")
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    agent_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
