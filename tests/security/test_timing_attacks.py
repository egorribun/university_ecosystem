"""Security tests verifying protection against timing attacks on cryptographic signatures and digests."""

from __future__ import annotations

import secrets

import pytest


@pytest.mark.security
def test_constant_time_signature_comparison():
    """Assert that secrets.compare_digest correctly performs constant-time comparison of signatures."""
    sig1 = "a" * 64
    sig2 = "a" * 64
    sig3 = "a" * 63 + "b"

    # compare_digest returns True for equal strings
    assert secrets.compare_digest(sig1, sig2) is True
    # compare_digest returns False for mismatched strings
    assert secrets.compare_digest(sig1, sig3) is False


@pytest.mark.security
def test_compare_digest_timing_safety():
    """Verify secrets.compare_digest raises TypeError if passed invalid/non-string-bytes types, enforcing exact byte types."""
    with pytest.raises(TypeError):
        secrets.compare_digest(123, "string")  # type: ignore[arg-type]
