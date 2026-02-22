import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    title_en: str | None = None
    body: str | None = None
    body_en: str | None = None
    type: str | None = None
    url: str | None = None
    dedupe_key: str | None = None
    read: bool = False
    read_at: datetime | None = None
    created_at: datetime
