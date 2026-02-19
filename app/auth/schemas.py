from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.auth.constants import (
    MFA_METHOD_RECOVERY_CODE,
    MFA_METHOD_TOTP,
    MFA_METHOD_WEBAUTHN,
)
from app.schemas.schemas import MfaTotpEnrollmentOut


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    trust_device: bool = False


class LoginPasskeyStartIn(BaseModel):
    email: EmailStr


class LoginPasskeyVerifyIn(BaseModel):
    challenge_token: str
    webauthn_response: dict[str, Any]
    trust_device: bool = False


class MfaMethodChallengeOut(BaseModel):
    method: Literal[MFA_METHOD_TOTP, MFA_METHOD_WEBAUTHN]
    challenge_token: str
    challenge_expires_at: datetime
    options: dict[str, Any] | None = None
    attempt_count: int | None = None
    attempt_limit: int | None = None
    remaining_attempts: int | None = None


MfaChallengeEntry = MfaMethodChallengeOut


class PendingMfaResponse(BaseModel):
    status: Literal["mfa_required"] = "mfa_required"
    user_id: UUID
    session_id: UUID | None = None
    default_method: Literal[MFA_METHOD_TOTP, MFA_METHOD_WEBAUTHN] | None = None
    methods: list[MfaMethodChallengeOut]


class TotpEnrollmentStartIn(BaseModel):
    label: str | None = None
    reuse_existing: bool | None = False


class TotpEnrollmentStartOut(BaseModel):
    enrollment: MfaTotpEnrollmentOut
    secret: str
    otpauth_url: str


class TotpEnrollmentConfirmIn(BaseModel):
    enrollment_id: UUID
    code: str


class MfaVerifyIn(BaseModel):
    method: Literal[MFA_METHOD_TOTP, MFA_METHOD_WEBAUTHN, MFA_METHOD_RECOVERY_CODE]
    challenge_token: str
    code: str | None = None
    webauthn_response: dict[str, Any] | None = None
    trust_device: bool = False
