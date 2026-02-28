import uuid
from datetime import datetime

from pydantic import ConfigDict

from app.schemas.base import SecureBaseModel


class PasswordResetTokenDTO(SecureBaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    user_id: uuid.UUID
    token_hash: str
    expires_at: datetime
    used: bool
    created_at: datetime


class EmailChangeTokenDTO(SecureBaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    user_id: uuid.UUID
    new_email: str
    token_hash: str
    expires_at: datetime
    used: bool
    created_at: datetime
