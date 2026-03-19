"""Setup service: initial IXP and admin user creation."""

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import ConflictError
from ixforge.models.ixp import IXP
from ixforge.models.user import User, UserRole
from ixforge.schemas.setup import SetupRequest
from ixforge.services.auth import hash_password


async def run_setup(session: AsyncSession, data: SetupRequest) -> None:
    """Create the initial IXP and admin user.

    Uses an advisory lock to prevent concurrent setup calls.
    Raises ConflictError if an IXP already exists.
    """
    await session.execute(text("SELECT pg_advisory_xact_lock(1)"))

    count = await session.scalar(select(func.count()).select_from(IXP))
    if count and count > 0:
        raise ConflictError("IXP already configured")

    ixp = IXP(
        id=uuid.uuid4(),
        name=data.ixp.name,
        short_name=data.ixp.short_name,
        asn=data.ixp.asn,
        website=data.ixp.website,
        country=data.ixp.country,
        city=data.ixp.city,
    )
    session.add(ixp)
    await session.flush()

    user = User(
        id=uuid.uuid4(),
        email=data.admin.email,
        hashed_password=hash_password(data.admin.password),
        full_name=data.admin.full_name,
        role=UserRole.admin,
        is_active=True,
    )
    session.add(user)
    await session.flush()


async def is_configured(session: AsyncSession) -> bool:
    """Return True if at least one IXP exists."""
    count = await session.scalar(select(func.count()).select_from(IXP))
    return bool(count and count > 0)
