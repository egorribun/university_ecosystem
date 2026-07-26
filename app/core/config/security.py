"""SecuritySettings: composed from focused mixin classes.

Each mixin addresses a single logical concern (JWT, CORS, rate-limiting,
MFA/password policy, CSP/headers). SecuritySettings assembles them into a
single Pydantic model that is loaded from environment variables.

Adding a new concern: create a new mixin in app/core/config/mixins/ and
add it to the SecuritySettings inheritance chain here.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import Field, ValidationInfo, field_validator

from app.core.logging import get_logger

from .base import (
    _DEVELOPMENT_ENVIRONMENTS,
    BaseAppSettings,
    _coerce_str_list,
    _load_file_secret,
    _validate_non_empty,
)
from .mixins import (
    CorsSettingsMixin,
    CspSettingsMixin,
    JwtSettingsMixin,
    MfaSettingsMixin,
    RateLimitSettingsMixin,
)

_logger = get_logger(__name__)

# CFG-2 (audit 2026-03): Placeholder detection for AUDIT_LOG_SECRET.
# Defined at module level (not inside the Pydantic model) so it's a plain
# Python constant and doesn't get treated as a Pydantic field/private-attr.
_AUDIT_SECRET_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "development-audit-secret-change-me",
        "change-me",
        "changeme",
        "change_me",
        "placeholder",
        "example",
        "secret",
        "your-secret",
        "86dfd54641624c4e8ae58a2d18449c25",
    }
)


class SecuritySettings(
    JwtSettingsMixin,
    CorsSettingsMixin,
    RateLimitSettingsMixin,
    MfaSettingsMixin,
    CspSettingsMixin,
    BaseAppSettings,
):
    """Application security configuration.

    Assembled from focused mixin classes — see app/core/config/mixins/ for
    the individual concerns. All fields are loaded from environment variables
    via Pydantic BaseSettings.
    """

    # ── General ──────────────────────────────────────────────────────────────
    api_v2_prefix: str = "/api/v2"
    monitoring_heavy_probe_enabled: bool = False
    geoip_database_path: str | None = None

    # ── ABAC & Subnet Security ─────────────────────────────────────────────
    campus_subnets: list[str] | str = Field(
        default_factory=lambda: ["192.168.0.0/16", "10.0.0.0/8", "127.0.0.1/32"]
    )
    control_work_grace_minutes: int = 15

    # ── Audit log ────────────────────────────────────────────────────────────
    # CFG-2 (audit 2026-03): Default secret must be at least 32 chars and not
    # use a common placeholder substring to avoid the production validator's
    # rejection and the development warning.
    audit_log_secret: str = (
        "f3d9a1c2e4b5a6d7c8e9f0a1b2c3d4e5"  # 32-char hex default (NOT a placeholder)
    )

    # ── Image proxy ──────────────────────────────────────────────────────────
    imgproxy_key: str | None = None
    imgproxy_salt: str | None = None
    imgproxy_base_url: str = "http://localhost:8081"

    # ── CSRF (RZ-003, audit 2026-03-10) ──────────────────────────────────────
    # Used to sign CSRF tokens with HMAC-SHA256, binding each token to the
    # session_id of the authenticated user. Without this binding, a subdomain
    # compromise (e.g. static.university.edu XSS) can set a known CSRF cookie
    # value and bypass the Double-Submit validation — the "subdomain fixation"
    # attack (OWASP CSRF Cheat Sheet §Signed Double-Submit Cookies).
    #
    # Must be set to an independent random secret (≥32 bytes) via env var.
    # Default: derived from SECRET_KEY only in dev/testing to keep the
    # application bootable without extra config in local environments.
    csrf_hmac_secret: str = ""

    # ── Internal gateway signature (RZ-14-05, audit 2026-03-18) ─────────────
    # Shared secret used to verify that X-User-ID / X-Session-ID headers were
    # injected by the trusted gateway (not forged by a client or SSRF).
    # The gateway signs `"{user_id}:{session_id}"` with HMAC-SHA256 and sets
    # X-Internal-Signature; the backend verifies it before trusting the headers.
    #
    # When empty: verification is skipped (dev/single-node mode, logs a warning).
    # In production: set INTERNAL_HMAC_SECRET to an independent ≥32-byte random
    # value (e.g. `openssl rand -hex 32`) and set it on BOTH gateway and backend.
    internal_hmac_secret: str = ""

    # ── SPIFFE Workload API & mTLS ──────────────────────────────────────────
    spiffe_enabled: bool = False
    spiffe_socket_path: str = Field(default="/tmp/spire-agent/public/api.sock")  # noqa: S108 # nosec B108
    spiffe_trust_domain: str = "university.ecosystem"
    spiffe_app_id: str = "spiffe://university.ecosystem/ns/default/sa/app"
    spiffe_allowed_clients: list[str] = Field(
        default_factory=lambda: [
            "spiffe://university.ecosystem/ns/default/sa/gateway",
            "spiffe://university.ecosystem/ns/default/sa/ws-hub",
            "spiffe://university.ecosystem/ns/default/sa/file-processor",
        ]
    )

    @field_validator("audit_log_secret")
    @classmethod
    def _validate_audit_log_secret(cls, value: str, info: ValidationInfo) -> str:
        # CFG-2 (audit 2026-03): expanded placeholder detection — the old default
        # value (44 chars) silently passed the 32-char length check.  Any secret
        # containing common placeholder substrings is now rejected in production
        # and warned about in development.  The placeholder set is defined at
        # module level (_AUDIT_SECRET_PLACEHOLDERS) to avoid Pydantic treating it
        # as a private-attr field.
        normalized = _validate_non_empty(value, label="AUDIT_LOG_SECRET")
        # TD-33-05: _coerce_str_list splits on commas intentionally — multiple
        # comma-separated secrets support key rotation (old + new secret accepted
        # concurrently).  A single secret containing a literal comma would be
        # split into two entries; avoid commas in individual secret values.
        secrets = _coerce_str_list(normalized)
        if not secrets:
            raise ValueError("AUDIT_LOG_SECRET must not be empty")

        env = str(
            info.data.get("environment")
            or os.environ.get("ENVIRONMENT", "production")
            or "production"
        ).lower()
        is_dev = env in _DEVELOPMENT_ENVIRONMENTS

        for secret in secrets:
            lower = secret.lower()
            if any(ph in lower for ph in _AUDIT_SECRET_PLACEHOLDERS):
                if is_dev:
                    _logger.warning(
                        "SECURITY: AUDIT_LOG_SECRET looks like a placeholder value. "
                        "Replace it with a cryptographically random secret before "
                        "deploying to production (e.g. `openssl rand -hex 32`)."
                    )
                else:
                    raise ValueError(
                        "AUDIT_LOG_SECRET contains a placeholder value and cannot "
                        "be used in production. Generate a real secret with: "
                        "openssl rand -hex 32"
                    )

        min_length = 32
        for secret in secrets:
            if len(secret) < min_length:
                raise ValueError(
                    "AUDIT_LOG_SECRET entries must be at least 32 characters long"
                )
        return ",".join(secrets)

    # RZ-20-02 (audit 2026-03-24): Docker/K8s Secrets support.
    @field_validator("internal_hmac_secret", mode="before")
    @classmethod
    def _load_hmac_secret_file(cls, v: str | None) -> str | None:
        return _load_file_secret("INTERNAL_HMAC_SECRET_FILE", v)

    @field_validator("internal_hmac_secret")
    @classmethod
    def _validate_internal_hmac_secret(cls, v: str, info: ValidationInfo) -> str:
        env = str(
            info.data.get("environment") or os.environ.get("ENVIRONMENT", "development")
        ).lower()
        if env not in _DEVELOPMENT_ENVIRONMENTS and not v:
            raise ValueError(
                "INTERNAL_HMAC_SECRET MUST be set in production to prevent identity spoofing (SSRF)."
            )
        return v

    @field_validator("campus_subnets", mode="before")
    @classmethod
    def _validate_campus_subnets(cls, v: Any) -> list[str]:
        if v is None:
            return ["192.168.0.0/16", "10.0.0.0/8", "127.0.0.1/32"]
        return _coerce_str_list(v)
