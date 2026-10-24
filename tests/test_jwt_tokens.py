"""Access tokens keep their wire format across JWT libraries and reject tampering"""

import pytest

from ixforge.exceptions import UnauthorizedError
from ixforge.services.auth import create_access_token, decode_access_token

SUBJECT = "00000000-0000-4000-8000-000000000001"
PAYLOAD = (
    "eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTQwMDAtODAwMC0wMDAwMDAwMDAwMDEiLCJleHAiOjQwNzA5MDg4MDAs"
    "ImlzcyI6Iml4Zm9yZ2UtY29yZSJ9"
)

# Signed by python-jose 3.5.0 with the test secret, before the switch to PyJWT
ISSUED_BY_PREVIOUS_LIBRARY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    + PAYLOAD
    + ".fK0W8HuZf2Kh9dl9elck-4RZdkF8OUawmyjnGSLpHcI"
)
EXPIRED = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTQwMDAtODAwMC0wMDAwMDAwMDAwMDEiLCJleHAiOjk0NjY4NDgwMCwi"
    "aXNzIjoiaXhmb3JnZS1jb3JlIn0.LAxUmMNwEtD6bTRZQIlCyHG0JHZNav4MC397NpW8ohI"
)
SIGNED_WITH_ANOTHER_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    + PAYLOAD
    + ".u_D4DweNMaN5-f1hdkQyuqSXCPVZCPfJGzURDRem0uI"
)
ANOTHER_ISSUER = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTQwMDAtODAwMC0wMDAwMDAwMDAwMDEiLCJleHAiOjQwNzA5MDg4MDAs"
    "ImlzcyI6InNvbWVvbmUtZWxzZSJ9.Zh1AYaj0JU_u_s3bijDGpA29tFPHvDXG5llYCo36itU"
)
ANOTHER_ALGORITHM = (
    "eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9."
    + PAYLOAD
    + ".03SAC9vumryDVnEEHP2-yswxSCq8wm99yi7cZM4_MRcBHqzWSYDY5FZkZq4HpSpfOICBZjwc5V5MLOa0350LgQ"
)
UNSIGNED = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0." + PAYLOAD + "."


def test_token_issued_before_the_library_switch_is_still_valid():
    assert decode_access_token(ISSUED_BY_PREVIOUS_LIBRARY) == SUBJECT


def test_a_new_token_round_trips():
    assert decode_access_token(create_access_token(SUBJECT)) == SUBJECT


@pytest.mark.parametrize(
    "token",
    [EXPIRED, SIGNED_WITH_ANOTHER_KEY, ANOTHER_ISSUER, ANOTHER_ALGORITHM, UNSIGNED, "not-a-jwt"],
    ids=["expired", "another-key", "another-issuer", "another-algorithm", "unsigned", "garbage"],
)
def test_tampered_or_foreign_tokens_are_rejected(token: str):
    with pytest.raises(UnauthorizedError):
        decode_access_token(token)
