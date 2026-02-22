from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DTOModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

class EventDTO(DTOModel):
    id: uuid.UUID
    title: str
    title_en: str | None
    description: str | None
    description_en: str | None
    location: str | None
    location_en: str | None
    event_type: str | None
    event_type_en: str | None
    starts_at: datetime
    ends_at: datetime
    created_by: uuid.UUID
    created_at: datetime
    is_active: bool
    speaker: str | None
    image_url: str | None
    about: str | None
    about_en: str | None
    attendance: list[EventAttendanceDTO] = []
    files_detail: list[EventFileDTO] = []

class EventAttendanceDTO(DTOModel):
    id: uuid.UUID
    user_id: uuid.UUID
    event_id: uuid.UUID
    registered_at: datetime | None = None
    qr_secret: str | None = None
    qr_hmac: str | None = None
    qr_token: str | None = None

class EventFileDTO(DTOModel):
    id: uuid.UUID
    event_id: uuid.UUID
    file_url: str
    description: str | None

class EventSearchResultDTO(DTOModel):
    event: EventDTO
    participant_count: int
    user_attendance: EventAttendanceDTO | None
