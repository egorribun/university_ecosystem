import uuid
from datetime import datetime

from pydantic import ConfigDict

from app.schemas.base import SecureBaseModel


class DataAccessLogDTO(SecureBaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    subject_user_id: uuid.UUID | None
    resource_type: str
    resource_id: str | None
    action: str
    context: dict | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime
    signature: str | None = None
