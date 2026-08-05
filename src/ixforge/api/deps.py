"""FastAPI dependencies (auth, db session, pagination, IXP resolution)."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.database import get_db, tenant_context
from ixforge.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from ixforge.models.api_key import APIKey
from ixforge.models.ixp import IXP
from ixforge.models.user import User, UserRole
from ixforge.services.auth import decode_access_token, hash_api_key

_bearer_scheme = HTTPBearer(auto_error=False)
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    """Yield an async database session. Re-exports get_db from database module."""
    async for session in get_db():
        yield session


DBSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user(
    request: Request,
    db: DBSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> User:
    """Resolve the current user from a Bearer JWT or a scoped API key.

    Una API key solo autentica el endpoint si tiene el scope granular que le
    corresponde (``<recurso>:read`` / ``<recurso>:write``, derivado del path y el
    metodo). Ademas se devuelve el usuario dueno, asi que los checks de rol de mas
    abajo siguen aplicando: la key nunca puede pasar de sus scopes NI del rol de su
    usuario (doble candado). Una key sin el scope requerido recibe 403
    """
    if credentials is not None:
        return await _resolve_jwt_user(db, credentials.credentials)

    if x_api_key is not None:
        return await _resolve_scoped_api_key_user(db, x_api_key, request)

    raise UnauthorizedError("Missing authentication credentials")


def _required_scope(request: Request) -> str | None:
    """Derive the ``<recurso>:<accion>`` scope required for this request.

    Returns None if the path is not a scoped management resource
    """
    parts = request.url.path.strip("/").split("/")
    # se espera ['api', 'v1', '<recurso>', ...]
    if len(parts) < 3 or parts[0] != "api" or parts[1] != "v1":
        return None
    resource = parts[2]
    action = "read" if request.method in _READ_METHODS else "write"
    return f"{resource}:{action}"


async def _resolve_scoped_api_key_user(db: AsyncSession, raw_key: str, request: Request) -> User:
    key_hash = hash_api_key(raw_key)
    stmt = select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active.is_(True))
    api_key = (await db.execute(stmt)).scalar_one_or_none()

    if api_key is None:
        raise UnauthorizedError("Invalid API key")
    if api_key.user_id is None:
        raise UnauthorizedError("API key is not associated with a user")

    required = _required_scope(request)
    if required is None or required not in api_key.scopes:
        raise ForbiddenError(f"API key missing required scope: {required or 'unknown'}")

    api_key.last_used_at = datetime.now(UTC)

    user = await db.get(User, api_key.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return user


async def _resolve_jwt_user(db: AsyncSession, token: str) -> User:
    user_id_str = decode_access_token(token)
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError as exc:
        raise UnauthorizedError("Invalid token subject") from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role != UserRole.admin:
        raise ForbiddenError("Admin access required")
    return user


async def require_member_or_admin(user: CurrentUser) -> User:
    if user.role not in (UserRole.admin, UserRole.member):
        raise ForbiddenError("Insufficient permissions")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
MemberOrAdminUser = Annotated[User, Depends(require_member_or_admin)]


async def get_ixp_id(db: DBSession) -> uuid.UUID:
    """Resolve the default IXP id (MVP: first IXP in the database).

    Also sets the tenant context so that all subsequent queries in this
    request are automatically filtered by ixp_id (defense-in-depth).
    """
    stmt = select(IXP.id).limit(1)
    result = await db.execute(stmt)
    ixp_id = result.scalar_one_or_none()
    if ixp_id is None:
        raise NotFoundError("IXP", "No IXP configured")
    tenant_context.set(ixp_id)
    return ixp_id


IXPId = Annotated[uuid.UUID, Depends(get_ixp_id)]


async def require_monitoring_scope(
    db: DBSession,
    x_api_key: Annotated[str | None, Header()] = None,
) -> uuid.UUID:
    """Resolve IXP id from an API key with monitoring:read scope."""
    if x_api_key is None:
        raise UnauthorizedError("API key required for monitoring endpoints")

    key_hash = hash_api_key(x_api_key)
    stmt = select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active.is_(True))
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()

    if api_key is None:
        raise UnauthorizedError("Invalid API key")

    if "monitoring:read" not in api_key.scopes:
        raise ForbiddenError("API key missing 'monitoring:read' scope")

    api_key.last_used_at = datetime.now(UTC)

    # Resolve the IXP id and set tenant context
    ixp_stmt = select(IXP.id).limit(1)
    ixp_result = await db.execute(ixp_stmt)
    ixp_id = ixp_result.scalar_one_or_none()
    if ixp_id is None:
        raise NotFoundError("IXP", "No IXP configured")
    tenant_context.set(ixp_id)
    return ixp_id


MonitoringIXPId = Annotated[uuid.UUID, Depends(require_monitoring_scope)]
