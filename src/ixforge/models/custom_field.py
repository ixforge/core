"""Custom field definition model."""

from sqlalchemy import Boolean, Enum, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.enums import CustomFieldEntityType, CustomFieldType
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

    entity_type: Mapped[CustomFieldEntityType] = mapped_column(
        Enum(CustomFieldEntityType, name="custom_field_entity_type"),
        nullable=False,
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    field_type: Mapped[CustomFieldType] = mapped_column(
        Enum(CustomFieldType, name="custom_field_type"),
        nullable=False,
    )
    is_required: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
