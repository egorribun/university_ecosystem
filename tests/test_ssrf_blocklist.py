"""RZ-W16-08 / RZ-W17-01: Tests for SSRF blocklist validation."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.ssrf import (
    validate_and_resolve,
    validate_public_https_url,
    validate_url_not_internal,
    validate_url_not_internal_async,
)


class TestSSRFBlocklist:
    """Validates that internal/private IPs are blocked."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://169.254.169.254/latest/meta-data/",  # AWS IMDS
            "http://127.0.0.1:8080/admin",
            "http://10.0.0.1/internal",
            "http://172.16.0.1/",
            "http://192.168.1.1/",
            "http://100.64.0.1/",
            "http://0.0.0.1/",
            "http://[::1]/",
            "http://[::ffff:127.0.0.1]/",
        ],
    )
    def test_blocks_internal_ips(self, url: str) -> None:
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_url_not_internal(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://api.openai.com/v1/embeddings",
            "https://api.spotify.com/v1/me",
            "https://api.pwnedpasswords.com/range/ABCDE",
        ],
    )
    def test_allows_public_urls(self, url: str) -> None:
        # Should not raise
        validate_url_not_internal(url)

    def test_rejects_empty_hostname(self) -> None:
        with pytest.raises(ValueError, match="no hostname"):
            validate_url_not_internal("not-a-url")

    def test_dns_failure_is_fail_closed(self) -> None:
        """RZ-W17-01: DNS failure MUST raise ValueError (fail-closed).

        Previously this was fail-open (silently returned), allowing SSRF when
        an attacker controlled a hostname with intermittent DNS responses.
        """
        import socket

        with patch(
            "app.core.ssrf.socket.getaddrinfo",
            side_effect=socket.gaierror("Name resolution failed"),
        ):
            with pytest.raises(ValueError, match="DNS resolution failed"):
                validate_url_not_internal("https://attacker-controlled.example.com/")

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/push",
            "https://127.0.0.1/push",
            "https://[::1]/push",
            "https://[::ffff:127.0.0.1]/push",
            "https://user%3Apassword@example.com/push",  # pragma: allowlist secret
        ],
    )
    def test_push_endpoint_requires_safe_https_url(self, url: str) -> None:
        with pytest.raises(ValueError):
            validate_public_https_url(url)

    def test_push_endpoint_accepts_provider_hostname(self) -> None:
        validate_public_https_url("https://push.example.com/wpush/v2/token")


class TestValidateAndResolve:
    """RZ-W17-01: Tests for DNS-rebinding-safe resolve function."""

    def test_returns_resolved_addrs_for_ip_literal(self) -> None:
        addrs = validate_and_resolve("https://93.184.216.34:443/path")
        assert len(addrs) >= 1
        assert addrs[0] == ("93.184.216.34", 443)

    def test_blocks_internal_ip_literal(self) -> None:
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_and_resolve("http://127.0.0.1:8080/")

    def test_dns_failure_raises(self) -> None:
        import socket

        with patch(
            "app.core.ssrf.socket.getaddrinfo",
            side_effect=socket.gaierror("Name resolution failed"),
        ):
            with pytest.raises(ValueError, match="DNS resolution failed"):
                validate_and_resolve("https://nonexistent.example.com/")

    def test_blocks_dns_resolving_to_internal(self) -> None:
        """Hostname that resolves to a private IP must be blocked."""
        mock_result = [(2, 1, 6, "", ("10.0.0.1", 443))]
        with patch("app.core.ssrf.socket.getaddrinfo", return_value=mock_result):
            with pytest.raises(ValueError, match="resolves to internal IP"):
                validate_and_resolve("https://evil.attacker.com/")

    def test_returns_port_from_url(self) -> None:
        mock_result = [(2, 1, 6, "", ("93.184.216.34", 8080))]
        with patch("app.core.ssrf.socket.getaddrinfo", return_value=mock_result):
            addrs = validate_and_resolve("http://example.com:8080/")
            assert addrs[0][1] == 8080

    def test_default_https_port(self) -> None:
        mock_result = [(2, 1, 6, "", ("93.184.216.34", 443))]
        with patch("app.core.ssrf.socket.getaddrinfo", return_value=mock_result):
            addrs = validate_and_resolve("https://example.com/")
            assert addrs[0][1] == 443


class TestAsyncSSRFValidation:
    """PERF-W17-01: Tests for async SSRF validation."""

    @pytest.mark.asyncio
    async def test_blocks_internal_ips(self) -> None:
        with pytest.raises(ValueError, match="SSRF blocked"):
            await validate_url_not_internal_async("http://169.254.169.254/")

    @pytest.mark.asyncio
    async def test_allows_public_ips(self) -> None:
        await validate_url_not_internal_async("http://93.184.216.34/")

    @pytest.mark.asyncio
    async def test_dns_failure_is_fail_closed(self) -> None:
        import socket

        with patch("app.core.ssrf.asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = _make_async_raiser(
                socket.gaierror("DNS failed")
            )
            with pytest.raises(ValueError, match="DNS resolution failed"):
                await validate_url_not_internal_async(
                    "https://nonexistent.example.com/"
                )

    @pytest.mark.asyncio
    async def test_rejects_empty_hostname(self) -> None:
        with pytest.raises(ValueError, match="no hostname"):
            await validate_url_not_internal_async("not-a-url")


def _make_async_raiser(exc: Exception):
    """Create an async callable that raises *exc*."""

    async def _raise(*args, **kwargs):
        raise exc

    return _raise
