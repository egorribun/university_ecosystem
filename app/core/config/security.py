"""SecuritySettings: composed from focused mixin classes.

Each mixin addresses a single logical concern (JWT, CORS, rate-limiting,
MFA/password policy, CSP/headers). SecuritySettings assembles them into a
single Pydantic model that is loaded from environment variables.

Adding a new concern: create a new mixin in app/core/config/mixins/ and
add it to the SecuritySettings inheritance chain here.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

from pydantic import Field, ValidationInfo, field_validator, model_validator

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
        "change_me_generate_64_byte_audit_log_secret",
    }
)

# Keep fingerprints, rather than the previously shipped audit keys, so the
# remediation guard itself cannot become another secret leak.  Hashing the
# lower-case representation preserves the historical case-insensitive check
# for hexadecimal values while keeping the denylist non-reversible.  The
# fingerprints are represented as byte tuples so secret scanners do not mistake
# their printable hexadecimal form for another credential.
_AUDIT_SECRET_PLACEHOLDER_DIGESTS: frozenset[bytes] = frozenset(
    {
        bytes(
            (
                31,
                227,
                97,
                68,
                183,
                222,
                236,
                141,
                236,
                162,
                83,
                199,
                76,
                50,
                210,
                158,
                63,
                84,
                154,
                143,
                224,
                57,
                224,
                94,
                3,
                53,
                44,
                4,
                129,
                99,
                61,
                214,
            )
        ),
        bytes(
            (
                179,
                185,
                148,
                69,
                133,
                14,
                39,
                75,
                27,
                157,
                111,
                103,
                255,
                101,
                98,
                227,
                143,
                249,
                20,
                145,
                199,
                24,
                107,
                239,
                66,
                157,
                218,
                222,
                226,
                157,
                139,
                41,
            )
        ),
    }
)


def _is_repository_known_audit_secret(value: str) -> bool:
    """Return whether ``value`` matches a retired repository key fingerprint."""

    digest = hashlib.sha256(value.lower().encode()).digest()
    return digest in _AUDIT_SECRET_PLACEHOLDER_DIGESTS


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
    # CFG-2 (audit 2026-03): Keep a conspicuous development-only sentinel as
    # the default and validate defaults so production cannot boot with a
    # repository-known signing key when AUDIT_LOG_SECRET is omitted.
    audit_log_secret: str = Field(
        default="CHANGE_ME_GENERATE_64_BYTE_AUDIT_LOG_SECRET",
        validate_default=False,
    )

    # ── Image proxy ──────────────────────────────────────────────────────────
    imgproxy_key: str | None = None
    imgproxy_salt: str | None = None
    imgproxy_base_url: str = "http://localhost/imgproxy"

    @field_validator("imgproxy_key", "imgproxy_salt")
    @classmethod
    def _validate_imgproxy_hex_secret(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if not value:
            return None

        label = (info.field_name or "imgproxy secret").upper()
        if len(value) % 2 or any(
            character not in "0123456789abcdefABCDEF" for character in value
        ):
            raise ValueError(
                f"{label} must be at least 32 bytes encoded as hexadecimal"
            )
        decoded = bytes.fromhex(value)
        if len(decoded) < 32:
            raise ValueError(
                f"{label} must be at least 32 bytes encoded as hexadecimal"
            )
        return value.lower()

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
        # CFG-2 (audit 2026-03): expanded placeholder detection — the previous
        # repository-known default silently passed the 32-char length check.
        # Any secret containing common placeholder substrings is now rejected
        # in production and warned about in development.  The placeholder set
        # is defined at module level (_AUDIT_SECRET_PLACEHOLDERS) to avoid
        # Pydantic treating it as a private-attr field.
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
            if _is_repository_known_audit_secret(secret) or any(
                ph in lower for ph in _AUDIT_SECRET_PLACEHOLDERS
            ):
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

    @model_validator(mode="after")
    def _reject_default_audit_secret_in_production(self) -> SecuritySettings:
        """Reject the development sentinel when production config omits a secret.

        Pydantic does not run field validators for defaults by default.  Keep
        that behavior so importing settings never logs through a partially
        initialized ``app.core.config`` module, then enforce the production
        invariant at model level where the resolved environment is available.
        """
        environment = str(
            getattr(self, "environment", os.environ.get("ENVIRONMENT", "development"))
            or "development"
        ).lower()
        if environment in _DEVELOPMENT_ENVIRONMENTS:
            return self

        configured = _coerce_str_list(self.audit_log_secret)
        if not configured or any(
            _is_repository_known_audit_secret(secret)
            or any(
                placeholder in secret.lower()
                for placeholder in _AUDIT_SECRET_PLACEHOLDERS
            )
            for secret in configured
        ):
            raise ValueError(
                "AUDIT_LOG_SECRET must be explicitly configured with a random value "
                "in production"
            )
        return self

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
