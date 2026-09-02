import uuid
from datetime import datetime

from pydantic import ConfigDict

from app.schemas.base import SecureBaseModel


class ActiveSessionDTO(SecureBaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

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
    mfa_method: str | None = None
    mfa_verified_at: datetime | None = None
    mfa_epoch: int = 0
    accept_language: str | None = None
    signing_key: str | None = None
    fingerprint_hash: str | None = None
