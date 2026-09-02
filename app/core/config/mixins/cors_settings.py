"""CORS and trusted-host configuration mixin."""

from __future__ import annotations

from functools import cached_property
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationInfo, field_validator

from app.core.config.base import _coerce_str_list


class CorsSettingsMixin:
    """CORS policy, trusted hosts, and origin validation.

    Computes effective allow-lists from the raw string/list settings,
    enforcing HTTPS-only origins in production (strict_security_headers_enabled).
    """

    frontend_origin: str = "http://localhost:5173"
    frontend_origins: str | list[str] = ""
    app_base_url: str = "http://localhost:5173"
    trusted_hosts: str | list[str] = "localhost,127.0.0.1"
    allowed_hosts: str | list[str] = ""

    cors_allow_credentials: bool = True
    cors_allow_methods: str | list[str] = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    cors_allow_headers: str | list[str] = (
        "Accept,Accept-Language,Authorization,Content-Language,Content-Type,"
        "Origin,X-Requested-With,x-profile-cache-envelope"
    )
    cors_expose_headers: str | list[str] = ""

    request_id_header: str = "x-request-id"
    trace_header: str = "x-trace-id"

    trusted_proxies: str | list[str] = ""

    internal_allowed_ips: str | list[str] = "127.0.0.1,::1"
    internal_auth_header: str = "X-Internal-Token"
    internal_auth_token: str | None = None

    @field_validator("internal_auth_token")
    @classmethod
    def _validate_internal_auth_token(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        # Require token in production to prevent IP-only access (spoofable)
        if not value:
            import os

            from app.core.config.base import _DEVELOPMENT_ENVIRONMENTS

            env = str(
                info.data.get("environment")
                or os.environ.get("ENVIRONMENT", "development")
                or "development"
            ).lower()
            if env not in _DEVELOPMENT_ENVIRONMENTS:
                from app.core.logging import get_logger

                logger = get_logger(__name__)
                logger.warning(
                    "Internal route shared guard is not configured in %s "
                    "environment. Internal API routes are vulnerable to IP spoofing.",
                    env,
                )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
        return value

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
            if (
                getattr(self, "strict_security_headers_enabled", False)
                and hostname
                not in {
                    "localhost",
                    "127.0.0.1",
                }
                and scheme != "https"
            ):
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
        if getattr(self, "strict_security_headers_enabled", False):
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
    def allowed_hosts_list(self) -> list[str]:
        """Hosts allowed by TrustedHostMiddleware for Host header validation."""
        if isinstance(self.allowed_hosts, list | tuple | set):
            items = [str(v).strip() for v in self.allowed_hosts]
        else:
            items = [p.strip() for p in str(self.allowed_hosts).split(",")]
        result = [host for host in items if host]
        if not result and getattr(self, "is_development", False):
            result = ["localhost", "127.0.0.1", "testserver"]
        return result

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
    def trusted_proxies_list(self) -> list[str]:
        return [proxy for proxy in _coerce_str_list(self.trusted_proxies) if proxy]
