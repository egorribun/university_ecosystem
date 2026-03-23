"""RZ-W16-08: Tests for SSRF blocklist validation."""

from __future__ import annotations

import pytest

from app.core.ssrf import validate_url_not_internal


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

    def test_dns_failure_is_not_ssrf(self) -> None:
        # Non-existent domain — DNS failure should pass (not SSRF).
        validate_url_not_internal(
            "https://this-domain-does-not-exist-xyzzy.example.com/"
        )
