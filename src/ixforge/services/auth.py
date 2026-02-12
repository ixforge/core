"""Authentication service: password hashing, JWT tokens, API key management."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import cast

import bcrypt
from jose import JWTError, jwt

from ixforge.config import get_settings
from ixforge.exceptions import UnauthorizedError

_ALGORITHM = "HS256"
_TOKEN_EXPIRE_MINUTES = 30
_API_KEY_PREFIX = "ixf_"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def create_access_token(subject: str) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, str | datetime] = {"sub": subject, "exp": expire}
    return cast("str", jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM))


def decode_access_token(token: str) -> str:
    """Decode a JWT and return the subject (user ID). Raises UnauthorizedError on failure."""
    settings = get_settings()
    try:
        payload: dict[str, str] = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
    except JWTError as exc:
        raise UnauthorizedError("Invalid or expired token") from exc

    subject: str | None = payload.get("sub")
    if subject is None:
        raise UnauthorizedError("Token missing subject claim")
    return subject


def generate_api_key() -> tuple[str, str, str]:
    """Generate an API key.

    Returns a tuple of (raw_key, key_hash, prefix).
    The raw_key is shown once to the user; key_hash is stored in the database.
    """
    random_part = secrets.token_hex(32)
    raw_key = f"{_API_KEY_PREFIX}{random_part}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    prefix = raw_key[:12]
    return raw_key, key_hash, prefix


def hash_api_key(raw_key: str) -> str:
    """Hash a raw API key for database lookup."""
    return hashlib.sha256(raw_key.encode()).hexdigest()
