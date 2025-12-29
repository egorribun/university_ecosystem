"""Tests for AuthService helper functions.

Only tests that work without complex async mocking.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.auth_service import _hash_token


# ============================================================
# Helper function tests
# ============================================================


def test_hash_token():
    """Test token hashing produces consistent results."""
    token = "test_token_123"
    hash1 = _hash_token(token)
    hash2 = _hash_token(token)
    assert hash1 == hash2
    assert hash1 != token


def test_hash_token_different_inputs():
    """Test different tokens produce different hashes."""
    hash1 = _hash_token("token1")
    hash2 = _hash_token("token2")
    assert hash1 != hash2


def test_hash_token_empty():
    """Test hashing empty token."""
    result = _hash_token("")
    assert result != ""
    assert len(result) == 64  # SHA256 hex digest


def test_hash_token_unicode():
    """Test hashing unicode token."""
    result = _hash_token("токен_123")
    assert len(result) == 64
