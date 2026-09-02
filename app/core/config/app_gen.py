from __future__ import annotations

from functools import cached_property
from typing import Literal, cast

from pydantic import ValidationInfo, field_validator

from .base import _DEVELOPMENT_ENVIRONMENTS, BaseAppSettings, _coerce_str_list

# MOD-W10-03: Full set of accepted environment names.  Any other string causes a
# startup ValidationError — prevents silent "prod" typos being treated as dev.
_VALID_ENVIRONMENTS: frozenset[str] = frozenset(
    _DEVELOPMENT_ENVIRONMENTS | frozenset({"staging", "production"})
)

# A process may only opt out of the security-state Redis capability when it is
# one of the explicitly reviewed, non-authentication workers.  Keeping this
# allowlist here (rather than treating a missing URL as an implicit opt-out)
# makes production configuration fail closed for the API and migration paths.
AppProcessRole = Literal["api", "outbox-worker", "notifications-worker"]
REVOCATION_REDIS_DISABLED_PROCESS_ROLES: frozenset[str] = frozenset(
    {"outbox-worker", "notifications-worker"}
)
_VALID_APP_PROCESS_ROLES: frozenset[str] = frozenset(
    {"api", *REVOCATION_REDIS_DISABLED_PROCESS_ROLES}
)


class AppGeneralSettings(BaseAppSettings):
    environment: str = "development"
    # The deployment manifests set these explicitly for background workers.
    # API/migration processes retain the secure defaults and therefore cannot
    # start with the revocation capability silently disabled.
    app_process_role: AppProcessRole = "api"
    revocation_redis_access_enabled: bool = True
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
    # MED-W19: opt-in flag for X-Response-Time header; disabled by default to
    # avoid leaking internal timing information to external clients in production.
    expose_timing_header: bool = False
    metrics_basic_auth_username: str = ""
    metrics_basic_auth_password: str = ""
    metrics_allowlist: str | list[str] = ""
    monitoring_heavy_probe_enabled: bool = False
    health_storage_probe_enabled: bool = True
    presence_ping_min_interval_seconds: int = 5
    presence_pubsub_enabled: bool = False
    presence_pubsub_channel: str = "presence_updates"

    # TD-14-02 (audit Wave 14): WebSocket connection settings.  Previously
    # accessed via getattr(settings, ..., default) in connection_manager.py,
    # which hid them from IDE autocomplete, type-checking, and .env docs.
    ws_max_connections_per_user: int = 5
    ws_message_rate: float = 5.0
    ws_message_burst: float = 10.0
    # LOW-W19: moved from os.environ.get() in api/ws/ticket.py to a proper
    # settings field so it is validated at startup, visible in .env docs, and
    # mockable in tests via Settings overrides.
    ws_ticket_ttl_seconds: int = 15

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

    @field_validator("environment", mode="before")
    @classmethod
    def _validate_environment(cls, v: object) -> str:
        """Fail-fast on unknown ENVIRONMENT values (e.g. 'prod' typo).

        MOD-W10-03: Prevents 'prod' from silently falling through to
        production-mode behaviour (or skipping production-only guards entirely).
        """
        normalized = str(v).lower().strip()
        if normalized not in _VALID_ENVIRONMENTS:
            raise ValueError(
                f"Unknown ENVIRONMENT value {v!r}. "
                f"Accepted values: {sorted(_VALID_ENVIRONMENTS)}"
            )
        return normalized

    @field_validator("app_process_role", mode="before")
    @classmethod
    def _validate_app_process_role(cls, value: object) -> AppProcessRole:
        """Normalize the closed process-role allowlist before model validation."""

        normalized = str(value).strip().lower()
        if normalized not in _VALID_APP_PROCESS_ROLES:
            raise ValueError(
                "APP_PROCESS_ROLE must be one of: "
                f"{', '.join(sorted(_VALID_APP_PROCESS_ROLES))}"
            )
        return cast(AppProcessRole, normalized)

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


# TD-33-07: local _coerce_str_list duplicate removed — now imported from .base
