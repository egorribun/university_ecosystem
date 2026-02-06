from __future__ import annotations

import logging
from functools import cached_property

from pydantic import ValidationInfo, field_validator

from .app_gen import AppGeneralSettings
from .base import (
    _DEVELOPMENT_ENVIRONMENTS,
    _PROJECT_ROOT,
)
from .base import (
    _ENV_FILE as _ENV_FILE,
)
from .base import (
    _should_allow_development_defaults as _base_should_allow,
)
from .cache import CacheSettings
from .database import DatabaseSettings
from .integrations import IntegrationSettings
from .notifications import NotificationSettings
from .observability import ObservabilitySettings
from .security import SecuritySettings
from .storage import StorageSettings

_logger = logging.getLogger(__name__)


class Settings(
    DatabaseSettings,
    SecuritySettings,
    CacheSettings,
    ObservabilitySettings,
    StorageSettings,
    NotificationSettings,
    IntegrationSettings,
    AppGeneralSettings,
):
    """Consolidated application settings."""

    health_storage_probe_enabled: bool = True
    health_storage_probe_min_interval_seconds: int = 3600
    monitoring_heavy_probe_enabled: bool = False
    audit_log_secret: str = "development-audit-secret-change-me"
    api_v2_prefix: str = "/api/v2"

    @field_validator("auto_create_schema")
    @classmethod
    def _warn_auto_create_schema(cls, value: bool, info: ValidationInfo) -> bool:
        if value:
            environment = str(info.data.get("environment") or "production").lower()
            if environment not in _DEVELOPMENT_ENVIRONMENTS:
                _logger.warning(
                    (
                        "AUTO_CREATE_SCHEMA is enabled while ENVIRONMENT=%s. "
                        "This should only be used for development or automated tests. "
                        "Run 'alembic upgrade head' and set AUTO_CREATE_SCHEMA=false "
                        "for production deployments."
                    ),
                    environment or "production",
                )
        return bool(value)

    @field_validator("audit_log_secret")
    @classmethod
    def _validate_audit_log_secret(cls, value: str, info: ValidationInfo) -> str:
        environment = str(info.data.get("environment") or "production").lower()
        if environment not in _DEVELOPMENT_ENVIRONMENTS and (
            not value or value == "development-audit-secret-change-me"
        ):
            _logger.warning(
                "AUDIT_LOG_SECRET is using development default in %s environment. "
                "Set a secure AUDIT_LOG_SECRET for production deployments.",
                environment,
            )
        return value or "development-audit-secret-change-me"

    @cached_property
    def app_base_url_clean(self) -> str:
        for candidate in (self.app_base_url, self.frontend_origin):
            if candidate:
                return str(candidate).rstrip("/")
        origins = self.frontend_origins_list
        return (origins[0] if origins else "http://localhost:5173").rstrip("/")


def _load_settings() -> Settings:
    try:
        return Settings()
    except RuntimeError as exc:
        missing_required = getattr(exc, "missing_required", None)
        # Re-use logic from base but with local check
        if not _base_should_allow(missing_required):
            raise
        _logger.debug(
            "Falling back to development defaults because settings "
            "initialization failed: %s",
            exc,
            exc_info=False,
        )
        fallback = Settings(_allow_missing=True)
        missing = ", ".join(
            name.upper() for name in fallback.development_fallback_fields
        )
        if not missing:
            missing = "DATABASE_URL, SECRET_KEY"
        hint_parts = [
            "Provide real secrets via environment variables or a .env file "
            "before deploying."
        ]
        if not (_PROJECT_ROOT / ".env").exists():
            hint_parts.append(
                "For local development, copy .env.example to .env and replace "
                "the placeholder values before starting the application."
            )
        _logger.warning(
            "Using development defaults for %s because required "
            "environment variables missing. %s",
            missing,
            " ".join(hint_parts),
        )
        return fallback


settings = _load_settings()
