from __future__ import annotations

import socket
from unittest.mock import AsyncMock, patch

import pytest

from app.core.ssrf import (
    _check_resolved,
    validate_and_resolve,
    validate_url_not_internal,
    validate_url_not_internal_async,
)


def _resolved(address: str, port: int = 80):
    return [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, port))
    ]


def test_check_resolved_fails_closed_for_malformed_and_blocked_addresses():
    with pytest.raises(ValueError, match="not a valid IP"):
        _check_resolved("example.test", _resolved("not-an-ip"))
    with pytest.raises(ValueError, match="internal IP"):
        _check_resolved("example.test", _resolved("10.0.0.7"))


def test_sync_validation_accepts_public_ip_literal():
    validate_url_not_internal("https://93.184.216.34/resource")


@pytest.mark.asyncio
async def test_async_validation_resolves_public_hostname():
    loop = AsyncMock()
    loop.getaddrinfo.return_value = _resolved("93.184.216.34")
    with patch("app.core.ssrf.asyncio.get_running_loop", return_value=loop):
        await validate_url_not_internal_async("https://example.test")
    loop.getaddrinfo.assert_awaited_once_with("example.test", None)


def test_validate_and_resolve_accepts_literal_and_rejects_empty_hostname():
    assert validate_and_resolve("https://93.184.216.34/path") == [
        ("93.184.216.34", 443)
    ]
    assert validate_and_resolve("http://93.184.216.34:8080/path") == [
        ("93.184.216.34", 8080)
    ]
    with pytest.raises(ValueError, match="no hostname"):
        validate_and_resolve("not-a-url")


def test_validate_and_resolve_rejects_malformed_or_empty_dns_results():
    with patch(
        "app.core.ssrf.socket.getaddrinfo",
        return_value=_resolved("not-an-ip"),
    ):
        with pytest.raises(ValueError, match="unparseable"):
            validate_and_resolve("https://example.test")

    with patch("app.core.ssrf.socket.getaddrinfo", return_value=[]):
        with pytest.raises(ValueError, match="no valid addresses"):
            validate_and_resolve("https://example.test")


def test_validate_and_resolve_returns_all_safe_addresses():
    resolved = _resolved("93.184.216.34", 443) + _resolved("93.184.216.35", 444)
    with patch("app.core.ssrf.socket.getaddrinfo", return_value=resolved):
        assert validate_and_resolve("https://example.test") == [
            ("93.184.216.34", 443),
            ("93.184.216.35", 444),
        ]
