"""Custom field definition model."""

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.models.base import (
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKey,
)


class CustomFieldDefinition(UUIDPrimaryKey, TenantMixin, TimestampMixin, Base):
    __tablename__ = "custom_field_definitions"
    __table_args__ = (
        UniqueConstraint(
            "ixp_id",
            "entity_type",
            "field_name",
            name="uq_custom_fields_ixp_entity_field",
        ),
    )

    entity_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="member, connection, port, switch, vlan",
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    field_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="string, integer, boolean, url, email",
    )
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
