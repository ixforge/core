"""Auth endpoints: login and current-user info."""

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import select

from ixforge.api.deps import CurrentUser, DBSession, IXPId
from ixforge.exceptions import UnauthorizedError
from ixforge.models.user import User
from ixforge.rate_limit import limiter
from ixforge.schemas.auth import LoginRequest, TokenResponse, UserRead
from ixforge.services.auth import create_access_token, hash_password, verify_password
from ixforge.services.events import create_event

auth_router = APIRouter(prefix="/auth", tags=["auth"])

_log = structlog.get_logger()


@auth_router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request, body: LoginRequest, db: DBSession, ixp_id: IXPId
) -> TokenResponse:
    stmt = select(User).where(User.email == body.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        # Dummy hash to equalize timing (prevents user enumeration)
        verify_password("dummy_check", hash_password("dummy_check"))
        _log.warning("auth.login_failed", email=body.email, reason="user_not_found")
        raise UnauthorizedError("Invalid email or password")

    if not verify_password(body.password, user.hashed_password):
        _log.warning(
            "auth.login_failed",
            email=body.email,
            user_id=str(user.id),
            reason="wrong_password",
        )
        raise UnauthorizedError("Invalid email or password")

    if not user.is_active:
        _log.warning(
            "auth.login_failed",
            email=body.email,
            user_id=str(user.id),
            reason="inactive",
        )
        raise UnauthorizedError("Invalid email or password")

    token = create_access_token(subject=str(user.id))

    await create_event(
        db,
        ixp_id=ixp_id,
        event_type="user.login",
        actor_id=user.id,
        resource_type="user",
        resource_id=user.id,
        data={"email": user.email},
    )

    return TokenResponse(access_token=token)


@auth_router.get("/me", response_model=UserRead)
async def get_me(user: CurrentUser) -> User:
    return user
