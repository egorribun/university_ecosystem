"""Rate limiting configuration mixin."""

from __future__ import annotations

from functools import cached_property

from pydantic import field_validator

from app.core.config.base import _coerce_str_list


class RateLimitSettingsMixin:
    """Rate limiting thresholds and storage backend configuration.

    All rate limit strings follow the '<count>/<window>' format (e.g. '5/minute').
    The storage backend can be 'memory' (in-process, no external dependency) or
    'redis' (distributed, requires RATE_LIMIT_STORAGE_URI to point at Redis).
    """

    rate_limit_enabled: bool = True
    rate_limit_default: str | list[str] = "200/minute"
    rate_limit_sensitive: str = "5/minute"
    rate_limit_auth: str = "5/minute"
    rate_limit_auth_login: str = "5/minute"
    rate_limit_auth_register: str = "5/minute"
    rate_limit_auth_password_reset: str = "3/minute"
    rate_limit_auth_mfa: str = "5/minute"
    rate_limit_auth_totp: str = "5/minute"
    rate_limit_users_me: str = "120/minute"
    rate_limit_users_avatar: str = "10/minute"
    rate_limit_notifications: str = "120/minute"
    rate_limit_notifications_check: str = "60/minute"
    rate_limit_news: str = "120/minute"
    rate_limit_events: str = "120/minute"
    rate_limit_chat: str = "120/minute"
    rate_limit_stories: str = "120/minute"
    rate_limit_schedule: str = "120/minute"
    rate_limit_interactions: str = "200/minute"
    rate_limit_upload: str = "10/minute"
    rate_limit_admin: str = "100/minute"
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

    @cached_property
    def rate_limit_default_list(self) -> list[str]:
        return _coerce_str_list(self.rate_limit_default)

    @cached_property
    def rate_limit_sensitive_value(self) -> str | None:
        value = str(self.rate_limit_sensitive).strip()
        return value or None
