"""ASNCache model: global cache for ASN → name lookups."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.models.base import Base


class ASNCache(Base):
    """Global ASN name cache, shared across all tenants.

    Intentionally omits UUIDPrimaryKey (ASN is the natural key),
    TenantMixin (data is global, not per-IXP),
    and TimestampMixin (fetched_at covers the relevant timestamp).
    """

    __tablename__ = "asn_cache"

    asn: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="UTC timestamp of last PeeringDB fetch",
    )
