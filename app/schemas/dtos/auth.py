import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PasswordResetTokenDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    user_id: uuid.UUID
    token_hash: str
    expires_at: datetime
    used: bool
    created_at: datetime


class EmailChangeTokenDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    user_id: uuid.UUID
    new_email: str
    token_hash: str
    expires_at: datetime
    used: bool
    created_at: datetime
