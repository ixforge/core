"""Auth endpoints: login and current-user info."""

from fastapi import APIRouter, Request
from sqlalchemy import select

from ixforge.api.deps import CurrentUser, DBSession
from ixforge.exceptions import UnauthorizedError
from ixforge.models.user import User
from ixforge.rate_limit import limiter
from ixforge.schemas.auth import LoginRequest, TokenResponse, UserRead
from ixforge.services.auth import create_access_token, verify_password

auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, db: DBSession) -> TokenResponse:
    stmt = select(User).where(User.email == body.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.hashed_password):
        raise UnauthorizedError("Invalid email or password")

    if not user.is_active:
        raise UnauthorizedError("Account is disabled")

    token = create_access_token(subject=str(user.id))
    return TokenResponse(access_token=token)


@auth_router.get("/me", response_model=UserRead)
async def get_me(user: CurrentUser) -> User:
    return user
