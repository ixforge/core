"""BGP session model."""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.models.base import Base, TimestampMixin, UUIDPrimaryKey


class BGPSession(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "bgp_sessions"

    route_server_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("route_servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    peer_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    peer_asn: Mapped[int] = mapped_column(Integer, nullable=False)
    admin_state: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="up, down",
    )
    oper_state: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="unknown",
        comment="up, down, unknown",
    )
    af: Mapped[int] = mapped_column(Integer, nullable=False, comment="Address family: 4 or 6")
    max_prefixes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    import_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    export_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
