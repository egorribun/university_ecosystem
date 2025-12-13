from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from email.utils import parseaddr
from functools import cached_property
from pathlib import Path
from urllib.parse import urlparse

from pydantic import (
    AliasChoices,
    Field,
    FieldValidationInfo,
    ValidationError,
    ValidationInfo,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_env_file(base_dir: Path) -> Path | None:
    """Locate a concrete environment file if one has been provided."""

    example_path = base_dir / ".env.example"
    try:
        example_bytes = example_path.read_bytes()
    except OSError:
        example_bytes = None

    for name in (".env", ".env.local"):
        candidate = base_dir / name
        if not candidate.is_file():
            continue
        if name == ".env" and example_bytes is not None:
            try:
                candidate_bytes = candidate.read_bytes()
            except OSError:
                candidate_bytes = None
            else:
                if candidate_bytes == example_bytes:
                    logging.getLogger(__name__).warning(
                        "%s is identical to %s; update it with real secrets before "
                        "deploying.",
                        candidate,
                        example_path,
                    )
        return candidate
    return None


_ENV_FILE = _resolve_env_file(_PROJECT_ROOT)


def _coerce_str_list(values: Iterable[str] | str | None) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        items = [item.strip() for item in values.split(",")]
    else:
        items = [str(item).strip() for item in values]
    return [item for item in items if item]


def _coerce_int_list(values: Iterable[str | int] | str | None) -> list[int]:
    raw_items = _coerce_str_list(values) if not isinstance(values, list) else values
    converted: list[int] = []
    for item in raw_items:
        try:
            converted.append(int(item))
        except (TypeError, ValueError):
            continue
    return converted


def _validate_webpush_subject(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("WEBPUSH_SUBJECT must not be empty")
    lower = normalized.lower()
    if lower.startswith("mailto:"):
        _, address = parseaddr(normalized[7:])
        if address and "@" in address:
            return f"mailto:{address.lower()}"
        raise ValueError("WEBPUSH_SUBJECT mailto: value must contain a valid email")
    parsed = urlparse(normalized)
    scheme = parsed.scheme.lower()
    if scheme not in {"https", "http"}:
        raise ValueError("WEBPUSH_SUBJECT URL must use https or http scheme")
    if not parsed.netloc:
        raise ValueError("WEBPUSH_SUBJECT URL must include a host")
    if scheme == "http":
        hostname = (parsed.hostname or "").lower()
        if hostname not in {"localhost", "127.0.0.1"}:
            raise ValueError(
                "Insecure http scheme is only allowed for localhost testing"
            )
    return normalized


def _validate_non_empty(value: str, *, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    return normalized


def _validate_positive_int(value: int, *, label: str) -> int:
    if value <= 0:
        raise ValueError(f"{label} must be greater than zero")
    return value


def _validate_non_negative_int(value: int, *, label: str) -> int:
    if value < 0:
        raise ValueError(f"{label} must be zero or positive")
    return value


def _validate_positive_float(value: float, *, label: str) -> float:
    if value <= 0:
        raise ValueError(f"{label} must be greater than zero")
    return value


_logger = logging.getLogger(__name__)


_DEVELOPMENT_ENVIRONMENTS = {
    "dev",
    "development",
    "local",
    "test",
    "testing",
}


_DEVELOPMENT_FALLBACKS: dict[str, str] = {
    "database_url": "sqlite+aiosqlite:///./dev.db",
    "secret_key": "development-secret-key",  # pragma: allowlist secret
}


class Settings(BaseSettings):
    def __init__(self, **values):
        allow_missing = values.pop("_allow_missing", False)
        try:
            super().__init__(**values)
        except ValidationError as exc:

            def _format_missing(loc: tuple[object, ...]) -> str | None:
                if not loc:
                    return None
                first = loc[0]
                if isinstance(first, str):
                    return first.upper()
                return str(first)

            missing_required = sorted(
                {
                    formatted
                    for error in exc.errors(include_url=False)
                    if error.get("type") == "missing"
                    for formatted in [
                        _format_missing(tuple(error.get("loc", ()) or ()))
                    ]
                    if formatted
                }
            )
            if allow_missing and missing_required:
                fallback_values: dict[str, str] = {}
                unresolved: list[str] = []
                for missing in missing_required:
                    field_name = missing.lower()
                    fallback = _DEVELOPMENT_FALLBACKS.get(field_name)
                    if fallback is None:
                        unresolved.append(missing)
                    else:
                        fallback_values[field_name] = fallback
                if not unresolved:
                    combined_values = {**values, **fallback_values}
                    super().__init__(**combined_values)
                    object.__setattr__(
                        self,
                        "_development_fallback_fields",
                        tuple(sorted(fallback_values.keys())),
                    )
                    return
            if missing_required:
                details = ", ".join(missing_required)
                raise RuntimeError(
                    "Missing required environment variables: "
                    f"{details}. Provide real secrets via environment variables or an"
                    " application .env file (not .env.example)."
                ) from None
            raise

    @property
    def development_fallback_fields(self) -> tuple[str, ...]:
        stored = getattr(self, "_development_fallback_fields", ())
        if isinstance(stored, tuple):
            return stored
        return tuple(stored)

    @property
    def has_development_fallbacks(self) -> bool:
        return bool(self.development_fallback_fields)

    database_url: str
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout: float = 30.0
    database_pool_recycle: int = 1_800
    secret_key: str
    jwt_signing_keys: list[str] | str = ""
    jwt_active_kid: str | None = None
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    frontend_origin: str = "http://localhost:5173"
    frontend_origins: str | list[str] = ""
    app_base_url: str = "http://localhost:5173"
    static_dir: str = "app/static"
    response_compression_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "response_compression_enabled", "enable_response_compression"
        ),
    )
    image_max_width: int = 1920
    image_max_height: int = 1920
    trusted_hosts: str | list[str] = "localhost,127.0.0.1"
    environment: str = "development"
    auto_create_schema: bool | None = None
    smtp_host: str = ""
    smtp_port: int = 0
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_security: str = "none"
    smtp_starttls: bool = False
    mail_from: str = "no-reply@example.com"
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_token_secret: str = ""
    spotify_redirect_uri: str = "http://localhost:8000/spotify/callback"
    spotify_scopes: str = "user-read-currently-playing user-read-playback-state"
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = ""
    enable_otel: bool = False
    otel_service_name: str = "university-ecosystem"
    otel_exporter_otlp_endpoint: str = ""
    otel_exporter_otlp_headers: str = ""
    otel_trace_sampler_ratio: float = 1.0
    enable_otel_metrics: bool = True
    enable_otel_logs: bool = True
    service_version: str = Field(
        default="",
        validation_alias=AliasChoices("service_version", "app_version"),
    )
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0
    sentry_profiles_sample_rate: float = 0.0
    sentry_environment: str = ""
    log_level: str = "INFO"
    request_id_header: str = "x-request-id"
    trace_header: str = "x-trace-id"
    internal_allowed_ips: str | list[str] = "127.0.0.1,::1"
    internal_auth_header: str = "X-Internal-Token"
    internal_auth_token: str | None = None
    cors_allow_credentials: bool = True
    cors_allow_methods: str | list[str] = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    cors_allow_headers: str | list[str] = "Authorization,Content-Type"
    cors_expose_headers: str | list[str] = ""
    rate_limit_enabled: bool = True
    rate_limit_default: str | list[str] = "100/minute"
    rate_limit_sensitive: str = "5/minute"
    rate_limit_storage_backend: str = "memory"
    rate_limit_storage_uri: str = "memory://"
    rate_limit_headers_enabled: bool = True
    auth_lockout_thresholds: str | list[str] = "5:30,8:300,10:3600"
    auth_lockout_history_minutes: int = 1_440
    mfa_enabled: bool = False
    mfa_default_method: str | None = None
    mfa_totp_issuer: str = "University Ecosystem"
    mfa_totp_initial_skew_windows: int = 1
    mfa_challenge_ttl_seconds: int = 300
    mfa_challenge_max_attempts: int = 5
    mfa_step_up_ttl_seconds: int = 300
    mfa_totp_attempt_limit: int = 5
    trusted_device_expire_days: int = 30
    trusted_device_cookie_name: str = "trusted_device"
    security_csp: str = ""
    # Extra hosts for connect-src; merged with defaults dynamically.
    security_connect_src_extra: str | list[str] = (
        "https://api.spotify.com,"
        "https://fcm.googleapis.com,"
        "https://fcmregistrations.googleapis.com,"
        "https://*.push.services.mozilla.com,"
        "https://updates.push.services.mozilla.com,"
        "https://*.push.apple.com"
    )
    security_csp_report_only: bool | None = None
    security_csp_report_uri: str = ""
    security_hsts_enabled: bool = True
    security_hsts_max_age: int = 31536000
    security_hsts_include_subdomains: bool = True
    security_hsts_preload: bool = True
    security_x_frame_options: str = "DENY"
    security_permissions_policy: str = "geolocation=(), microphone=(), camera=()"
    security_referrer_policy: str = "no-referrer"
    security_x_content_type_options: str = "nosniff"
    enable_strict_security_headers: bool | None = None
    enable_coop: bool = False
    enable_coep: bool = False
    coep_value: str = "require-corp"
    enable_corp: bool = False
    corp_value: str = "same-site"
    cache_backend: str = "redis"
    cache_enabled: bool = False
    cache_redis_url: str = "redis://127.0.0.1:6379/0"
    cache_default_ttl_seconds: int = 300
    stats_cache_ttl_seconds: int = 180
    cache_warmup_enabled: bool = False
    cache_warmup_groups: list[int] | str = ""
    cache_warmup_stats_users: list[int] | str = ""
    cache_warmup_periods: list[str] | str = "30d,90d"
    cache_warmup_max_age_seconds: int = 120
    enable_metrics_endpoint: bool = False
    metrics_basic_auth_username: str = ""
    metrics_basic_auth_password: str = ""
    metrics_allowlist: str | list[str] = ""
    notifications_scheduler_poll_seconds: int = 30
    notifications_scheduler_window_minutes: int = 6
    notifications_scheduler_max_backoff_seconds: int = 300
    notifications_scheduler_inline_enabled: bool = True
    notifications_worker_metrics_host: str = "0.0.0.0"
    notifications_worker_metrics_port: int = 9101
    notifications_webpush_concurrency_limit: int = 10
    notifications_retention_days: int = 90
    notifications_retention_cleanup_interval_seconds: int = 86_400
    notifications_retention_batch_size: int = 500
    notification_queue_dead_letter_retention_days: int = 30
    notification_queue_dead_letter_cleanup_interval_seconds: int = 86_400
    storage_backend: str = "static"
    storage_static_base_url: str = "/static"
    storage_s3_bucket: str = ""
    storage_s3_region: str = ""
    storage_s3_access_key_id: str = ""
    storage_s3_secret_access_key: str = ""
    storage_s3_endpoint_url: str = ""
    storage_s3_base_url: str = ""
    notifications_queue_max_size: int = 1024
    notifications_queue_enqueue_timeout_seconds: float = 0.5
    notifications_queue_in_memory_only: bool = False
    notifications_queue_retry_base_seconds: float = 1.0
    notifications_allowed_push_topics: list[str] | str = Field(
        default_factory=lambda: ["news", "schedule", "events", "system"]
    )
    attendance_token_secret: str = ""
    attendance_token_ttl_seconds: int = 300
    notifications_queue_max_attempts: int = 5
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
    access_log_retention_days: int = 180
    event_file_allowed_mime_types: str | list[str] = (
        "application/pdf,"
        "text/plain,"
        "application/msword,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "application/vnd.ms-excel,"
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    event_file_allowed_extensions: str | list[str] = ".pdf,.txt,.doc,.docx,.xls,.xlsx"
    event_file_max_size_bytes: int = 10 * 1024 * 1024
    event_file_scanner_enabled: bool = False
    event_file_scanner_backend: str = "clamd"
    event_file_scanner_host: str = "127.0.0.1"
    event_file_scanner_port: int = 3310
    event_file_scanner_socket: str = ""
    event_file_scanner_timeout: float = 30.0
    event_file_scanner_max_size_mb: float = Field(default=25.0, ge=0.0)
    event_file_scanner_max_duration_sec: float = Field(default=10.0, ge=0.0)

    @field_validator("auto_create_schema", mode="before")
    @classmethod
    def _default_auto_create_schema(
        cls, value: bool | None, info: ValidationInfo
    ) -> bool:
        if value is not None:
            return bool(value)
        environment = str(info.data.get("environment") or "development").lower()
        return environment in _DEVELOPMENT_ENVIRONMENTS

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

    @field_validator("database_pool_size")
    @classmethod
    def _validate_database_pool_size(cls, value: int) -> int:
        return _validate_positive_int(value, label="DATABASE_POOL_SIZE")

    @field_validator("database_max_overflow")
    @classmethod
    def _validate_database_max_overflow(cls, value: int) -> int:
        return _validate_non_negative_int(value, label="DATABASE_MAX_OVERFLOW")

    @field_validator("database_pool_timeout")
    @classmethod
    def _validate_database_pool_timeout(cls, value: float) -> float:
        return _validate_positive_float(value, label="DATABASE_POOL_TIMEOUT")

    @field_validator("database_pool_recycle")
    @classmethod
    def _validate_database_pool_recycle(cls, value: int) -> int:
        return _validate_non_negative_int(value, label="DATABASE_POOL_RECYCLE")

    @field_validator("coep_value")
    @classmethod
    def _validate_coep_value(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"require-corp", "credentialless"}:
            raise ValueError(
                "COEP_VALUE must be either 'require-corp' or 'credentialless'"
            )
        return normalized

    @field_validator("corp_value")
    @classmethod
    def _validate_corp_value(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"same-origin", "same-site", "cross-origin"}:
            raise ValueError(
                "CORP_VALUE must be one of 'same-origin', 'same-site', "
                "or 'cross-origin'"
            )
        return normalized

    @field_validator("rate_limit_storage_backend")
    @classmethod
    def _validate_rate_limit_storage_backend(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"memory", "redis"}:
            raise ValueError("RATE_LIMIT_STORAGE_BACKEND must be 'memory' or 'redis'")
        return normalized

    @field_validator("storage_backend")
    @classmethod
    def _validate_storage_backend(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"static", "filesystem", "local", "s3", "minio"}:
            raise ValueError(
                "STORAGE_BACKEND must be one of static, filesystem, local, s3, or minio"
            )
        return normalized

    @field_validator("notifications_allowed_push_topics", mode="before")
    @classmethod
    def _validate_notifications_allowed_push_topics(
        cls, value: Iterable[str] | str | None
    ) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in _coerce_str_list(value):
            candidate = item.strip().lower()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            normalized.append(candidate)
        if not normalized:
            raise ValueError(
                "NOTIFICATIONS_ALLOWED_PUSH_TOPICS must include at least one topic"
            )
        return normalized

    @field_validator("notifications_retention_batch_size")
    @classmethod
    def _validate_notifications_retention_batch_size(cls, value: int) -> int:
        return _validate_positive_int(
            int(value), label="NOTIFICATIONS_RETENTION_BATCH_SIZE"
        )

    @field_validator("stats_cache_ttl_seconds")
    @classmethod
    def _validate_stats_cache_ttl_seconds(cls, value: int) -> int:
        return _validate_positive_int(value, label="STATS_CACHE_TTL_SECONDS")

    @field_validator("cache_backend")
    @classmethod
    def _validate_cache_backend(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"redis", "memory", "none"}:
            raise ValueError("CACHE_BACKEND must be redis, memory, or none")
        return normalized

    @field_validator("cache_warmup_max_age_seconds")
    @classmethod
    def _validate_cache_warmup_max_age(cls, value: int) -> int:
        return _validate_non_negative_int(value, label="CACHE_WARMUP_MAX_AGE_SECONDS")

    @field_validator("mfa_totp_issuer")
    @classmethod
    def _validate_mfa_totp_issuer(cls, value: str) -> str:
        return _validate_non_empty(value, label="MFA_TOTP_ISSUER")

    @field_validator(
        "mfa_challenge_ttl_seconds",
        "mfa_challenge_max_attempts",
        "mfa_step_up_ttl_seconds",
    )
    @classmethod
    def _validate_positive_mfa_values(
        cls, value: int, info: FieldValidationInfo
    ) -> int:
        field_name = getattr(info, "field_name", None) or "mfa_value"
        return _validate_positive_int(value, label=field_name.upper())

    @field_validator("mfa_totp_attempt_limit")
    @classmethod
    def _validate_mfa_attempt_limits(cls, value: int, info: FieldValidationInfo) -> int:
        field_name = getattr(info, "field_name", None) or "mfa_attempt_limit"
        return _validate_non_negative_int(value, label=str(field_name).upper())

    @field_validator("password_reset_max_active_tokens")
    @classmethod
    def _validate_password_reset_max_active_tokens(cls, value: int) -> int:
        return _validate_positive_int(value, label="PASSWORD_RESET_MAX_ACTIVE_TOKENS")

    @field_validator("mfa_totp_initial_skew_windows")
    @classmethod
    def _validate_totp_skew(cls, value: int) -> int:
        if value < 0:
            raise ValueError("MFA_TOTP_INITIAL_SKEW_WINDOWS must be zero or positive")
        return value

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE is not None else None,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    def _build_jwt_signing_key_entries(self) -> list[tuple[str, str]]:
        entries: list[tuple[str, str]] = []
        seen_kids: set[str] = set()
        for raw_entry in _coerce_str_list(self.jwt_signing_keys):
            if ":" not in raw_entry:
                raise RuntimeError(
                    "JWT_SIGNING_KEYS entries must be in '<kid>:<secret>' format"
                )
            kid, secret = raw_entry.split(":", 1)
            kid = kid.strip()
            secret = secret.strip()
            if not kid:
                raise RuntimeError(
                    "JWT_SIGNING_KEYS entries must specify a non-empty kid value"
                )
            if not secret:
                raise RuntimeError(
                    "JWT_SIGNING_KEYS entries must specify a non-empty secret value"
                )
            if kid in seen_kids:
                raise RuntimeError(
                    "JWT_SIGNING_KEYS entries must use unique kid values"
                )
            entries.append((kid, secret))
            seen_kids.add(kid)

        if not entries:
            fallback_kid = (self.jwt_active_kid or "primary").strip() or "primary"
            entries.append((fallback_kid, self.secret_key))
        return entries

    @property
    def jwt_signing_key_registry(self) -> dict[str, str]:
        registry: dict[str, str] = {}
        for kid, secret in self._build_jwt_signing_key_entries():
            registry[kid] = secret
        return registry

    @property
    def jwt_signing_active_kid(self) -> str:
        registry = self.jwt_signing_key_registry
        configured = (
            self.jwt_active_kid.strip()
            if isinstance(self.jwt_active_kid, str)
            else None
        )
        if configured:
            if configured not in registry:
                raise RuntimeError(
                    "JWT_ACTIVE_KID must match one of the configured JWT_SIGNING_KEYS"
                )
            return configured
        return next(iter(registry))

    @property
    def jwt_signing_active_secret(self) -> str:
        registry = self.jwt_signing_key_registry
        active_kid = self.jwt_signing_active_kid
        secret = registry.get(active_kid)
        if secret is None:
            raise RuntimeError(
                "Configured JWT signing key registry does not contain the active kid"
            )
        return secret

    @cached_property
    def SECRET_KEY(self) -> str:
        return self.jwt_signing_active_secret

    @cached_property
    def ALGORITHM(self) -> str:
        return self.algorithm

    @cached_property
    def frontend_origins_list(self) -> list[str]:
        raw: list[str] = []

        def _extend(values: Iterable[str] | str | None) -> None:
            if not values:
                return
            if isinstance(values, str):
                raw.extend([v.strip() for v in values.split(",") if v.strip()])
            else:
                raw.extend([str(v).strip() for v in values if str(v).strip()])

        _extend(self.frontend_origins)
        _extend(self.frontend_origin)
        _extend(self.app_base_url)
        if self.is_development:
            raw.extend(["http://localhost:5173", "http://127.0.0.1:5173"])
        seen: set[str] = set()
        result: list[str] = []
        for origin in raw:
            normalized = origin.rstrip("/")
            key = normalized.lower()
            if normalized and key not in seen:
                seen.add(key)
                result.append(normalized)
        return result

    @cached_property
    def VAPID_PUBLIC_KEY(self) -> str:
        return self.vapid_public_key

    @cached_property
    def VAPID_PRIVATE_KEY(self) -> str:
        return self.vapid_private_key

    @cached_property
    def WEBPUSH_SUBJECT(self) -> str:
        raw_subject = (self.vapid_subject or "").strip()
        if not raw_subject:
            return "mailto:no-reply@example.com"
        subject = _validate_webpush_subject(raw_subject)
        return subject

    @cached_property
    def notifications_allowed_push_topics_set(self) -> frozenset[str]:
        return frozenset(self.notifications_allowed_push_topics)

    @cached_property
    def notifications_allowed_push_topics_list(self) -> list[str]:
        return list(self.notifications_allowed_push_topics)

    @cached_property
    def cors_allow_origins_list(self) -> list[str]:
        allowed: list[str] = []
        seen: set[str] = set()
        for origin in self.frontend_origins_list:
            candidate = origin.strip()
            if not candidate or candidate == "*":
                continue
            parsed = urlparse(candidate)
            scheme = parsed.scheme.lower()
            hostname = (parsed.hostname or "").lower()
            if self.strict_security_headers_enabled and hostname not in {
                "localhost",
                "127.0.0.1",
            }:
                if scheme != "https":
                    continue
            key = candidate.lower()
            if key not in seen:
                seen.add(key)
                allowed.append(candidate)
        return allowed

    @cached_property
    def cors_allow_credentials_effective(self) -> bool:
        if not self.cors_allow_credentials:
            return False
        if not self.cors_allow_origins_list:
            return False
        if self.strict_security_headers_enabled:
            for origin in self.cors_allow_origins_list:
                parsed = urlparse(origin)
                scheme = parsed.scheme.lower()
                hostname = (parsed.hostname or "").lower()
                if hostname in {"localhost", "127.0.0.1"}:
                    continue
                if scheme != "https":
                    return False
        return True

    @cached_property
    def trusted_hosts_list(self) -> list[str]:
        if isinstance(self.trusted_hosts, list | tuple | set):
            items = [str(v).strip() for v in self.trusted_hosts]
        else:
            items = [p.strip() for p in str(self.trusted_hosts).split(",")]
        return [host for host in items if host]

    @cached_property
    def internal_allowed_ips_list(self) -> list[str]:
        return [ip for ip in _coerce_str_list(self.internal_allowed_ips) if ip]

    @cached_property
    def static_dir_path(self) -> Path:
        raw_path = Path(self.static_dir)
        if not raw_path.is_absolute():
            raw_path = (_PROJECT_ROOT / raw_path).resolve()
        return raw_path

    @property
    def event_file_allowed_mime_types_set(self) -> set[str]:
        values = {
            value.lower()
            for value in _coerce_str_list(self.event_file_allowed_mime_types)
            if value
        }
        return values

    @property
    def event_file_allowed_extensions_set(self) -> set[str]:
        values: set[str] = set()
        for value in _coerce_str_list(self.event_file_allowed_extensions):
            normalized = value.strip().lower()
            if normalized.startswith("."):
                normalized = normalized[1:]
            if normalized:
                values.add(normalized)
        return values

    @cached_property
    def app_base_url_clean(self) -> str:
        for candidate in (self.app_base_url, self.frontend_origin):
            if candidate:
                return str(candidate).rstrip("/")
        origins = self.frontend_origins_list
        return (origins[0] if origins else "http://localhost:5173").rstrip("/")

    @cached_property
    def is_development(self) -> bool:
        return str(self.environment).lower() in _DEVELOPMENT_ENVIRONMENTS

    @cached_property
    def cors_allow_methods_list(self) -> list[str]:
        methods = _coerce_str_list(self.cors_allow_methods)
        return methods or ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

    @cached_property
    def cors_allow_headers_list(self) -> list[str]:
        headers = _coerce_str_list(self.cors_allow_headers)
        return headers or ["Authorization", "Content-Type"]

    @cached_property
    def cors_expose_headers_list(self) -> list[str]:
        headers = {
            header.strip(): None
            for header in _coerce_str_list(self.cors_expose_headers)
        }
        headers[self.request_id_header] = None
        headers[self.trace_header] = None
        return [key for key in headers.keys() if key]

    @cached_property
    def rate_limit_default_list(self) -> list[str]:
        return _coerce_str_list(self.rate_limit_default)

    @property
    def metrics_allowlist_entries(self) -> list[str]:
        return _coerce_str_list(self.metrics_allowlist)

    @cached_property
    def rate_limit_sensitive_value(self) -> str | None:
        value = str(self.rate_limit_sensitive).strip()
        return value or None

    @cached_property
    def strict_security_headers_enabled(self) -> bool:
        value = self.enable_strict_security_headers
        if value is None:
            return not self.is_development
        return bool(value)

    @property
    def cookie_secure(self) -> bool:
        return self.strict_security_headers_enabled

    @property
    def cookie_samesite(self) -> str:
        """Return cookie SameSite policy.

        In development mode, returns 'lax' to allow cross-origin requests
        (e.g., frontend on port 5173 accessing backend on port 8000).
        In production, returns 'strict' for maximum security.
        """
        if self.is_development:
            return "lax"
        return "strict"

    @cached_property
    def security_csp_report_only_effective(self) -> bool:
        if self.security_csp_report_only is not None:
            return bool(self.security_csp_report_only)
        return not self.strict_security_headers_enabled

    @cached_property
    def security_connect_src_values(self) -> list[str]:
        values: list[str] = []
        seen: set[str] = set()
        for candidate in ["'self'"] + _coerce_str_list(self.security_connect_src_extra):
            parts = [part.strip() for part in str(candidate).split() if part.strip()]
            for part in parts:
                key = part.lower()
                if key not in seen:
                    seen.add(key)
                    values.append(part)
        return values

    def _development_connect_overrides(self) -> list[str]:
        if not self.is_development:
            return []
        overrides: list[str] = []
        seen: set[str] = {value.lower() for value in self.security_connect_src_values}
        for host in ("127.0.0.1:8000", "localhost:5173", "127.0.0.1:5173"):
            http_origin = f"http://{host}"
            key = http_origin.lower()
            if key not in seen:
                overrides.append(http_origin)
                seen.add(key)
        # Preserve websocket origins for local dev servers.
        for host in ("localhost:5173", "127.0.0.1:5173"):
            ws_origin = f"ws://{host}"
            key = ws_origin.lower()
            if key not in seen:
                overrides.append(ws_origin)
                seen.add(key)
        for origin in self.frontend_origins_list:
            cleaned = origin.rstrip("/")
            if not cleaned:
                continue
            lower = cleaned.lower()
            if lower not in seen:
                overrides.append(cleaned)
                seen.add(lower)
            parsed = urlparse(cleaned)
            scheme = parsed.scheme.lower()
            if scheme in {"http", "https"}:
                ws_scheme = "ws" if scheme == "http" else "wss"
                ws_origin = f"{ws_scheme}://{parsed.netloc}" if parsed.netloc else ""
                if ws_origin:
                    key = ws_origin.lower()
                    if key not in seen:
                        overrides.append(ws_origin)
                        seen.add(key)
        return overrides

    @cached_property
    def coop_enabled(self) -> bool:
        return bool(self.enable_coop)

    @cached_property
    def coep_enabled(self) -> bool:
        return bool(self.enable_coep)

    @cached_property
    def coep_header_value(self) -> str:
        return self.coep_value

    @cached_property
    def corp_enabled(self) -> bool:
        return bool(self.enable_corp)

    @cached_property
    def corp_header_value(self) -> str:
        return self.corp_value

    @cached_property
    def security_hsts_enabled_effective(self) -> bool:
        if not self.strict_security_headers_enabled:
            return False
        if not self.security_hsts_enabled:
            return False
        return self.app_base_url_clean.startswith("https://")

    @cached_property
    def should_inject_csp_nonce(self) -> bool:
        if self.security_csp_report_only_effective:
            return False
        return self.strict_security_headers_enabled

    @cached_property
    def strict_security_csp(self) -> str:
        policy = self.build_csp_policy(nonce="{nonce}", report_only=False)
        return policy

    def build_csp_policy(self, *, nonce: str | None, report_only: bool) -> str:
        # Allow explicit overrides via SECURITY_CSP for power users.
        if "security_csp" in self.model_fields_set and self.security_csp.strip():
            template = self.security_csp.strip()
            require_trusted_types = (
                "require-trusted-types-for 'script'"
                if self.strict_security_headers_enabled and not report_only
                else ""
            )
            policy = template.replace("{require_trusted_types}", require_trusted_types)
            connect_sources = (
                self.security_connect_src_values + self._development_connect_overrides()
            )
            connect_value = " ".join(connect_sources).strip()
            policy = policy.replace("{connect_src}", connect_value or "'self'")
            if nonce:
                policy = policy.replace("{nonce}", nonce)
            else:
                policy = (
                    policy.replace("'nonce-{nonce}'", "")
                    .replace("{nonce}", "")
                    .replace("  ", " ")
                )
            directives = [part.strip() for part in policy.split(";") if part.strip()]
            policy = "; ".join(directives)
        else:
            connect_sources = (
                self.security_connect_src_values + self._development_connect_overrides()
            )
            connect_value = " ".join(
                dict.fromkeys([value for value in connect_sources if value])
            )
            if not connect_value:
                connect_value = "'self'"
            if self.strict_security_headers_enabled and not report_only:
                directives = [
                    "default-src 'self'",
                    (
                        "script-src 'self' 'nonce-{nonce}' "
                        "'strict-dynamic' 'report-sample'"
                    ),
                    "style-src 'self' 'unsafe-inline'",
                    "img-src 'self' data: blob:",
                    f"connect-src {connect_value}",
                    "object-src 'none'",
                    "base-uri 'self'",
                    "frame-ancestors 'self'",
                    "trusted-types app dompurify-news goog#html 'allow-duplicates'",
                    "require-trusted-types-for 'script'",
                ]
            else:
                directives = [
                    "default-src 'self' http://localhost:5173",
                    (
                        "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
                        "http://localhost:5173 'report-sample'"
                    ),
                    "style-src 'self' 'unsafe-inline'",
                    "img-src 'self' data: blob:",
                    f"connect-src {connect_value}",
                    "object-src 'none'",
                    "base-uri 'self'",
                    "frame-ancestors 'self'",
                    "trusted-types app dompurify-news goog#html 'allow-duplicates'",
                ]
            policy = "; ".join(directives)
            if nonce:
                policy = policy.replace("{nonce}", nonce)
            else:
                policy = policy.replace("'nonce-{nonce}'", "").replace("{nonce}", "")
        policy = "; ".join(
            part.strip() for part in policy.split(";") if part and part.strip()
        )
        if not policy:
            policy = "default-src 'self'"
        if "default-src" not in policy.lower():
            policy = f"default-src 'self'; {policy}".strip("; ")
        report_uri = self.security_csp_report_uri.strip()
        if report_uri:
            policy = f"{policy}; report-uri {report_uri}".rstrip("; ")
        return policy

    @cached_property
    def cache_backend_normalized(self) -> str:
        return self.cache_backend.strip().lower()

    @cached_property
    def cache_warmup_group_ids(self) -> tuple[int, ...]:
        return tuple(_coerce_int_list(self.cache_warmup_groups))

    @cached_property
    def cache_warmup_stats_user_ids(self) -> tuple[int, ...]:
        return tuple(_coerce_int_list(self.cache_warmup_stats_users))

    @cached_property
    def cache_warmup_period_keys(self) -> tuple[str, ...]:
        normalized = [
            item.strip().lower() for item in _coerce_str_list(self.cache_warmup_periods)
        ]
        unique: list[str] = []
        seen: set[str] = set()
        for item in normalized:
            if not item or item in seen:
                continue
            seen.add(item)
            unique.append(item)
        return tuple(unique)


def _should_allow_development_defaults() -> bool:
    if _ENV_FILE is not None:
        return False
    return not any(os.environ.get(name) for name in ("DATABASE_URL", "SECRET_KEY"))


def _load_settings() -> Settings:
    try:
        return Settings()
    except RuntimeError as exc:
        if not _should_allow_development_defaults():
            raise
        _logger.debug(
            (
                "Falling back to development defaults because settings "
                "initialization failed: %s"
            ),
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
            (
                "Provide real secrets via environment variables or a .env file "
                "before deploying."
            ),
        ]
        if not (_PROJECT_ROOT / ".env").exists():
            hint_parts.append(
                (
                    "For local development, copy root/.env.example to root/.env "
                    "and replace the placeholder values before "
                    "starting the application."
                ),
            )
        _logger.warning(
            (
                "Using development defaults for %s because DATABASE_URL and SECRET_KEY "
                "are not configured. %s"
            ),
            missing,
            " ".join(hint_parts),
        )
        return fallback


settings = _load_settings()
