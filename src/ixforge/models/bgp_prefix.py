"""Prefijos que cada peer anuncia, y su historial de cambios."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from ixforge.enums import PrefixEventType
from ixforge.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKey


class BGPSessionPrefix(UUIDPrimaryKey, TenantMixin, TimestampMixin, Base):
    """Un prefijo que el peer esta anunciando ahora mismo

    Es un espejo de lo que el agente vio en BIRD, no un historico: lo que el
    peer retira se borra de aca y queda como evento
    """

    __tablename__ = "bgp_session_prefixes"
    __table_args__ = (
        UniqueConstraint("bgp_session_id", "prefix", name="uq_bgp_session_prefixes_sesion_prefijo"),
        UniqueConstraint(
            "route_server_peer_id", "prefix", name="uq_bgp_session_prefixes_peer_prefijo"
        ),
        CheckConstraint(
            "(bgp_session_id IS NULL) <> (route_server_peer_id IS NULL)",
            name="ck_bgp_session_prefixes_una_sola_fuente",
        ),
        Index("ix_bgp_session_prefixes_prefix", "prefix"),
    )

    # Un prefijo cuelga de una sesion de miembro o de un peer del route server,
    # nunca de las dos ni de ninguna: el upstream no tiene sesion de miembro
    # pero sus prefijos se muestran igual
    bgp_session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("bgp_sessions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    route_server_peer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("route_server_peers.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Texto y no cidr: el sitio busca por prefijo con un LIKE por el comienzo, y
    # el valor viene validado como red desde el schema
    prefix: Mapped[str] = mapped_column(String(43), nullable=False)
    as_path: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, default=list,
        comment="Vacio si la ruta no trae el atributo, que no es lo mismo que no anunciarla",
    )
    # Estandar y grandes juntas como texto: "64166:65012" y "64166:1001:1". Es
    # donde el miembro ve por que su prefijo quedo como quedo
    communities: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, default=list,
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class BGPPrefixEvent(UUIDPrimaryKey, TenantMixin, Base):
    """Lo que cambio entre un reporte y el siguiente

    Sin updated_at a proposito: un evento describe un instante y no se edita
    """

    __tablename__ = "bgp_prefix_events"
    __table_args__ = (
        Index("ix_bgp_prefix_events_sesion_fecha", "bgp_session_id", "occurred_at"),
        Index("ix_bgp_prefix_events_peer_fecha", "route_server_peer_id", "occurred_at"),
        CheckConstraint(
            "(bgp_session_id IS NULL) <> (route_server_peer_id IS NULL)",
            name="ck_bgp_prefix_events_una_sola_fuente",
        ),
        Index("ix_bgp_prefix_events_prefix", "prefix"),
    )

    bgp_session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("bgp_sessions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    route_server_peer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("route_server_peers.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    prefix: Mapped[str] = mapped_column(String(43), nullable=False)
    event_type: Mapped[PrefixEventType] = mapped_column(
        Enum(PrefixEventType, name="prefix_event_type"), nullable=False,
    )
    as_path: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False, default=list)
    previous_as_path: Mapped[list[int] | None] = mapped_column(
        ARRAY(Integer), nullable=True,
        comment="Solo en updated: con que camino venia antes",
    )
    communities: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, default=list)
    previous_communities: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(64)), nullable=True,
        comment="Solo en updated: con que communities venia antes",
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True,
    )
