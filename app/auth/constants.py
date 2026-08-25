from typing import Final

MFA_METHOD_TOTP: Final = "totp"
MFA_METHOD_EMAIL_OTP: Final = "email_otp"
MFA_METHOD_RECOVERY_CODE: Final = "recovery_code"

CHALLENGE_TYPE_TOTP_ENROLL = "totp-enroll"
CHALLENGE_TYPE_TOTP_VERIFY = "totp-verify"
CHALLENGE_TYPE_TOTP_AUTH = "totp-auth"
CHALLENGE_TYPE_EMAIL_OTP = "email-otp"
CHALLENGE_TYPE_RECOVERY_CODE = "recovery_code"
