"""User management endpoints (admin only)."""

import uuid
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ixforge.api.deps import AdminUser, DBSession
from ixforge.exceptions import ConflictError, NotFoundError
from ixforge.models.api_key import APIKey
from ixforge.models.user import User
from ixforge.schemas.auth import (
    APIKeyCreate,
    APIKeyCreateResponse,
    APIKeyRead,
    UserCreate,
    UserRead,
    UserUpdate,
)
from ixforge.services.auth import generate_api_key, hash_password

users_router = APIRouter(prefix="/users", tags=["users"])


@users_router.get("", response_model=list[UserRead])
async def list_users(db: DBSession, _admin: AdminUser) -> list[User]:
    stmt = select(User).order_by(User.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@users_router.post("", response_model=UserRead, status_code=201)
async def create_user(body: UserCreate, db: DBSession, _admin: AdminUser) -> User:
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ConflictError(f"User with email {body.email} already exists") from exc
    return user


@users_router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: uuid.UUID, db: DBSession, _admin: AdminUser) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("User", str(user_id))
    return user


@users_router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, db: DBSession, _admin: AdminUser
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("User", str(user_id))

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    try:
        await db.flush()
    except IntegrityError as exc:
        raise ConflictError(f"User with email {body.email} already exists") from exc
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


@users_router.get("/{user_id}/api-keys", response_model=list[APIKeyRead])
async def list_api_keys(user_id: uuid.UUID, db: DBSession, _admin: AdminUser) -> list[APIKey]:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("User", str(user_id))

    stmt = select(APIKey).where(APIKey.user_id == user_id).order_by(APIKey.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())
