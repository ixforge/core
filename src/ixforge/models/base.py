"""Base model, mixins, and type annotation map."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Uuid, event, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, with_loader_criteria


class Base(DeclarativeBase):
    pass


@event.listens_for(Session, "do_orm_execute")
def _inject_tenant_filter(execute_state):  # type: ignore[no-untyped-def]
    """Auto-inject ixp_id filter on queries against TenantMixin models.

    Defense-in-depth: ensures all tenant-scoped queries are filtered by the
    current tenant even if the caller forgets to add the WHERE clause.
    Only activates when tenant_context has been set for the current request.
    """
    if execute_state.is_column_load or execute_state.is_relationship_load:
        return

    from ixforge.database import tenant_context

    tenant_id = tenant_context.get()
    if tenant_id is None:
        return

    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            TenantMixin,
            lambda cls: cls.ixp_id == tenant_id,
            include_aliases=True,
        )
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantMixin:
    ixp_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ixps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class ExtraDataMixin:
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, default=None)
