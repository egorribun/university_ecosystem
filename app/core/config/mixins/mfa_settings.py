"""MFA, password policy, and authentication configuration mixin."""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re

from cryptography.fernet import Fernet
from pydantic import Field, ValidationInfo, field_validator, model_validator

from app.core.config.app_gen import REVOCATION_REDIS_DISABLED_PROCESS_ROLES
from app.core.config.base import (
    _DEVELOPMENT_ENVIRONMENTS,
    _validate_non_empty,
    _validate_positive_int,
)

_TOTP_KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _decode_totp_fernet_key(value: str) -> bytes:
    """Validate a Fernet representation and return its decoded 32-byte key."""
    try:
        encoded = value.encode("ascii")
        key_material = base64.urlsafe_b64decode(encoded)
        Fernet(encoded)
    except (UnicodeEncodeError, ValueError, binascii.Error):
        raise ValueError(
            "MFA_TOTP_ENCRYPTION_KEYS entries must contain valid Fernet keys"
        ) from None
    return key_material


def _parse_totp_encryption_keyring(value: str) -> dict[str, str]:
    """Validate the explicit key-id/Fernet-key ring without logging key data."""
    keys: dict[str, str] = {}
    key_materials: set[bytes] = set()
    for entry in value.split(","):
        key_id, separator, key = entry.strip().partition(":")
        if (
            not separator
            or _TOTP_KEY_ID_PATTERN.fullmatch(key_id) is None
            or not key
            or key.strip() != key
            or key_id in keys
        ):
            raise ValueError(
                "MFA_TOTP_ENCRYPTION_KEYS entries must use unique "
                "key-id:Fernet-key pairs"
            )
        key_material = _decode_totp_fernet_key(key)
        if key_material in key_materials:
            raise ValueError("MFA_TOTP_ENCRYPTION_KEYS must contain unique keys")
        key_materials.add(key_material)
        keys[key_id] = key
    return keys


class MfaSettingsMixin:
    """Multi-factor authentication and password policy settings.

    Covers TOTP, email OTP, trusted devices, and password strength requirements.
    Leaked-password screening (HIBP) is enabled by default in staging and
    production (AUD-392); development keeps it opt-in.
    """

    mfa_enabled: bool = False
    mfa_default_method: str | None = None
    mfa_totp_issuer: str = "University Ecosystem"
    # Dedicated TOTP Fernet key ring. Non-active entries are read-only legacy
    # keys so operators can retire them after rotating stored enrollment rows.
    mfa_totp_encryption_keys: str = Field(default="", repr=False)
    mfa_totp_active_encryption_key_id: str = ""
    mfa_totp_initial_skew_windows: int = 1
    mfa_challenge_ttl_seconds: int = 600
    mfa_challenge_max_attempts: int = 5
    mfa_step_up_ttl_seconds: int = 300
    mfa_totp_attempt_limit: int = 5
    mfa_totp_attempt_hourly_limit: int = 15
    mfa_email_otp_ttl_seconds: int = 600
    mfa_email_otp_resend_cooldown_seconds: int = 60
    mfa_email_otp_hmac_keys: str = ""
    mfa_email_otp_active_hmac_key_id: str = ""
    mfa_email_delivery_keks: str = ""
    mfa_email_delivery_active_kek_id: str = ""
    mfa_trusted_device_hmac_keys: str = ""
    mfa_trusted_device_active_hmac_key_id: str = ""
    trusted_device_expire_days: int = 30
    trusted_device_cookie_name: str = "trusted_device"

    password_min_length: int = 8
    password_max_length: int = 200
    password_min_character_classes: int = 3
    password_require_uppercase: bool = True
    password_require_lowercase: bool = True
    password_require_digit: bool = True
    password_require_special: bool = True
    password_zxcvbn_min_score: int = 1
    # AUD-392: unset resolves to enabled in staging/production (see validator below).
    password_hibp_check_enabled: bool = False
    password_hibp_api_url: str = "https://api.pwnedpasswords.com/range"
    password_hibp_timeout_seconds: int = 5
    # RZ-2 / RZ-22-07 (Wave 22): When True, password operations succeed even
    # if HIBP API is unreachable. Default False (fail-closed).
    #
    # SECURITY IMPLICATIONS (RZ-22-07):
    #   - Users can register/change passwords without breach checking.
    #   - Acceptable ONLY when: (1) availability SLA > security policy, AND
    #     (2) Prometheus alert ``hibp_check_failures_total`` fires within 5 min.
    #   - MUST be paired with compensating control: daily batch HIBP re-check
    #     of all passwords changed during fail-open windows.
    password_hibp_fail_open: bool = False

    @field_validator("mfa_totp_encryption_keys")
    @classmethod
    def _validate_mfa_totp_encryption_keys(cls, value: str) -> str:
        normalized = value.strip()
        if normalized:
            _parse_totp_encryption_keyring(normalized)
        return normalized

    @field_validator("mfa_totp_active_encryption_key_id")
    @classmethod
    def _validate_mfa_totp_active_encryption_key_id(cls, value: str) -> str:
        normalized = value.strip()
        if normalized and _TOTP_KEY_ID_PATTERN.fullmatch(normalized) is None:
            raise ValueError(
                "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID must be a valid key identifier"
            )
        return normalized

    @model_validator(mode="after")
    def _validate_mfa_totp_encryption_configuration(self) -> MfaSettingsMixin:
        environment = str(
            getattr(self, "environment", None)
            or os.environ.get("ENVIRONMENT", "development")
            or "development"
        ).lower()
        ring = self.mfa_totp_encryption_keys
        active_id = self.mfa_totp_active_encryption_key_id
        if not ring:
            if active_id:
                raise ValueError(
                    "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID requires "
                    "MFA_TOTP_ENCRYPTION_KEYS"
                )
            process_role = str(getattr(self, "app_process_role", "api") or "api")
            if (
                environment not in _DEVELOPMENT_ENVIRONMENTS
                and process_role not in REVOCATION_REDIS_DISABLED_PROCESS_ROLES
            ):
                raise ValueError(
                    "MFA_TOTP_ENCRYPTION_KEYS and "
                    "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID are required for "
                    "authentication-capable processes outside development"
                )
            return self

        keys = _parse_totp_encryption_keyring(ring)
        if not active_id or active_id not in keys:
            raise ValueError(
                "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID must identify a configured "
                "MFA_TOTP_ENCRYPTION_KEYS entry"
            )
        spotify_keys = {
            key.strip()
            for key in str(getattr(self, "spotify_token_secret", "") or "").split(",")
            if key.strip()
        }
        # The historical fallback remains an encryption key even when an
        # explicit Spotify key ring is configured, so keep it in the separation
        # check for every TOTP active key.
        secret_key = str(getattr(self, "secret_key", "") or "").strip()
        if secret_key:
            spotify_keys.add(
                base64.urlsafe_b64encode(
                    hashlib.sha256(secret_key.encode("utf-8")).digest()
                ).decode("ascii")
            )
        spotify_key_materials = {_decode_totp_fernet_key(key) for key in spotify_keys}
        active_key_material = _decode_totp_fernet_key(keys[active_id])
        if active_key_material in spotify_key_materials:
            raise ValueError(
                "The active MFA_TOTP encryption key must be independent of "
                "SPOTIFY_TOKEN_SECRET"
            )
        return self

    @field_validator("mfa_totp_issuer")
    @classmethod
    def _validate_mfa_totp_issuer(cls, value: str) -> str:
        return _validate_non_empty(value, label="MFA_TOTP_ISSUER")

    @field_validator(
        "mfa_challenge_ttl_seconds",
        "mfa_challenge_max_attempts",
        "mfa_step_up_ttl_seconds",
        "mfa_totp_attempt_limit",
    )
    @classmethod
    def _validate_positive_mfa_values(cls, value: int, info: ValidationInfo) -> int:
        field_name = getattr(info, "field_name", None) or "mfa_value"
        return _validate_positive_int(value, label=field_name.upper())

    @model_validator(mode="after")
    def _enable_hibp_screening_in_deployed_environments(self) -> MfaSettingsMixin:
        """AUD-392: leaked-password screening is on by default in staging/production.

        Registration and admin-created accounts read this flag, while reset and
        password change always query HIBP. An unset flag therefore resolves to
        enabled in deployed environments, and an explicit ``false`` is rejected
        there. Development keeps the opt-in default so local runs need no egress.
        """
        environment = (
            str(getattr(self, "environment", "development") or "development")
            .strip()
            .lower()
        )
        if environment not in {"staging", "production"}:
            return self
        if "password_hibp_check_enabled" not in getattr(
            self, "model_fields_set", set()
        ):
            self.password_hibp_check_enabled = True
        elif not self.password_hibp_check_enabled:
            raise ValueError(
                "PASSWORD_HIBP_CHECK_ENABLED must be true in staging/production"
            )
        return self

    @field_validator("password_min_length", "password_max_length")
    @classmethod
    def _validate_password_length_bounds(cls, value: int, info: ValidationInfo) -> int:
        field_name = getattr(info, "field_name", None) or "password_length"
        validated = _validate_positive_int(value, label=field_name.upper())
        if field_name == "password_max_length":
            min_length = info.data.get("password_min_length", 1)
            if validated < int(min_length):
                raise ValueError("PASSWORD_MAX_LENGTH must be >= PASSWORD_MIN_LENGTH")
        return validated

    @field_validator("password_min_character_classes")
    @classmethod
    def _validate_password_character_classes(cls, value: int) -> int:
        if value < 0 or value > 4:
            raise ValueError("PASSWORD_MIN_CHARACTER_CLASSES must be between 0 and 4")
        return value

    @field_validator("password_zxcvbn_min_score")
    @classmethod
    def _validate_password_zxcvbn_score(cls, value: int) -> int:
        if value < 0 or value > 4:
            raise ValueError("PASSWORD_ZXCVBN_MIN_SCORE must be between 0 and 4")
        return value

    @field_validator("password_hibp_timeout_seconds")
    @classmethod
    def _validate_password_hibp_timeout(cls, value: int) -> int:
        return _validate_positive_int(value, label="PASSWORD_HIBP_TIMEOUT_SECONDS")

    @field_validator("mfa_totp_initial_skew_windows")
    @classmethod
    def _validate_totp_skew(cls, value: int) -> int:
        if value < 0:
            raise ValueError("MFA_TOTP_INITIAL_SKEW_WINDOWS must be zero or positive")
        return value
