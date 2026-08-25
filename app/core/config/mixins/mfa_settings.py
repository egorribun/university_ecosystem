"""MFA, password policy, and authentication configuration mixin."""

from __future__ import annotations

from pydantic import ValidationInfo, field_validator

from app.core.config.base import _validate_non_empty, _validate_positive_int


class MfaSettingsMixin:
    """Multi-factor authentication and password policy settings.

    Covers TOTP, email OTP, trusted devices, and password strength requirements.
    """

    mfa_enabled: bool = False
    mfa_default_method: str | None = None
    mfa_totp_issuer: str = "University Ecosystem"
    mfa_totp_initial_skew_windows: int = 1
    mfa_challenge_ttl_seconds: int = 600
    mfa_challenge_max_attempts: int = 5
    mfa_step_up_ttl_seconds: int = 300
    mfa_totp_attempt_limit: int = 5
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

    auth_dummy_hash: str = (
        "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$"
        "RytvY29SUnlxS3V5dWdyS3V5dWdyS3V5dWdyS3V5dWdyS3V5dw"
    )
    auth_min_response_time: float = 0.5  # Seconds. Used to mitigate timing attacks.

    @field_validator("mfa_totp_issuer")
    @classmethod
    def _validate_mfa_totp_issuer(cls, value: str) -> str:
        return _validate_non_empty(value, label="MFA_TOTP_ISSUER")

    @field_validator(
        "mfa_challenge_ttl_seconds",
        "mfa_challenge_max_attempts",
        "mfa_step_up_ttl_seconds",
    )
    @classmethod
    def _validate_positive_mfa_values(cls, value: int, info: ValidationInfo) -> int:
        field_name = getattr(info, "field_name", None) or "mfa_value"
        return _validate_positive_int(value, label=field_name.upper())

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
