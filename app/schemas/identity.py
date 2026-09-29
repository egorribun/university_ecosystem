"""Credential, MFA, token and session schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import (
    EmailStr,
    Field,
    model_validator,
)

from app.models.auth import ChallengeState
from app.schemas.common import BaseModel, OrmModel


class PasswordResetTokenCreate(BaseModel):
    user_id: uuid.UUID  # RZ-33-17: was `int`, model uses UUID7 PKs
    token_hash: str
    expires_at: datetime
    used: bool = False


class EmailChangeTokenCreate(BaseModel):
    user_id: uuid.UUID  # RZ-33-17: was `int`, model uses UUID7 PKs
    new_email: EmailStr
    token_hash: str
    expires_at: datetime
    used: bool = False


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=200)


class UserEmailChangeIn(BaseModel):
    email: EmailStr
    password: str


class UserEmailConfirmIn(BaseModel):
    token: str


class UserPasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class MfaTotpEnrollmentOut(OrmModel):
    id: uuid.UUID
    user_id: uuid.UUID
    label: str | None = None
    is_active: bool
    confirmed_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime


class MfaChallengeOut(OrmModel):
    id: uuid.UUID
    user_id: uuid.UUID
    session_id: uuid.UUID | None = None
    challenge_type: str
    token: str
    expires_at: datetime
    consumed_at: datetime | None = None
    created_at: datetime
    payload: dict[str, Any] | None = None
    attempt_count: int = 0
    # TD-W5-01: Added after the original payload shape was persisted.  The
    # validator below preserves the state encoded by pre-migration payloads
    # that have no state field; ORM rows created after the migration expose the
    # enum value directly.
    state: ChallengeState = ChallengeState.PENDING

    @model_validator(mode="before")
    @classmethod
    def restore_legacy_state(cls, value: Any) -> Any:
        """Recover the MFA state encoded by the pre-enum payload shape.

        The migration introduced ``state`` after older serialized rows already
        existed.  Those rows used ``consumed_at``/``locked_at`` as the state
        machine.  Preserve that meaning when an old dict is read instead of
        silently defaulting a consumed or locked challenge to ``pending``.
        """
        if not isinstance(value, dict) or "state" in value:
            return value
        if value.get("locked_at") is not None:
            return {**value, "state": ChallengeState.LOCKED}
        if value.get("consumed_at") is not None:
            return {**value, "state": ChallengeState.CONSUMED}
        return value


class MfaFactorStatusOut(BaseModel):
    disabled: bool
    mfa_default_method: Literal["totp", "email_otp"] | None = None
    mfa_required: bool = False


class RecoveryCodesGenerateOut(BaseModel):
    codes: list[str]
    created_at: datetime


class RecoveryCodeVerifyIn(BaseModel):
    code: str


class UserMfaMethodsOut(BaseModel):
    totp_enrollments: list[MfaTotpEnrollmentOut] = Field(default_factory=list)


class PasswordChangeOut(BaseModel):
    ok: bool
    revoked_sessions: int = 0


class SessionBulkRevokeOut(BaseModel):
    revoked: int = 0


class Token(BaseModel):
    access_token: str | None = None
    token_type: str = "bearer"


class SessionSigningKeyOut(BaseModel):
    signing_key: str


class ActiveSessionOut(OrmModel):
    id: uuid.UUID
    user_id: uuid.UUID
    jti: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    last_seen_at: datetime | None = None
    mfa_required: bool = False
    mfa_completed_at: datetime | None = None
    mfa_method: Literal["totp", "email_otp", "recovery_code"] | None = None
    mfa_verified_at: datetime | None = None
    is_current: bool = False
