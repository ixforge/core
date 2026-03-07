"""RouteServerVLAN association model."""

import uuid

from sqlalchemy import ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKey


class RouteServerVLAN(UUIDPrimaryKey, TenantMixin, TimestampMixin, Base):
    __tablename__ = "route_server_vlans"
    __table_args__ = (
        UniqueConstraint("route_server_id", "vlan_id", name="uq_route_server_vlans"),
    )

    route_server_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("route_servers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vlan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("vlans.id", ondelete="CASCADE"), nullable=False, index=True
    )
