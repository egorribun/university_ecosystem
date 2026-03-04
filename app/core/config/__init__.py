from __future__ import annotations

import logging
import os
from functools import cached_property

from pydantic import ValidationInfo, field_validator, model_validator

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

    @model_validator(mode="after")
    def _reject_insecure_production_config(self) -> Settings:
        """Fail fast on insecure defaults that are only acceptable locally.

        RZ-12 (audit 2026-03-04): Operators frequently copy .env.example → .env
        without updating MINIO_SECURE and ELASTICSEARCH_URL, resulting in plaintext
        object storage and search traffic in production (OWASP A02).

        Escape hatch: SQLite in the database URL is an infallible sign of a test
        or development environment (real production always uses PostgreSQL), so we
        skip infrastructure TLS checks in that case.
        """
        env = str(getattr(self, "environment", "production") or "production").lower()
        if env in _DEVELOPMENT_ENVIRONMENTS:
            return self

        # SQLite database URL → test run — never used in real production.
        db_url = str(getattr(self, "database_url", "") or "")
        if "sqlite" in db_url.lower():
            return self

        # Guard MinIO TLS
        if not getattr(self, "minio_secure", False):
            raise ValueError(
                "MINIO_SECURE must be true in production/staging — "
                "plaintext object storage exposes file uploads to network interception."
            )
        # Guard Elasticsearch TLS
        es_url = str(getattr(self, "elasticsearch_url", "") or "")
        if es_url.startswith("http://"):
            raise ValueError(
                "ELASTICSEARCH_URL must use https:// in production/staging — "
                "plaintext Elasticsearch exposes search queries and indexed data."
            )
        return self

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
            is_ci = (
                os.environ.get("CI") == "true"
                or os.environ.get("GITHUB_ACTIONS") == "true"
            )
            if is_ci:
                hint_parts.append(
                    "This is permitted for CI/CD pipelines (CI=true detected). "
                    "If this step requires real secrets, ensure they are injected "
                    "via environment variables."
                )
            else:
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
