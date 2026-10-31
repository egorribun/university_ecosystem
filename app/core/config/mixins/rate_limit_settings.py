"""Rate limiting configuration mixin."""

from __future__ import annotations

import unicodedata
from functools import cached_property
from urllib.parse import urlsplit

from pydantic import field_validator, model_validator

from app.core.config.base import _coerce_str_list


class RateLimitSettingsMixin:
    """Rate limiting thresholds and storage backend configuration.

    All rate limit strings follow the '<count>/<window>' format (e.g. '5/minute').
    The storage backend can be 'memory' (process-local, suitable for development/tests) or
    'redis' (requires a valid Redis URI supplied by deployment configuration).
    """

    rate_limit_enabled: bool = True
    rate_limit_default: str | list[str] = "200/minute"
    rate_limit_sensitive: str = "5/minute"
    rate_limit_auth_login: str = "5/minute"
    rate_limit_auth_register: str = "5/minute"
    rate_limit_auth_password_reset: str = "3/minute"
    rate_limit_auth_mfa: str = "5/minute"
    rate_limit_users_me: str = "120/minute"
    rate_limit_users_avatar: str = "10/minute"
    rate_limit_news: str = "120/minute"
    rate_limit_events: str = "120/minute"
    rate_limit_chat: str = "120/minute"
    rate_limit_stories: str = "120/minute"
    rate_limit_interactions: str = "200/minute"
    rate_limit_upload: str = "10/minute"
    rate_limit_websocket: str = "60/minute"
    rate_limit_static: str = "300/minute"
    rate_limit_graphql: str = "30/minute"
    rate_limit_storage_backend: str = "memory"
    rate_limit_storage_uri: str = "memory://"
    rate_limit_headers_enabled: bool = True

    auth_lockout_thresholds: str | list[str] = "5:30,8:300,10:3600"
    auth_lockout_history_minutes: int = 1_440

    @field_validator("rate_limit_storage_backend")
    @classmethod
    def _validate_rate_limit_storage_backend(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"memory", "redis"}:
            raise ValueError("RATE_LIMIT_STORAGE_BACKEND must be 'memory' or 'redis'")
        return normalized

    @model_validator(mode="after")
    def _validate_rate_limit_storage_configuration(self) -> RateLimitSettingsMixin:
        environment = str(getattr(self, "environment", "development")).strip().lower()
        if (
            environment in {"staging", "production"}
            and self.rate_limit_storage_backend != "redis"
        ):
            raise ValueError(
                "RATE_LIMIT_STORAGE_BACKEND must be 'redis' in staging/production"
            )

        if self.rate_limit_storage_backend == "redis":
            raw_uri = self.rate_limit_storage_uri
            if any(
                character.isspace() or unicodedata.category(character) == "Cc"
                for character in raw_uri
            ):
                raise ValueError(
                    "RATE_LIMIT_STORAGE_URI must be a valid Redis URL when "
                    "RATE_LIMIT_STORAGE_BACKEND is redis"
                )
            try:
                parsed_uri = urlsplit(raw_uri)
                is_redis_uri = parsed_uri.scheme.lower() in {"redis", "rediss"}
                has_redis_host = parsed_uri.hostname is not None
                _ = parsed_uri.port
            except ValueError:
                raise ValueError(
                    "RATE_LIMIT_STORAGE_URI must be a valid Redis URL when "
                    "RATE_LIMIT_STORAGE_BACKEND is redis"
                ) from None
            if not is_redis_uri or not has_redis_host:
                raise ValueError(
                    "RATE_LIMIT_STORAGE_URI must be a valid Redis URL when "
                    "RATE_LIMIT_STORAGE_BACKEND is redis"
                )
        return self

    @cached_property
    def rate_limit_default_list(self) -> list[str]:
        return _coerce_str_list(self.rate_limit_default)

    @cached_property
    def rate_limit_sensitive_value(self) -> str | None:
        value = str(self.rate_limit_sensitive).strip()
        return value or None
