"""app.auth.mfa — Multi-Factor Authentication helpers.

This package replaces the former ``app/auth/mfa.py`` god-object module.
All public symbols are re-exported here so that existing callers continue to
work without changes::

    from app.auth import mfa
    mfa.verify_totp_for_user(...)

    from app.auth.mfa import generate_recovery_codes
    await generate_recovery_codes(db, user=user)
"""

from app.auth.constants import (
    MFA_METHOD_RECOVERY_CODE,
    MFA_METHOD_TOTP,
    MFA_METHOD_WEBAUTHN,
)
from app.auth.mfa.challenge import (
    CHALLENGE_TYPE_TOTP_AUTH,
    consume_challenge,
    describe_challenge_attempts,
    get_challenge,
    issue_challenge,
    purge_expired_challenges,
)
from app.auth.mfa.lifecycle import (
    MfaResetStats,
    has_totp_enabled,
    has_webauthn_enabled,
    record_mfa_success,
    refresh_user_mfa_preferences,
    reset_user_mfa,
    user_has_active_factor,
    user_has_confirmed_interactive_factor,
)
from app.auth.mfa.recovery import (
    count_remaining_recovery_codes,
    generate_recovery_codes,
    verify_recovery_code,
)
from app.auth.mfa.totp import (
    TOTP_ENROLLMENT_LIMIT_ERROR,
    TOTP_ENROLLMENT_PENDING_ERROR,
    build_totp_uri,
    complete_totp_enrollment,
    create_totp_secret,
    disable_totp,
    start_totp_enrollment,
    start_totp_verification,
    verify_totp,
    verify_totp_for_user,
)
from app.auth.mfa.trusted_device import (
    create_trusted_device_token,
    verify_trusted_device_token,
)
from app.models.models import MfaTotpEnrollment, WebAuthnCredential

__all__ = [
    # challenge
    "CHALLENGE_TYPE_TOTP_AUTH",
    "consume_challenge",
    "describe_challenge_attempts",
    "get_challenge",
    "issue_challenge",
    "purge_expired_challenges",
    # lifecycle
    "MfaResetStats",
    "has_totp_enabled",
    "has_webauthn_enabled",
    "record_mfa_success",
    "refresh_user_mfa_preferences",
    "reset_user_mfa",
    "user_has_active_factor",
    "user_has_confirmed_interactive_factor",
    # recovery
    "count_remaining_recovery_codes",
    "generate_recovery_codes",
    "verify_recovery_code",
    # totp
    "TOTP_ENROLLMENT_LIMIT_ERROR",
    "TOTP_ENROLLMENT_PENDING_ERROR",
    "build_totp_uri",
    "complete_totp_enrollment",
    "create_totp_secret",
    "disable_totp",
    "start_totp_enrollment",
    "start_totp_verification",
    "verify_totp",
    "verify_totp_for_user",
    # trusted_device
    "create_trusted_device_token",
    "verify_trusted_device_token",
    # models
    "MfaTotpEnrollment",
    "WebAuthnCredential",
    # constants
    "MFA_METHOD_TOTP",
    "MFA_METHOD_WEBAUTHN",
    "MFA_METHOD_RECOVERY_CODE",
]
