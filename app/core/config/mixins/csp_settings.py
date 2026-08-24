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
    # RZ-15 (audit 2026-03-05): When True, Python ASGI middleware suppresses HSTS
    # because the upstream reverse-proxy (Caddy/nginx) already emits it, preventing
    # duplicate Strict-Transport-Security headers.
    # Set SECURITY_HSTS_BEHIND_PROXY=true in your production .env.
    security_hsts_behind_proxy: bool = False
    security_hsts_max_age: int = 31536000
    security_hsts_include_subdomains: bool = True
    security_hsts_preload: bool = True
    security_x_frame_options: str = "DENY"
    security_permissions_policy: str = (
        "accelerometer=(), autoplay=(), camera=(), cross-origin-isolated=(), "
        "display-capture=(), encrypted-media=(), fullscreen=(), geolocation=(), "
        "gyroscope=(), keyboard-map=(), magnetometer=(), microphone=(), midi=(), "
        "payment=(), picture-in-picture=(), publickey-credentials-get=(), "
        "screen-wake-lock=(), sync-xhr=(self), usb=(), web-share=(), "
        "xr-spatial-tracking=(), clipboard-read=(), clipboard-write=(), gamepad=()"
    )
    security_referrer_policy: str = "no-referrer"
    security_x_content_type_options: str = "nosniff"
    enable_strict_security_headers: bool | None = None
    enable_coop: bool = True
    enable_coep: bool = False
    coep_value: str = "require-corp"
    enable_corp: bool = True
    corp_value: str = "same-site"
    # Wave 131 SW6 — Phase 4 deploy infrastructure cookie SameSite migration.
    # Production default flipped from "strict" to "lax" so that direct-link
    # clicks from external referrers (search engines, email, social media)
    # carry the access_token_v2 / csrf_token cookies — Strict blocks the
    # cookie on the initial cross-site GET, defeating SSR auth-at-edge for
    # the very flow that benefits most from it.
    #
    # SECURITY_COOKIE_SAMESITE_OVERRIDE provides an emergency rollback knob:
    # set to "strict" to restore pre-W131 behavior without a code change.
    # Empty string = use the dev/prod default below.
    #
    # CSRF compatibility: app/core/csrf.py CSRFMiddleware uses Signed
    # Double-Submit Cookie + HMAC-SHA256 + X-CSRF-Token header check.
    # Cross-site state-change attempts can't set custom X-CSRF-Token
    # (CORS preflight blocks), so SameSite=Lax does not open new attack
    # surface — the CSRF defenses remain intact.
    security_cookie_samesite_override: str = ""

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

    @field_validator("security_cookie_samesite_override")
    @classmethod
    def _validate_cookie_samesite_override(cls, value: str) -> str:
        # Wave 131 SW6 — RZ-131-01: validate the override at config-load
        # time so a typo can never silently degrade to None / "" at runtime
        # (which would inadvertently fall through to the prod default).
        normalized = value.strip().lower()
        if normalized and normalized not in {"strict", "lax", "none"}:
            raise ValueError(
                "SECURITY_COOKIE_SAMESITE_OVERRIDE must be empty or one of "
                f"'strict', 'lax', 'none' (got: {value!r})"
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
        # Wave 131 SW6 — Phase 4 deploy infrastructure cookie migration.
        # Pre-W131: dev returned "lax", prod returned "strict". Strict
        # blocked the access_token_v2 / csrf_token cookies on cross-site GET
        # (e.g. direct link clicks from search engines, email, social media)
        # — defeating SSR auth-at-edge for the very flow that benefits most
        # from it. Post-W131: both dev and prod default to "lax".
        # SECURITY_COOKIE_SAMESITE_OVERRIDE env var provides an emergency
        # rollback knob ("strict" / "lax" / "none"; "" = use default).
        # CSRF safety preserved via Signed Double-Submit + HMAC + X-CSRF-
        # Token header check (CORS preflight blocks cross-site header
        # forgery, so Lax does not open new attack surface).
        override = getattr(self, "security_cookie_samesite_override", "")
        if override:
            return override
        return "lax"

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
            # Development-only loopback Vite HMR; production never reaches
            # this branch and HTTPS origins are mapped to WSS below.
            ws_origin = f"ws://{host}"  # nosemgrep: javascript.lang.security.detect-insecure-websocket.detect-insecure-websocket
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
        # RZ-15 (audit 2026-03-05): When running behind a trusted proxy (Caddy, nginx)
        # that already sends Strict-Transport-Security, suppress it from the ASGI layer
        # to avoid duplicate headers. Set SECURITY_HSTS_BEHIND_PROXY=true in production.
        if getattr(self, "security_hsts_behind_proxy", False):
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
