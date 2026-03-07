"""User management endpoints (admin only)."""

import uuid
from typing import Any

from fastapi import APIRouter, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ixforge.api.deps import AdminUser, CurrentUser, DBSession
from ixforge.exceptions import ConflictError, NotFoundError
from ixforge.models.api_key import APIKey
from ixforge.models.user import User, UserRole
from ixforge.schemas.auth import (
    APIKeyCreate,
    APIKeyCreateResponse,
    APIKeyRead,
    UserCreate,
    UserRead,
    UserUpdate,
)
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.services.auth import generate_api_key, hash_password
from ixforge.services.base import paginate

users_router = APIRouter(prefix="/users", tags=["users"])


@users_router.get("", response_model=CursorPage[UserRead])
async def list_users(
    db: DBSession,
    _admin: AdminUser,
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> CursorPage[UserRead]:
    stmt = select(User)
    return await paginate(
        db, stmt, CursorParams(cursor=cursor, limit=limit),
        User.created_at, User.id, UserRead,
    )


@users_router.post("", response_model=UserRead, status_code=201)
async def create_user(body: UserCreate, db: DBSession, _admin: AdminUser) -> User:
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
        phone=body.phone,
        position=body.position,
        pgp_key=body.pgp_key,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ConflictError(f"User with email {body.email} already exists") from exc
    return user


@users_router.get("/me", response_model=UserRead)
async def get_me(user: CurrentUser) -> User:
    """Return the currently authenticated user."""
    return user


@users_router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: uuid.UUID, db: DBSession, _admin: AdminUser) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("User", str(user_id))
    return user


@users_router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, db: DBSession, admin: AdminUser
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("User", str(user_id))

    update_data = body.model_dump(exclude_unset=True)

    # Prevent self-deactivation or self-demotion
    if admin.id == user_id:
        if update_data.get("is_active") is False:
            raise ConflictError("Cannot deactivate your own account")
        if update_data.get("role") is not None and update_data["role"] != UserRole.admin:
            raise ConflictError("Cannot demote your own admin role")

    # Prevent leaving the system without active admins
    if (
        user.role == UserRole.admin
        and user.is_active
        and (
            update_data.get("is_active") is False
            or (update_data.get("role") is not None and update_data["role"] != UserRole.admin)
        )
    ):
        active_admin_count = await db.scalar(
            select(func.count()).select_from(User).where(
                User.role == UserRole.admin,
                User.is_active.is_(True),
            )
        )
        if (active_admin_count or 0) <= 1:
            raise ConflictError("Cannot deactivate or demote the last active admin")

    for field, value in update_data.items():
        setattr(user, field, value)

    try:
        await db.flush()
    except IntegrityError as exc:
        raise ConflictError("A user with that email already exists") from exc
    return user


@users_router.post("/{user_id}/api-keys", response_model=APIKeyCreateResponse, status_code=201)
async def create_api_key(
    user_id: uuid.UUID, body: APIKeyCreate, db: DBSession, _admin: AdminUser
) -> dict[str, Any]:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("User", str(user_id))

    raw_key, key_hash, prefix = generate_api_key()
    api_key = APIKey(
        key_hash=key_hash,
        prefix=prefix,
        name=body.name,
        scopes=body.scopes,
        user_id=user_id,
    )
    db.add(api_key)
    await db.flush()

    return {
        "id": api_key.id,
        "prefix": api_key.prefix,
        "name": api_key.name,
        "scopes": api_key.scopes,
        "is_active": api_key.is_active,
        "last_used_at": api_key.last_used_at,
        "created_at": api_key.created_at,
        "raw_key": raw_key,
    }


@users_router.get("/{user_id}/api-keys", response_model=CursorPage[APIKeyRead])
async def list_api_keys(
    user_id: uuid.UUID,
    db: DBSession,
    _admin: AdminUser,
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> CursorPage[APIKeyRead]:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("User", str(user_id))

    stmt = select(APIKey).where(APIKey.user_id == user_id)
    return await paginate(
        db, stmt, CursorParams(cursor=cursor, limit=limit),
        APIKey.created_at, APIKey.id, APIKeyRead,
    )


@users_router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID, db: DBSession, admin: AdminUser
) -> Response:
    """Hard delete an inactive user (admin only). Cannot delete self or the last admin."""
    if user_id == admin.id:
        raise ConflictError("Cannot delete your own account")

    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("User", str(user_id))

    if user.is_active:
        raise ConflictError("Cannot delete an active user. Deactivate first.")

    await db.delete(user)
    await db.flush()
    return Response(status_code=204)
