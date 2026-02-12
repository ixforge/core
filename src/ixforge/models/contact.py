"""Contact model."""

import uuid

from sqlalchemy import Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.enums import ContactRole
from ixforge.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Contact(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "contacts"

    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    role: Mapped[ContactRole] = mapped_column(
        Enum(ContactRole, name="contact_role"),
        nullable=False,
    )
