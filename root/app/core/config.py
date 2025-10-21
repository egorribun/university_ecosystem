from __future__ import annotations

from email.utils import parseaddr
from functools import cached_property
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_env_file(base_dir: Path) -> Path:
    candidates = [".env", ".env.local", ".env.example"]
    for name in candidates:
        candidate = base_dir / name
        if candidate.exists():
            return candidate
    return base_dir / candidates[0]


_ENV_FILE = _resolve_env_file(_PROJECT_ROOT)


def _coerce_str_list(values: Iterable[str] | str | None) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        items = [item.strip() for item in values.split(",")]
    else:
        items = [str(item).strip() for item in values]
    return [item for item in items if item]


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


class Settings(BaseSettings):
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    frontend_origin: str = "http://localhost:5173"
    frontend_origins: str | list[str] = ""
    app_base_url: str = "http://localhost:5173"
    static_dir: str = "app/static"
    image_max_width: int = 1920
    image_max_height: int = 1920
    trusted_hosts: str | list[str] = "localhost,127.0.0.1"
    environment: str = "development"
    auto_create_schema: bool = True
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
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0
    sentry_profiles_sample_rate: float = 0.0
    sentry_environment: str = ""
    log_level: str = "INFO"
    request_id_header: str = "x-request-id"
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
    cache_enabled: bool = False
    cache_redis_url: str = "redis://127.0.0.1:6379/0"
    cache_default_ttl_seconds: int = 300
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
    notifications_queue_max_size: int = 1024
    notifications_queue_enqueue_timeout_seconds: float = 0.5
    session_cleanup_interval_seconds: int = 900
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

    @field_validator("coep_value")
    @classmethod
    def _validate_coep_value(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"require-corp", "credentialless"}:
            raise ValueError(
                "COEP_VALUE must be either 'require-corp' or 'credentialless'"
            )
        return normalized

    @field_validator("rate_limit_storage_backend")
    @classmethod
    def _validate_rate_limit_storage_backend(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"memory", "redis"}:
            raise ValueError("RATE_LIMIT_STORAGE_BACKEND must be 'memory' or 'redis'")
        return normalized

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @cached_property
    def SECRET_KEY(self) -> str:
        return self.secret_key

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
        if isinstance(self.trusted_hosts, (list, tuple, set)):
            items = [str(v).strip() for v in self.trusted_hosts]
        else:
            items = [p.strip() for p in str(self.trusted_hosts).split(",")]
        return [host for host in items if host]

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
        return str(self.environment).lower() in {
            "dev",
            "development",
            "local",
            "test",
            "testing",
        }

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
        return _coerce_str_list(self.cors_expose_headers)

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
                    "script-src 'self' 'nonce-{nonce}' 'strict-dynamic' 'report-sample'",
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
                    "script-src 'self' 'unsafe-inline' 'unsafe-eval' http://localhost:5173 'report-sample'",
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


settings = Settings()
