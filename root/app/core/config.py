from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

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


class Settings(BaseSettings):
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    frontend_origin: str = "http://localhost:5173"
    frontend_origins: str | list[str] = ""
    app_base_url: str = "http://localhost:5173"
    static_dir: str = "app/static"
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
    rate_limit_storage_uri: str = "memory://"
    rate_limit_headers_enabled: bool = True
    security_csp: str = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "script-src 'self' 'nonce-{nonce}'; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "object-src 'none'; "
        "upgrade-insecure-requests"
    )
    security_csp_report_only: bool = False
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
    cache_enabled: bool = False
    cache_redis_url: str = "redis://127.0.0.1:6379/0"
    cache_default_ttl_seconds: int = 300

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

    @cached_property
    def strict_security_csp(self) -> str:
        directives = [
            part.strip()
            for part in self.security_csp.split(";")
            if part.strip()
        ]
        policy = "; ".join(directives)
        if not policy:
            policy = "default-src 'self'"
        if "default-src" not in policy.lower():
            policy = f"default-src 'self'; {policy}"
        policy = policy.rstrip("; ")
        report_uri = self.security_csp_report_uri.strip()
        if report_uri:
            policy = f"{policy}; report-uri {report_uri}".rstrip("; ")
        return policy


settings = Settings()
