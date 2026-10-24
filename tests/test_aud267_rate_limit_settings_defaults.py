from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.config.mixins.rate_limit_settings import RateLimitSettingsMixin


class _RateLimitSettings(RateLimitSettingsMixin, BaseModel):
    environment: str = "development"
    model_config = ConfigDict(validate_default=True)


def test_rate_limit_defaults_keep_local_memory_mode() -> None:
    settings = _RateLimitSettings()

    assert settings.environment == "development"
    assert settings.rate_limit_storage_backend == "memory"
    assert settings.rate_limit_storage_uri == "memory://"


def test_explicit_memory_backend_remains_available_in_development() -> None:
    settings = _RateLimitSettings(rate_limit_storage_backend=" MEMORY ")

    assert settings.rate_limit_storage_backend == "memory"
    assert settings.rate_limit_storage_uri == "memory://"


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_deployed_environments_require_redis_backend(environment: str) -> None:
    with pytest.raises(ValidationError, match="RATE_LIMIT_STORAGE_BACKEND"):
        _RateLimitSettings(environment=environment)


@pytest.mark.parametrize(
    ("environment", "backend", "uri"),
    [
        ("development", " REDIS ", "redis://rate-limit.test.invalid:6379/1"),
        ("staging", "redis", "redis://rate-limit.test.invalid:6379/1"),
        ("production", "redis", "rediss://rate-limit.test.invalid:6379/1"),
    ],
)
def test_redis_backend_accepts_redis_uri_configuration(
    environment: str, backend: str, uri: str
) -> None:
    settings = _RateLimitSettings(
        environment=environment,
        rate_limit_storage_backend=backend,
        rate_limit_storage_uri=uri,
    )

    assert settings.rate_limit_storage_backend == "redis"
    assert settings.rate_limit_storage_uri == uri


def test_redis_backend_rejects_default_memory_uri() -> None:
    with pytest.raises(ValidationError, match="RATE_LIMIT_STORAGE_URI"):
        _RateLimitSettings(rate_limit_storage_backend="redis")


@pytest.mark.parametrize(
    "uri",
    [
        "memory://",
        "https://redis.internal",
        "redis://",
        "redis://rate-limit.test.invalid:invalid/1",
    ],
)
def test_redis_backend_rejects_invalid_uri(uri: str) -> None:
    with pytest.raises(ValidationError, match="RATE_LIMIT_STORAGE_URI"):
        _RateLimitSettings(
            rate_limit_storage_backend="redis",
            rate_limit_storage_uri=uri,
        )


def test_rate_limit_backend_rejects_unsupported_value() -> None:
    with pytest.raises(ValidationError, match="RATE_LIMIT_STORAGE_BACKEND"):
        _RateLimitSettings(rate_limit_storage_backend="postgres")


def test_rate_limit_views_handle_default_and_empty_values() -> None:
    settings = _RateLimitSettings()
    empty_sensitive = _RateLimitSettings(rate_limit_sensitive="  ")

    assert settings.rate_limit_default_list == ["200/minute"]
    assert settings.rate_limit_sensitive_value == "5/minute"
    assert empty_sensitive.rate_limit_sensitive_value is None
