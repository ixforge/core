"""The rate limit key cannot be chosen by the client"""

from starlette.requests import Request

from ixforge.rate_limit import limiter


def _request(headers: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": headers,
            "client": ("198.51.100.7", 40000),
        }
    )


def test_spoofed_forwarding_header_does_not_change_the_key():
    spoofed = _request([(b"x_forwarded_for", b"203.0.113.9")])

    assert limiter._key_func(spoofed) == "198.51.100.7"


def test_key_is_the_connection_address():
    assert limiter._key_func(_request([])) == "198.51.100.7"
