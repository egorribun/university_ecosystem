"""Closure tests for public rate-limit exception state."""

from types import SimpleNamespace

from app.core.ratelimit.exceptions import (
    RateLimitError,
    RateLimitExceeded,
    RateLimitStorageUnavailable,
)


def test_rate_limit_exceeded_preserves_info_and_message():
    info = SimpleNamespace(retry_after=3)

    error = RateLimitExceeded(info)

    assert isinstance(error, RateLimitError)
    assert error.info is info
    assert str(error) == "Rate limit exceeded"


def test_storage_unavailable_is_a_rate_limit_error():
    error = RateLimitStorageUnavailable("redis offline")

    assert isinstance(error, RateLimitError)
    assert str(error) == "redis offline"
