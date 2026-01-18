"""
Security configuration settings.

Extracted from main config.py for better organization.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecuritySettings(BaseSettings):
    """Security-related configuration."""

    secret_key: str = Field(
        default="changeme-use-a-strong-secret-key",
        description="Secret key for JWT signing",
    )

    algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm",
    )

    access_token_expire_minutes: int = Field(
        default=60,
        description="JWT access token expiration in minutes",
    )

    # Password hashing
    password_hash_algorithm: str = Field(
        default="argon2",
        description="Password hashing algorithm (argon2 or bcrypt)",
    )

    # Cookie settings
    cookie_secure: bool = Field(
        default=True,
        description="Set Secure flag on cookies",
    )

    cookie_samesite: str = Field(
        default="lax",
        description="SameSite cookie policy",
    )

    # CORS
    cors_allow_origins: str = Field(
        default="http://localhost:5173",
        description="Comma-separated list of allowed CORS origins",
    )

    # MFA
    mfa_required_default: bool = Field(
        default=False,
        description="Require MFA for new users by default",
    )

    mfa_totp_attempt_limit: int = Field(
        default=5,
        description="Max TOTP verification attempts",
    )

    # CSP
    csp_report_only: bool = Field(
        default=False,
        description="Use CSP report-only mode",
    )

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins into a list."""
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


__all__ = ["SecuritySettings"]
