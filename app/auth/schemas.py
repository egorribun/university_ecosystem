from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

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
    method: Literal["totp", "webauthn"]
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
    default_method: Literal["totp", "webauthn"] | None = None
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
    method: Literal["totp", "webauthn", "recovery_code"]
    # Constrain challenge_token to prevent Redis key amplification attacks:
    # min 32 chars (all legitimate tokens are UUIDs or longer), max 128 chars,
    # and restrict to the character set used by the server's token generator.
    challenge_token: str = Field(
        min_length=32,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_\-]+$",
    )
    # LOW-W19: max_length=19 matches the longest valid value (recovery code format
    # "XXXXX-XXXXX-XXXXX" = 17 chars + 2 dashes). Prevents oversized payloads from
    # reaching TOTP/recovery-code verification logic.
    code: str | None = Field(default=None, max_length=19)
    webauthn_response: dict[str, Any] | None = None
    trust_device: bool = False
