"""Tests for auth service: JWT issuer validation."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt as jose_jwt

from ixforge.config import get_settings
from ixforge.exceptions import UnauthorizedError
from ixforge.services.auth import decode_access_token


class TestJWTIssuerValidation:
    def test_decode_token_with_wrong_issuer_rejected(self):
        """Token con iss diferente debe ser rechazado"""
        settings = get_settings()
        token = jose_jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "exp": datetime.now(UTC) + timedelta(minutes=5),
                "iss": "evil-issuer",
            },
            settings.secret_key,
            algorithm="HS256",
        )
        with pytest.raises(UnauthorizedError):
            decode_access_token(token)

    def test_decode_token_without_issuer_rejected(self):
        """Token sin iss debe ser rechazado"""
        settings = get_settings()
        token = jose_jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "exp": datetime.now(UTC) + timedelta(minutes=5),
            },
            settings.secret_key,
            algorithm="HS256",
        )
        with pytest.raises(UnauthorizedError):
            decode_access_token(token)
