"""Tests for MFA challenge fingerprint binding (RED-03).

Ensures that a challenge token created from one IP/User-Agent cannot be
consumed from a different IP/User-Agent — closing the MFA replay window.
"""

from __future__ import annotations

import pytest

from app.core.fingerprint import extract_request_fingerprint


class TestMfaFingerprintBinding:
    """MFA challenge must be bound to the originating request context."""

    @pytest.mark.asyncio
    async def test_extract_request_fingerprint_consistent(self) -> None:
        """Same IP + UA always produces the same fingerprint."""
        from unittest.mock import MagicMock

        req1 = MagicMock()
        req1.client = MagicMock()
        req1.client.host = "1.2.3.4"
        req1.headers = {"user-agent": "Mozilla/5.0 TestBrowser"}

        req2 = MagicMock()
        req2.client = MagicMock()
        req2.client.host = "1.2.3.4"
        req2.headers = {"user-agent": "Mozilla/5.0 TestBrowser"}

        fp1 = extract_request_fingerprint(req1)
        fp2 = extract_request_fingerprint(req2)

        assert fp1 == fp2, "Same IP+UA must produce the same fingerprint"
        assert len(fp1) == 64, "HMAC-SHA256 32-byte digest = 64 hex chars"

    @pytest.mark.asyncio
    async def test_extract_request_fingerprint_differs_by_ip(self) -> None:
        """Different IPs produce different fingerprints."""
        from unittest.mock import MagicMock

        req_a = MagicMock()
        req_a.client = MagicMock()
        req_a.client.host = "1.2.3.4"
        req_a.headers = {"user-agent": "TestBrowser/1.0"}

        req_b = MagicMock()
        req_b.client = MagicMock()
        req_b.client.host = "9.9.9.9"
        req_b.headers = {"user-agent": "TestBrowser/1.0"}

        assert extract_request_fingerprint(req_a) != extract_request_fingerprint(req_b)

    @pytest.mark.asyncio
    async def test_extract_request_fingerprint_differs_by_ua(self) -> None:
        """Different User-Agents produce different fingerprints."""
        from unittest.mock import MagicMock

        req_a = MagicMock()
        req_a.client = MagicMock()
        req_a.client.host = "1.2.3.4"
        req_a.headers = {"user-agent": "LegitBrowser/1.0"}

        req_b = MagicMock()
        req_b.client = MagicMock()
        req_b.client.host = "1.2.3.4"
        req_b.headers = {"user-agent": "AttackerBot/1.0"}

        assert extract_request_fingerprint(req_a) != extract_request_fingerprint(req_b)

    @pytest.mark.asyncio
    async def test_verify_mfa_fingerprint_no_stored_key_returns_true(self) -> None:
        """If no fingerprint is stored in Redis, verification passes (graceful degradation)."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.core.fingerprint import verify_mfa_fingerprint

        mock_cache = AsyncMock()
        mock_cache.get.return_value = None  # No stored fingerprint

        request = MagicMock()
        request.client = MagicMock()
        request.client.host = "1.2.3.4"
        request.headers = {"user-agent": "TestBrowser/1.0"}

        with patch("app.deps.cache.get_cache_client", return_value=mock_cache):
            result = await verify_mfa_fingerprint(
                request, "valid-challenge-token-abc123"
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_mfa_fingerprint_match_returns_true(self) -> None:
        """Matching fingerprint returns True."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.core.fingerprint import (
            extract_request_fingerprint,
            verify_mfa_fingerprint,
        )

        request = MagicMock()
        request.client = MagicMock()
        request.client.host = "1.2.3.4"
        request.headers = {"user-agent": "TestBrowser/1.0"}

        stored_fp = extract_request_fingerprint(request)
        mock_cache = AsyncMock()
        mock_cache.get.return_value = stored_fp.encode()

        with patch("app.deps.cache.get_cache_client", return_value=mock_cache):
            result = await verify_mfa_fingerprint(
                request, "valid-challenge-token-abc123"
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_mfa_fingerprint_mismatch_returns_false(self) -> None:
        """Mismatched fingerprint (different IP/UA) returns False — replay attack blocked."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.core.fingerprint import verify_mfa_fingerprint

        # Attacker uses different IP
        attacker_request = MagicMock()
        attacker_request.client = MagicMock()
        attacker_request.client.host = "9.9.9.9"  # Different IP
        attacker_request.headers = {"user-agent": "AttackerBot/1.0"}

        # Stored fingerprint was for legitimate user at 1.2.3.4
        from app.core.fingerprint import extract_request_fingerprint

        legit_request = MagicMock()
        legit_request.client = MagicMock()
        legit_request.client.host = "1.2.3.4"
        legit_request.headers = {"user-agent": "LegitBrowser/1.0"}
        legit_fp = extract_request_fingerprint(legit_request)

        mock_cache = AsyncMock()
        mock_cache.get.return_value = legit_fp.encode()

        with patch("app.deps.cache.get_cache_client", return_value=mock_cache):
            result = await verify_mfa_fingerprint(
                attacker_request, "stolen-challenge-token-xyz"
            )

        assert result is False, "Attacker with different IP/UA must be rejected"

    @pytest.mark.asyncio
    async def test_verify_mfa_fingerprint_redis_error_returns_true(self) -> None:
        """Redis unavailability causes graceful degradation (returns True, not error)."""
        from unittest.mock import MagicMock, patch

        from app.core.fingerprint import verify_mfa_fingerprint

        request = MagicMock()
        request.client = MagicMock()
        request.client.host = "1.2.3.4"
        request.headers = {"user-agent": "TestBrowser/1.0"}

        with patch(
            "app.deps.cache.get_cache_client", side_effect=ConnectionError("Redis down")
        ):
            result = await verify_mfa_fingerprint(
                request, "valid-challenge-token-abc123"
            )

        assert result is True, "Redis errors must degrade gracefully, not block auth"
