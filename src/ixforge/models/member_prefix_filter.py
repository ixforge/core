"""Filtros de prefijos y ASN de origen por miembro y familia."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.enums import PrefixFilterSource
from ixforge.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKey
from ixforge.models.types import CIDR


class MemberPrefixFilter(UUIDPrimaryKey, TenantMixin, TimestampMixin, Base):
    """Origen permitido para las rutas de un miembro en una familia

    Un miembro sin fila se comporta como origin_asns = [su propio ASN] y sin
    filtro de prefijos, que es el default seguro. NULL y lista vacia NO son lo
    mismo en prefixes: NULL desactiva el filtro, la lista vacia no autoriza
    ningun prefijo
    """

    __tablename__ = "member_prefix_filters"
    __table_args__ = (
        CheckConstraint("af IN (4, 6)", name="ck_member_prefix_filters_af_valid"),
        UniqueConstraint("member_id", "af", name="uq_member_prefix_filters_member_af"),
    )

    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    af: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Address family: 4 o 6"
    )
    origin_asns: Mapped[list[int] | None] = mapped_column(
        ARRAY(BigInteger),
        nullable=True,
        comment="NULL o vacio significa solo el ASN del miembro",
    )
    prefixes: Mapped[list[str] | None] = mapped_column(
        ARRAY(CIDR),
        nullable=True,
        comment="NULL desactiva el filtro, la lista vacia no autoriza nada",
    )
    as_set: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[PrefixFilterSource] = mapped_column(
        Enum(PrefixFilterSource, name="prefix_filter_source"),
        nullable=False,
        default=PrefixFilterSource.manual,
    )
    last_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
