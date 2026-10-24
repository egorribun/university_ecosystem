"""AUD-362 regression cases for unspecified IPv6 SSRF targets."""

from __future__ import annotations

import asyncio
import socket
from unittest.mock import AsyncMock, patch

import pytest

from app.core.ssrf import (
    validate_and_resolve,
    validate_public_https_url,
    validate_url_not_internal,
    validate_url_not_internal_async,
)

UNSPECIFIED_URL = "https://[::]/resource"
PUBLIC_IPV6 = "2606:4700:4700::1111"


def _resolved_ipv6(
    address: str, port: int = 443
) -> list[tuple[socket.AddressFamily, int, int, str, tuple[str, int, int, int]]]:
    return [
        (
            socket.AF_INET6,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            (address, port, 0, 0),
        )
    ]


def test_public_https_validator_rejects_unspecified_ipv6_literal() -> None:
    with pytest.raises(ValueError, match="private/reserved address"):
        validate_public_https_url(UNSPECIFIED_URL)


def test_sync_validator_rejects_unspecified_ipv6_literal_without_dns() -> None:
    with patch(
        "app.core.ssrf.socket.getaddrinfo", return_value=_resolved_ipv6(PUBLIC_IPV6)
    ) as resolver:
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_url_not_internal(UNSPECIFIED_URL)
    resolver.assert_not_called()


def test_async_validator_rejects_unspecified_ipv6_literal_without_dns() -> None:
    loop = AsyncMock()
    loop.getaddrinfo.return_value = _resolved_ipv6(PUBLIC_IPV6)
    with patch("app.core.ssrf.asyncio.get_running_loop", return_value=loop):
        with pytest.raises(ValueError, match="SSRF blocked"):
            asyncio.run(validate_url_not_internal_async(UNSPECIFIED_URL))
    loop.getaddrinfo.assert_not_awaited()


def test_resolver_rejects_unspecified_ipv6_literal_without_dns() -> None:
    with patch(
        "app.core.ssrf.socket.getaddrinfo", return_value=_resolved_ipv6(PUBLIC_IPV6)
    ) as resolver:
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_and_resolve(UNSPECIFIED_URL)
    resolver.assert_not_called()


def test_sync_and_resolver_reject_unspecified_ipv6_dns_answers() -> None:
    with patch(
        "app.core.ssrf.socket.getaddrinfo", return_value=_resolved_ipv6("::")
    ) as resolver:
        with pytest.raises(ValueError, match="internal IP ::"):
            validate_url_not_internal("https://example.test/resource")
        resolver.assert_called_once_with("example.test", None)

    with patch(
        "app.core.ssrf.socket.getaddrinfo", return_value=_resolved_ipv6("::")
    ) as resolver:
        with pytest.raises(ValueError, match="internal IP ::"):
            validate_and_resolve("https://example.test/resource")
        resolver.assert_called_once_with("example.test", 443, proto=socket.IPPROTO_TCP)


def test_async_validator_rejects_unspecified_ipv6_dns_answer() -> None:
    loop = AsyncMock()
    loop.getaddrinfo.return_value = _resolved_ipv6("::")
    with patch("app.core.ssrf.asyncio.get_running_loop", return_value=loop):
        with pytest.raises(ValueError, match="internal IP ::"):
            asyncio.run(
                validate_url_not_internal_async("https://example.test/resource")
            )
    loop.getaddrinfo.assert_awaited_once_with("example.test", None)


def test_global_ipv6_remains_allowed() -> None:
    public_url = f"https://[{PUBLIC_IPV6}]/resource"
    validate_public_https_url(public_url)
    validate_url_not_internal(public_url)
    assert validate_and_resolve(public_url) == [(PUBLIC_IPV6, 443)]


def test_async_validator_allows_global_ipv6_literal() -> None:
    asyncio.run(validate_url_not_internal_async(f"https://[{PUBLIC_IPV6}]/resource"))
