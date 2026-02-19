"""SecuritySettings: composed from focused mixin classes.

Each mixin addresses a single logical concern (JWT, CORS, rate-limiting,
MFA/password policy, CSP/headers). SecuritySettings assembles them into a
single Pydantic model that is loaded from environment variables.

Adding a new concern: create a new mixin in app/core/config/mixins/ and
add it to the SecuritySettings inheritance chain here.
"""

from __future__ import annotations

import logging
import os

from pydantic import ValidationInfo, field_validator

from .base import (
    _DEVELOPMENT_ENVIRONMENTS,
    BaseAppSettings,
    _coerce_str_list,
    _validate_non_empty,
)
from .mixins import (
    CorsSettingsMixin,
    CspSettingsMixin,
    JwtSettingsMixin,
    MfaSettingsMixin,
    RateLimitSettingsMixin,
)

_logger = logging.getLogger(__name__)


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

    # ── Audit log ────────────────────────────────────────────────────────────
    audit_log_secret: str = "development-audit-secret-change-me"

    # ── Image proxy ──────────────────────────────────────────────────────────
    imgproxy_key: str | None = None
    imgproxy_salt: str | None = None
    imgproxy_base_url: str = "http://localhost:8081"

    @field_validator("audit_log_secret")
    @classmethod
    def _validate_audit_log_secret(cls, value: str, info: ValidationInfo) -> str:
        normalized = _validate_non_empty(value, label="AUDIT_LOG_SECRET")
        secrets = _coerce_str_list(normalized)
        if not secrets:
            raise ValueError("AUDIT_LOG_SECRET must not be empty")

        # Prevent usage of default value in non-dev environments
        env = (
            info.data.get("environment") or os.environ.get("ENVIRONMENT", "development")
        ).lower()
        if (
            env not in _DEVELOPMENT_ENVIRONMENTS
            and "development-audit-secret-change-me" in secrets
        ):
            raise ValueError("Default AUDIT_LOG_SECRET cannot be used in production")

        min_length = 32
        for secret in secrets:
            if len(secret) < min_length:
                raise ValueError(
                    "AUDIT_LOG_SECRET entries must be at least 32 characters long"
                )
        return ",".join(secrets)
