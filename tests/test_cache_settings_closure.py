from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config.cache import CacheSettings


def test_cache_backend_validator_accepts_all_modes_and_normalizes():
    for backend in ("redis", "memory", "tiered", "none", "nats"):
        settings = CacheSettings(cache_backend=f"  {backend.upper()}  ")
        assert settings.cache_backend == backend
        assert settings.cache_backend_normalized == backend


def test_cache_backend_validator_rejects_unknown_mode():
    with pytest.raises(ValidationError, match="CACHE_BACKEND must be"):
        CacheSettings(cache_backend="filesystem")


def test_revocation_redis_url_validator_rejects_blank_value():
    with pytest.raises(ValidationError, match="REVOCATION_REDIS_URL must not be empty"):
        CacheSettings(revocation_redis_url="   ")


def test_cache_ttl_validators_reject_invalid_values():
    with pytest.raises(ValidationError, match="STATS_CACHE_TTL_SECONDS"):
        CacheSettings(stats_cache_ttl_seconds=0)
    with pytest.raises(ValidationError, match="CACHE_WARMUP_MAX_AGE_SECONDS"):
        CacheSettings(cache_warmup_max_age_seconds=-1)


def test_nats_auth_token_file_is_loaded(monkeypatch):
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as handle:
        handle.write("  token-from-file  \n")
        token_file = Path(handle.name)
    monkeypatch.setenv("NATS_AUTH_TOKEN_FILE", str(token_file))
    try:
        assert (
            CacheSettings(nats_auth_token="fallback").nats_auth_token
            == "token-from-file"
        )
    finally:
        token_file.unlink(missing_ok=True)


def test_nats_auth_token_file_errors_are_validation_errors(monkeypatch):
    missing_file = Path(tempfile.gettempdir()) / f"missing-{uuid.uuid4()}"
    monkeypatch.setenv("NATS_AUTH_TOKEN_FILE", str(missing_file))
    with pytest.raises(ValidationError, match="NATS_AUTH_TOKEN_FILE"):
        CacheSettings(nats_auth_token="fallback")


def test_cache_warmup_properties_coerce_and_deduplicate_values():
    settings = CacheSettings(
        cache_warmup_groups="1, bad, 2, 1",
        cache_warmup_stats_users="3,invalid,4",
        cache_warmup_periods="30D, 90d, , 30d, 7D",
    )
    assert settings.cache_warmup_group_ids == (1, 2, 1)
    assert settings.cache_warmup_stats_user_ids == (3, 4)
    assert settings.cache_warmup_period_keys == ("30d", "90d", "7d")


def test_cache_warmup_properties_handle_empty_and_iterable_inputs():
    settings = CacheSettings(
        cache_warmup_groups=[],
        cache_warmup_stats_users=[],
        cache_warmup_periods=[],
    )
    assert settings.cache_warmup_group_ids == ()
    assert settings.cache_warmup_stats_user_ids == ()
    assert settings.cache_warmup_period_keys == ()
