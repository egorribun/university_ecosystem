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
