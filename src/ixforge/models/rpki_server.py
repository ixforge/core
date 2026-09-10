"""Servidores RTR para validacion RPKI."""

import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.enums import RPKITransport
from ixforge.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKey


class RPKIServer(UUIDPrimaryKey, TenantMixin, TimestampMixin, Base):
    __tablename__ = "rpki_servers"
    __table_args__ = (UniqueConstraint("ixp_id", "name", name="uq_rpki_servers_ixp_name"),)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=3323)
    route_server_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("route_servers.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="NULL aplica a todos los route servers del IXP",
    )
    transport: Mapped[RPKITransport] = mapped_column(
        Enum(RPKITransport, name="rpki_transport"),
        nullable=False,
        default=RPKITransport.tcp,
    )
    refresh_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expire_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
