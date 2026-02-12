"""User model."""

import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.enums import UserRole as UserRole
from ixforge.models.base import Base, TimestampMixin, UUIDPrimaryKey


class User(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"),
        nullable=False,
        default=UserRole.member,
    )
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("members.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
