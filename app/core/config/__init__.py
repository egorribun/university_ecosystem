from __future__ import annotations

import os
import typing
from functools import cached_property
from hmac import compare_digest
from urllib.parse import unquote, urlsplit

from pydantic import ValidationInfo, field_validator, model_validator

from app.core.logging import get_logger

from .app_gen import REVOCATION_REDIS_DISABLED_PROCESS_ROLES, AppGeneralSettings
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
from .cache import DEFAULT_REVOCATION_REDIS_URL, CacheSettings
from .database import DatabaseSettings
from .integrations import IntegrationSettings
from .notifications import NotificationSettings
from .observability import ObservabilitySettings
from .security import SecuritySettings
from .storage import StorageSettings

_logger = get_logger(__name__)


T = typing.TypeVar("T")


class _NamespaceView[T]:
    """Lightweight proxy that delegates attribute access to the parent Settings.

    TD-21-01 (audit 2026-03-25 Wave 21): Phase 2 of the config composition
    refactor.  Each namespace property (``settings.db``, ``settings.security``,
    etc.) returns a ``_NamespaceView`` that:

    1. Resolves attributes against the owning Settings instance (delegation).
    2. Is typed as the narrow mixin class for IDE autocompletion.
    3. Restricts ``dir()`` to the mixin's own fields for cleaner introspection.

    This is a non-breaking intermediate step toward full composition (Phase 3)
    where each namespace would hold its own independent Pydantic model.
    """

    __slots__ = ("_mixin_cls", "_parent")

    def __init__(self, parent: object, mixin_cls: type[T]) -> None:
        object.__setattr__(self, "_parent", parent)
        object.__setattr__(self, "_mixin_cls", mixin_cls)

    def __getattr__(self, name: str) -> typing.Any:
        parent = object.__getattribute__(self, "_parent")
        return getattr(parent, name)

    def __setattr__(self, name: str, value: typing.Any) -> None:
        if name in object.__getattribute__(self, "__slots__"):
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, "_parent"), name, value)

    def __delattr__(self, name: str) -> None:
        if name in object.__getattribute__(self, "__slots__"):
            object.__delattr__(self, name)
        else:
            parent = object.__getattribute__(self, "_parent")
            try:
                delattr(parent, name)
            except AttributeError:
                pass

    def __repr__(self) -> str:
        cls_name = object.__getattribute__(self, "_mixin_cls").__name__
        return f"<_NamespaceView({cls_name})>"


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
    """Consolidated application settings.

    Note: health_storage_probe_enabled, health_storage_probe_min_interval_seconds,
    monitoring_heavy_probe_enabled, and api_v2_prefix are inherited from parent
    mixin classes (AppGeneralSettings / SecuritySettings / StorageSettings).
    Do not re-declare them here — shadowing breaks MRO field resolution.
    (TD-33-04, Wave 33)
    """

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

    @model_validator(mode="after")
    def _validate_security_invariants(self) -> Settings:
        # MOD-003 (audit 2026-03-04): pydantic-settings Startup Validation Hook
        if self.environment == "production":
            if not getattr(self, "spotify_token_secret", None):
                raise ValueError("SPOTIFY_TOKEN_SECRET required in production")
            if not getattr(self, "nats_auth_token", None):
                raise ValueError("NATS_AUTH_TOKEN required in production")
            # RZ-33-07: RS256 signing legitimately requires a private key.
            # Only reject if the *public* JWKS endpoint accidentally contains a private key.
            # The signing secret is expected to be private for RS256.
        return self

    @model_validator(mode="after")
    def _validate_dependent_settings(self) -> Settings:
        """TD-29-02: Cross-validate dependent configuration pairs.

        Catches configuration mistakes that compile individually but break
        at runtime due to missing counterparts.
        """
        env = str(getattr(self, "environment", "production") or "production").lower()
        process_role = str(getattr(self, "app_process_role", "api") or "api")
        revocation_access_enabled = bool(
            getattr(self, "revocation_redis_access_enabled", True)
        )
        if process_role in REVOCATION_REDIS_DISABLED_PROCESS_ROLES:
            if revocation_access_enabled:
                raise ValueError(
                    f"APP_PROCESS_ROLE={process_role!r} must disable "
                    "REVOCATION_REDIS_ACCESS_ENABLED because this worker has no "
                    "authentication or session-revocation responsibility"
                )
        elif not revocation_access_enabled:
            raise ValueError(
                "REVOCATION_REDIS_ACCESS_ENABLED=false is restricted to non-auth "
                "worker roles; API, migration, and authentication-capable processes "
                "must retain the revocation capability"
            )

        if env in _DEVELOPMENT_ENVIRONMENTS:
            return self

        # Cache backend requires matching URL
        cache_backend = str(getattr(self, "cache_backend", "redis") or "redis").lower()
        if cache_backend in ("redis", "tiered"):
            redis_url = str(getattr(self, "cache_redis_url", "") or "")
            if not redis_url or redis_url == "redis://127.0.0.1:6379/0":
                _logger.warning(
                    "TD-29-02: cache_backend=%s but cache_redis_url is default/empty — "
                    "set CACHE_REDIS_URL for production or connections will fail",
                    cache_backend,
                )

        if not revocation_access_enabled:
            return self

        revocation_url = str(getattr(self, "revocation_redis_url", "") or "").strip()
        if not revocation_url or revocation_url == DEFAULT_REVOCATION_REDIS_URL:
            raise ValueError(
                "REVOCATION_REDIS_URL is required and must be explicitly configured outside "
                "development for authentication-capable processes"
            )
        cache_url = str(getattr(self, "cache_redis_url", "") or "")
        cache_endpoint = urlsplit(cache_url)
        revocation_endpoint = urlsplit(revocation_url)
        cache_host_port = (cache_endpoint.hostname, cache_endpoint.port or 6379)
        revocation_host_port = (
            revocation_endpoint.hostname,
            revocation_endpoint.port or 6379,
        )
        if cache_host_port == revocation_host_port:
            raise ValueError(
                "REVOCATION_REDIS_URL must use a distinct Redis process from "
                "CACHE_REDIS_URL so cache eviction cannot erase security state"
            )
        cache_password = unquote(cache_endpoint.password or "")
        revocation_password = unquote(revocation_endpoint.password or "")
        if (
            cache_password
            and revocation_password
            and compare_digest(
                cache_password.encode("utf-8"), revocation_password.encode("utf-8")
            )
        ):
            raise ValueError(
                "REVOCATION_REDIS_URL must not reuse CACHE_REDIS_URL credentials "
                "outside development"
            )

        # Database pool coordination
        pool_size = int(getattr(self, "database_pool_size", 5) or 5)
        max_overflow = int(getattr(self, "database_max_overflow", 10) or 10)
        if pool_size + max_overflow < 4:
            _logger.warning(
                "TD-29-02: database_pool_size=%d + max_overflow=%d = %d connections — "
                "this is very low for production; consider at least 10 total",
                pool_size,
                max_overflow,
                pool_size + max_overflow,
            )

        # Read replica URL should be different from primary
        replica_url = str(getattr(self, "database_read_replica_url", "") or "")
        db_url = str(getattr(self, "database_url", "") or "")
        if replica_url and replica_url == db_url:
            _logger.warning(
                "TD-29-02: database_read_replica_url is identical to database_url — "
                "read queries will hit the primary instead of a replica"
            )

        return self

    @model_validator(mode="after")
    def _validate_cwv_rum_settings(self) -> Settings:
        """A partially configured trust chain must never collect certifiable data."""
        if not self.cwv_rum_enabled:
            return self
        import re
        import uuid
        from urllib.parse import urlsplit

        if str(self.environment).lower() != "staging":
            raise ValueError("CWV_RUM_ENABLED is restricted to the staging environment")
        if len(self.cwv_rum_signing_secret.get_secret_value().encode()) < 32:
            raise ValueError("CWV_RUM_SIGNING_SECRET must contain at least 32 bytes")
        if re.fullmatch(r"[0-9a-f]{40}", self.cwv_release_sha) is None:
            raise ValueError("CWV_RELEASE_SHA must be an exact commit SHA")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", self.cwv_frontend_image_digest) is None:
            raise ValueError("CWV_FRONTEND_IMAGE_DIGEST must be an immutable digest")
        if self.cwv_deployment_run_id < 1 or self.cwv_deployment_run_attempt < 1:
            raise ValueError("CWV deployment workflow run binding is required")
        if self.cwv_deployed_at is None or self.cwv_deployed_at.tzinfo is None:
            raise ValueError("CWV_DEPLOYED_AT must be a timezone-aware timestamp")
        if not 60 <= self.cwv_envelope_ttl_seconds <= 600:
            raise ValueError("CWV_ENVELOPE_TTL_SECONDS must be between 60 and 600")
        if not 3 <= self.cwv_retention_days <= 30:
            raise ValueError("CWV_RETENTION_DAYS must be between 3 and 30")
        deployment_url = urlsplit(self.cwv_deployment_url)
        if (
            deployment_url.scheme != "https"
            or not deployment_url.netloc
            or deployment_url.username is not None
            or deployment_url.password is not None
            or deployment_url.path not in {"", "/"}
            or deployment_url.query
            or deployment_url.fragment
        ):
            raise ValueError("CWV_DEPLOYMENT_URL must be an exact HTTPS origin")
        origins = [
            item.strip() for item in self.cwv_allowed_origins.split(",") if item.strip()
        ]
        if not origins:
            raise ValueError("CWV_ALLOWED_ORIGINS must contain an HTTPS staging origin")
        for item in origins:
            parsed = urlsplit(item)
            if (
                parsed.scheme != "https"
                or not parsed.netloc
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("CWV_ALLOWED_ORIGINS must contain exact HTTPS origins")
        deployment_origin = f"https://{deployment_url.netloc.lower()}"
        allowed_origins = {
            f"https://{urlsplit(item).netloc.lower()}" for item in origins
        }
        if deployment_origin not in allowed_origins:
            raise ValueError("CWV deployment origin must be explicitly allowed")
        testers = [
            item.strip()
            for item in self.cwv_manual_tester_user_ids.get_secret_value().split(",")
            if item.strip()
        ]
        try:
            canonical_testers = {str(uuid.UUID(item)) for item in testers}
        except ValueError as exc:
            raise ValueError("CWV manual tester cohort must contain UUIDs") from exc
        if any(item != str(uuid.UUID(item)) for item in testers):
            raise ValueError("CWV manual tester cohort UUIDs must be canonical")
        if len(canonical_testers) < 25 or len(canonical_testers) > 50:
            raise ValueError("CWV manual tester cohort must contain 25 to 50 users")
        if len(canonical_testers) != len(testers):
            raise ValueError("CWV manual tester cohort must contain unique UUIDs")
        expected_workflow = (
            f"{self.cwv_export_oidc_repository}/.github/workflows/"
            "cwv-field-certification.yml@refs/heads/main"
        )
        if (
            not self.cwv_export_oidc_enabled
            or not self.cwv_export_oidc_repository
            or self.cwv_export_oidc_workflow_ref != expected_workflow
            or re.fullmatch(
                r"repo:[^:]+:environment:staging", self.cwv_export_oidc_subject
            )
            is None
        ):
            raise ValueError("CWV exporter GitHub OIDC policy is incomplete")
        return self

    @cached_property
    def app_base_url_clean(self) -> str:
        for candidate in (self.app_base_url, self.frontend_origin):
            if candidate:
                return str(candidate).rstrip("/")
        origins = self.frontend_origins_list
        return (origins[0] if origins else "http://localhost:5173").rstrip("/")

    # ── TD-21-01 Phase 2: Namespace Properties with Delegation ──────────
    #
    # TD-20-01 Phase 1 returned ``self`` — a stepping stone.  Phase 2
    # returns ``_NamespaceView`` wrappers that delegate attribute access
    # to the parent Settings object but are typed as the narrow mixin class.
    # This enables future Phase 3 (full separation) without breaking callers.
    #
    # Both access patterns work:
    #   settings.db.database_pool_size      (preferred — namespaced)
    #   settings.database_pool_size         (legacy — still works, no warning yet)

    @cached_property
    def db(self) -> DatabaseSettings:
        """Namespace: ``settings.db.database_pool_size``."""
        return typing.cast(DatabaseSettings, _NamespaceView(self, DatabaseSettings))

    @cached_property
    def security(self) -> SecuritySettings:
        """Namespace: ``settings.security.jwt_signing_active_secret``."""
        return typing.cast(SecuritySettings, _NamespaceView(self, SecuritySettings))

    @cached_property
    def cache(self) -> CacheSettings:
        """Namespace: ``settings.cache.cache_redis_url``."""
        return typing.cast(CacheSettings, _NamespaceView(self, CacheSettings))

    @cached_property
    def observability(self) -> ObservabilitySettings:
        """Namespace: ``settings.observability.enable_otel``."""
        return typing.cast(
            ObservabilitySettings, _NamespaceView(self, ObservabilitySettings)
        )

    @cached_property
    def storage(self) -> StorageSettings:
        """Namespace: ``settings.storage.storage_backend``."""
        return typing.cast(StorageSettings, _NamespaceView(self, StorageSettings))

    @cached_property
    def notifications(self) -> NotificationSettings:
        """Namespace: ``settings.notifications.smtp_host``."""
        return typing.cast(
            NotificationSettings, _NamespaceView(self, NotificationSettings)
        )

    @cached_property
    def integrations(self) -> IntegrationSettings:
        """Namespace: ``settings.integrations.spotify_client_id``."""
        return typing.cast(
            IntegrationSettings, _NamespaceView(self, IntegrationSettings)
        )

    @cached_property
    def app(self) -> AppGeneralSettings:
        """Namespace: ``settings.app.environment``."""
        return typing.cast(AppGeneralSettings, _NamespaceView(self, AppGeneralSettings))


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
