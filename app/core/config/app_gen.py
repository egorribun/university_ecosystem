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
    partition_retention_days: int = 365
    partition_warmup_months: int = 1
    enable_metrics_endpoint: bool = False
    metrics_basic_auth_username: str = ""
    metrics_basic_auth_password: str = ""
    metrics_allowlist: str | list[str] = ""
    monitoring_heavy_probe_enabled: bool = False
    health_storage_probe_enabled: bool = True
    presence_ping_min_interval_seconds: int = 5
    presence_pubsub_enabled: bool = False
    presence_pubsub_channel: str = "presence_updates"

    api_v2_prefix: str = "/api/v2"
    # CFG-2 (audit 2026-03): audit_log_secret is defined and validated in
    # SecuritySettings (with a proper field_validator).  The duplicate here was
    # removed to avoid shadowing that validator if MRO changes.

    # Semantic Search
    semantic_search_enabled: bool = True
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_api_key: str = ""
    embedding_api_base: str = "https://api.openai.com/v1"

    health_storage_probe_min_interval_seconds: int = 3600

    @field_validator("auto_create_schema", mode="before")
    @classmethod
    def _default_auto_create_schema(
        cls, value: bool | str | None, info: ValidationInfo
    ) -> bool:
        if value is not None:
            if isinstance(value, str):
                return value.lower() not in ("false", "0", "no", "off", "")
            return bool(value)
        environment = str(info.data.get("environment") or "development").lower()
        return environment in _DEVELOPMENT_ENVIRONMENTS

    @cached_property
    def is_development(self) -> bool:
        return str(self.environment).lower() in _DEVELOPMENT_ENVIRONMENTS

    @property
    def metrics_allowlist_entries(self) -> list[str]:
        return _coerce_str_list(self.metrics_allowlist)


def _coerce_str_list(values: object) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        items = [item.strip() for item in values.split(",")]
    else:
        from collections.abc import Iterable

        if isinstance(values, Iterable):
            items = [str(item).strip() for item in values]
        else:
            items = [str(values).strip()]
    return [item for item in items if item]
