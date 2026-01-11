from __future__ import annotations

import logging
from functools import cached_property
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationInfo, field_validator

from .base import (
    BaseAppSettings,
    _coerce_str_list,
    _validate_non_empty,
    _validate_positive_int,
)

_logger = logging.getLogger(__name__)


class SecuritySettings(BaseAppSettings):
    secret_key: str
    jwt_signing_keys: list[str] | str = ""
    jwt_active_kid: str | None = None
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    api_v2_prefix: str = "/api/v2"
    monitoring_heavy_probe_enabled: bool = False
    audit_log_secret: str = "development-audit-secret-change-me"

    max_sessions_per_user: int = 5
    frontend_origin: str = "http://localhost:5173"
    frontend_origins: str | list[str] = ""
    app_base_url: str = "http://localhost:5173"
    trusted_hosts: str | list[str] = "localhost,127.0.0.1"

    request_id_header: str = "x-request-id"
    trace_header: str = "x-trace-id"

    internal_allowed_ips: str | list[str] = "127.0.0.1,::1"
    internal_auth_header: str = "X-Internal-Token"
    internal_auth_token: str | None = None

    imgproxy_key: str | None = None
    imgproxy_salt: str | None = None
    imgproxy_base_url: str = "http://localhost:8081"

    cors_allow_credentials: bool = True
    cors_allow_methods: str | list[str] = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    cors_allow_headers: str | list[str] = (
        "Accept,Accept-Language,Authorization,Content-Language,Content-Type,Origin,X-Requested-With,x-profile-cache-envelope"
    )
    cors_expose_headers: str | list[str] = ""

    rate_limit_enabled: bool = True
    rate_limit_default: str | list[str] = "100/minute"
    rate_limit_sensitive: str = "5/minute"
    rate_limit_auth: str = "5/minute"
    rate_limit_upload: str = "10/minute"
    rate_limit_admin: str = "50/minute"
    rate_limit_websocket: str = "30/minute"
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
    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "University Ecosystem"
    webauthn_origin: str = "http://localhost:5173"
    trusted_device_expire_days: int = 30
    trusted_device_cookie_name: str = "trusted_device"

    security_csp: str = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://accounts.google.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data: https: blob:; "
        "connect-src 'self' https://api.spotify.com https://fcm.googleapis.com "
        "https://fcmregistrations.googleapis.com "
        "https://*.push.services.mozilla.com https://*.push.apple.com; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "object-src 'none'; "
        "base-uri 'self';"
    )
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

    @field_validator("mfa_totp_issuer")
    @classmethod
    def _validate_mfa_totp_issuer(cls, value: str) -> str:
        return _validate_non_empty(value, label="MFA_TOTP_ISSUER")

    @field_validator("audit_log_secret")
    @classmethod
    def _validate_audit_log_secret(cls, value: str) -> str:
        normalized = _validate_non_empty(value, label="AUDIT_LOG_SECRET")
        secrets = _coerce_str_list(normalized)
        if not secrets:
            raise ValueError("AUDIT_LOG_SECRET must not be empty")
        min_length = 32
        for secret in secrets:
            if len(secret) < min_length:
                raise ValueError(
                    "AUDIT_LOG_SECRET entries must be at least 32 characters long"
                )
        return ",".join(secrets)

    @field_validator(
        "mfa_challenge_ttl_seconds",
        "mfa_challenge_max_attempts",
        "mfa_step_up_ttl_seconds",
    )
    @classmethod
    def _validate_positive_mfa_values(cls, value: int, info: ValidationInfo) -> int:
        field_name = getattr(info, "field_name", None) or "mfa_value"
        return _validate_positive_int(value, label=field_name.upper())

    @field_validator("mfa_totp_initial_skew_windows")
    @classmethod
    def _validate_totp_skew(cls, value: int) -> int:
        if value < 0:
            raise ValueError("MFA_TOTP_INITIAL_SKEW_WINDOWS must be zero or positive")
        return value

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

        def _extend(values: Any) -> None:
            if not values:
                return
            if isinstance(values, str):
                raw.extend([v.strip() for v in values.split(",") if v.strip()])
            else:
                raw.extend([str(v).strip() for v in values if str(v).strip()])

        _extend(self.frontend_origins)
        _extend(self.frontend_origin)
        _extend(self.app_base_url)
        _extend(self.webauthn_origin)

        # We can't use self.is_development here directly if we want this as a mixin,
        # but BaseAppSettings has it.
        if getattr(self, "is_development", False):
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
        if isinstance(self.trusted_hosts, list | tuple | set):
            items = [str(v).strip() for v in self.trusted_hosts]
        else:
            items = [p.strip() for p in str(self.trusted_hosts).split(",")]
        return [host for host in items if host]

    @cached_property
    def internal_allowed_ips_list(self) -> list[str]:
        return [ip for ip in _coerce_str_list(self.internal_allowed_ips) if ip]

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
        return [key for key in headers if key]

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
            # We need is_development here too.
            return not getattr(self, "is_development", False)
        return bool(value)

    @property
    def cookie_secure(self) -> bool:
        return self.strict_security_headers_enabled

    @property
    def cookie_samesite(self) -> str:
        if getattr(self, "is_development", False):
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
        if not getattr(self, "is_development", False):
            return []
        overrides: list[str] = []
        seen: set[str] = {value.lower() for value in self.security_connect_src_values}
        for host in (
            "127.0.0.1:8000",
            "localhost:5173",
            "127.0.0.1:5173",
            "localhost:8081",
            "127.0.0.1:8081",
        ):
            http_origin = f"http://{host}"
            key = http_origin.lower()
            if key not in seen:
                overrides.append(http_origin)
                seen.add(key)
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
        # app_base_url_clean will be needed.
        return getattr(self, "app_base_url_clean", "").startswith("https://")

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
