from typing import Final

MFA_METHOD_TOTP: Final = "totp"
MFA_METHOD_WEBAUTHN: Final = "webauthn"
MFA_METHOD_RECOVERY_CODE: Final = "recovery_code"

CHALLENGE_TYPE_TOTP_ENROLL = "totp-enroll"
CHALLENGE_TYPE_TOTP_VERIFY = "totp-verify"
CHALLENGE_TYPE_TOTP_AUTH = "totp-verify"
CHALLENGE_TYPE_WEBAUTHN_REG = "webauthn-registration"
CHALLENGE_TYPE_WEBAUTHN_AUTH = "webauthn-authentication"
CHALLENGE_TYPE_RECOVERY_CODE = "recovery_code"
