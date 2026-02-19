"""Content Security Policy and HTTP security headers configuration mixin."""

from __future__ import annotations

from functools import cached_property
from urllib.parse import urlparse

from pydantic import field_validator

from app.core.config.base import _coerce_str_list


class CspSettingsMixin:
    """HTTP security headers: CSP, HSTS, COOP, COEP, CORP, X-Frame-Options.

    The CSP is generated dynamically by ContentSecurityPolicy (app.core.policies.csp)
    using the connect-src extra sources and environment-aware defaults.
    """

    security_csp: str = ""
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

    @cached_property
    def strict_security_headers_enabled(self) -> bool:
        value = self.enable_strict_security_headers
        if value is None:
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
        for candidate in ["'self'", *_coerce_str_list(self.security_connect_src_extra)]:
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
        for origin in getattr(self, "frontend_origins_list", []):
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
        return getattr(self, "app_base_url_clean", "").startswith("https://")

    @cached_property
    def should_inject_csp_nonce(self) -> bool:
        if self.security_csp_report_only_effective:
            return False
        return self.strict_security_headers_enabled

    @cached_property
    def strict_security_csp(self) -> str:
        from app.core.policies.csp import ContentSecurityPolicy

        connect_sources = self.security_connect_src_values + (
            self._development_connect_overrides()
            if getattr(self, "is_development", False)
            else []
        )
        policy_gen = ContentSecurityPolicy(
            is_development=getattr(self, "is_development", False),
            report_only=self.security_csp_report_only_effective,
            report_uri=self.security_csp_report_uri,
            connect_src_extra=connect_sources,
            custom_policy=self.security_csp,
        )
        return policy_gen.generate(nonce="{nonce}")

    def build_csp_policy(self, *, nonce: str | None, report_only: bool) -> str:
        """Backward compatibility wrapper using the new Policy engine."""
        from app.core.policies.csp import ContentSecurityPolicy

        connect_sources = self.security_connect_src_values + (
            self._development_connect_overrides()
            if getattr(self, "is_development", False)
            else []
        )
        policy_gen = ContentSecurityPolicy(
            is_development=getattr(self, "is_development", False),
            report_only=report_only,
            report_uri=self.security_csp_report_uri,
            connect_src_extra=connect_sources,
            custom_policy=self.security_csp,
        )
        return policy_gen.generate(nonce=nonce)
