from __future__ import annotations

from functools import cached_property

from pydantic import ValidationInfo, field_validator

from .base import _DEVELOPMENT_ENVIRONMENTS, BaseAppSettings


class AppGeneralSettings(BaseAppSettings):
    environment: str = "development"
    auto_create_schema: bool | None = None
    attendance_token_secret: str = ""
    attendance_token_ttl_seconds: int = 300
    session_cleanup_interval_seconds: int = 900
    mfa_challenge_cleanup_interval_seconds: int = 600
    mfa_challenge_cleanup_grace_period_seconds: int = 600
    password_reset_cleanup_interval_seconds: int = 3_600
    password_reset_cleanup_retention_minutes: int = 45
    email_change_cleanup_interval_seconds: int = 3_600
    email_change_cleanup_retention_minutes: int = 45
    password_reset_max_active_tokens: int = 1
    stories_cleanup_enabled: bool = True
    stories_retention_cleanup_interval_seconds: int = 86_400
    privacy_cleanup_interval_seconds: int = 86_400
    session_retention_days: int = 90
    mfa_retention_days: int = 30
    failed_login_retention_days: int = 30
    access_log_retention_days: int = 365
    partition_management_enabled: bool = True
    partition_management_interval_seconds: int = 86400
    enable_metrics_endpoint: bool = False
    metrics_basic_auth_username: str = ""
    metrics_basic_auth_password: str = ""
    metrics_allowlist: str | list[str] = ""

    @field_validator("auto_create_schema", mode="before")
    @classmethod
    def _default_auto_create_schema(
        cls, value: bool | None, info: ValidationInfo
    ) -> bool:
        if value is not None:
            return bool(value)
        environment = str(info.data.get("environment") or "development").lower()
        return environment in _DEVELOPMENT_ENVIRONMENTS

    @cached_property
    def is_development(self) -> bool:
        return str(self.environment).lower() in _DEVELOPMENT_ENVIRONMENTS
