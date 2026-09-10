"""Sesiones BGP de un route server que no pertenecen a un miembro."""

import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.enums import BGPAdminState, BGPOperState, RouteServerPeerType
from ixforge.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKey
from ixforge.models.types import INET


class RouteServerPeer(UUIDPrimaryKey, TenantMixin, TimestampMixin, Base):
    """Upstream, colector o peer especial

    No lleva columna af: se deriva de peer_ip. BGPSession si la necesita porque
    cuelga de un trunk_vlan y no de una IP, pero aca guardarla seria una segunda
    fuente de verdad que puede discrepar de la primera
    """

    __tablename__ = "route_server_peers"
    __table_args__ = (
        UniqueConstraint(
            "route_server_id", "peer_ip", name="uq_route_server_peers_rs_ip"
        ),
    )

    route_server_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("route_servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    peer_ip: Mapped[str] = mapped_column(INET, nullable=False)
    peer_asn: Mapped[int] = mapped_column(Integer, nullable=False)
    local_asn: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="NULL usa el ASN del IXP"
    )
    passive: Mapped[bool] = mapped_column(nullable=False, default=True)
    peer_type: Mapped[RouteServerPeerType] = mapped_column(
        Enum(RouteServerPeerType, name="route_server_peer_type"), nullable=False
    )
    mark_community: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="Forma asn:value"
    )
    max_prefixes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    admin_state: Mapped[BGPAdminState] = mapped_column(
        Enum(BGPAdminState, name="bgp_admin_state"),
        nullable=False,
        default=BGPAdminState.up,
    )
    oper_state: Mapped[BGPOperState] = mapped_column(
        Enum(BGPOperState, name="bgp_oper_state"),
        nullable=False,
        default=BGPOperState.unknown,
    )
