"""app.auth.mfa — Multi-Factor Authentication helpers.

This package replaces the former ``app/auth/mfa.py`` god-object module.
All public symbols are re-exported here so that existing callers continue to
work without changes::

    from app.auth import mfa
    mfa.verify_totp_for_user(...)

    from app.auth.mfa import generate_recovery_codes
    await generate_recovery_codes(db, user=user)
"""

import datetime

from app.auth.constants import (
    CHALLENGE_TYPE_RECOVERY_CODE,
    CHALLENGE_TYPE_TOTP_AUTH,
    CHALLENGE_TYPE_TOTP_ENROLL,
    CHALLENGE_TYPE_TOTP_VERIFY,
    CHALLENGE_TYPE_WEBAUTHN_AUTH,
    CHALLENGE_TYPE_WEBAUTHN_REG,
    MFA_METHOD_RECOVERY_CODE,
    MFA_METHOD_TOTP,
    MFA_METHOD_WEBAUTHN,
)
from app.auth.mfa.challenge import (
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
    _base64url_decode,
    _base64url_encode,
    create_trusted_device_token,
    verify_trusted_device_token,
)
from app.models import MfaTotpEnrollment, RecoveryCode, WebAuthnCredential


def _utcnow() -> datetime.datetime:
    import datetime

    return datetime.datetime.now(datetime.UTC)


__all__ = [
    "CHALLENGE_TYPE_RECOVERY_CODE",
    "CHALLENGE_TYPE_TOTP_AUTH",
    "CHALLENGE_TYPE_TOTP_ENROLL",
    "CHALLENGE_TYPE_TOTP_VERIFY",
    "CHALLENGE_TYPE_WEBAUTHN_AUTH",
    "CHALLENGE_TYPE_WEBAUTHN_REG",
    "MFA_METHOD_RECOVERY_CODE",
    "MFA_METHOD_TOTP",
    "MFA_METHOD_WEBAUTHN",
    "TOTP_ENROLLMENT_LIMIT_ERROR",
    "TOTP_ENROLLMENT_PENDING_ERROR",
    "MfaResetStats",
    "MfaTotpEnrollment",
    "RecoveryCode",
    "WebAuthnCredential",
    "_base64url_decode",
    "_base64url_encode",
    "_utcnow",
    "build_totp_uri",
    "complete_totp_enrollment",
    "consume_challenge",
    "count_remaining_recovery_codes",
    "create_totp_secret",
    "create_trusted_device_token",
    "describe_challenge_attempts",
    "disable_totp",
    "generate_recovery_codes",
    "get_challenge",
    "has_totp_enabled",
    "has_webauthn_enabled",
    "issue_challenge",
    # MED-W19: Removed "mfa_enrollments" — this name was never defined or
    # imported in this package, making it a dangling __all__ entry that raises
    # AttributeError on wildcard imports.
    "purge_expired_challenges",
    "record_mfa_success",
    "refresh_user_mfa_preferences",
    "reset_user_mfa",
    "start_totp_enrollment",
    "start_totp_verification",
    "user_has_active_factor",
    "user_has_confirmed_interactive_factor",
    "verify_recovery_code",
    "verify_totp",
    "verify_totp_for_user",
    "verify_trusted_device_token",
]
