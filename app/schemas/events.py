"""Event, attachment and attendance schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import (
    Field,
    model_validator,
)

from app.core.localization import translate
from app.schemas.common import BaseModel, OrmModel
from app.schemas.validators import CleanStr, SafeRichText, SanitizedInput


class EventFileOut(OrmModel):
    id: uuid.UUID
    event_id: uuid.UUID
    file_url: str
    description: str | None = None

    @model_validator(mode="after")
    def protect_private_url(self) -> EventFileOut:
        """Expose event attachments only through the authorized download route."""

        from app.services.private_attachments import private_attachment_url

        object.__setattr__(
            self,
            "file_url",
            private_attachment_url("event", self.event_id, self.file_url),
        )
        return self


class EventCreate(BaseModel):
    title: CleanStr
    description: SafeRichText | None = None
    title_en: SanitizedInput = None
    description_en: SanitizedInput = None
    location: CleanStr | None = None
    location_en: SanitizedInput = None
    event_type: SanitizedInput = None
    event_type_en: SanitizedInput = None
    starts_at: datetime
    ends_at: datetime
    speaker: CleanStr | None = None
    image_url: str | None = None
    about: SafeRichText | None = None
    about_en: SanitizedInput = None

    @model_validator(mode="after")
    def _validate_time_order(self) -> EventCreate:
        if self.ends_at <= self.starts_at:
            raise ValueError(translate("validation.events.end_after_start"))
        return self


class EventUpdate(BaseModel):
    title: CleanStr | None = None
    description: SafeRichText | None = None
    title_en: SanitizedInput = None
    description_en: SanitizedInput = None
    location: CleanStr | None = None
    location_en: SanitizedInput = None
    event_type: SanitizedInput = None
    event_type_en: SanitizedInput = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool | None = None
    speaker: CleanStr | None = None
    image_url: str | None = None
    about: SafeRichText | None = None
    about_en: SanitizedInput = None

    @model_validator(mode="after")
    def _validate_time_updates(self) -> EventUpdate:
        provided = self.model_fields_set
        starts_set = "starts_at" in provided
        ends_set = "ends_at" in provided
        if starts_set ^ ends_set:
            raise ValueError(translate("validation.events.times_required"))
        if starts_set or ends_set:
            if self.starts_at is None or self.ends_at is None:
                raise ValueError(translate("validation.events.times_required"))
            if self.ends_at <= self.starts_at:
                raise ValueError(translate("validation.events.end_after_start"))
        return self


class EventOut(OrmModel):
    id: uuid.UUID
    title: str
    description: str | None = None
    title_en: str | None = None
    description_en: str | None = None
    location: str | None = None
    location_en: str | None = None
    event_type: str | None = None
    event_type_en: str | None = None
    starts_at: datetime
    ends_at: datetime
    created_by: str | Any
    created_at: datetime
    is_active: bool
    speaker: str | None = None
    image_url: str | None = None
    about: str | None = None
    about_en: str | None = None
    files: list[EventFileOut] = Field(
        default_factory=list, json_schema_extra={"default": []}
    )
    participant_count: int = 0
    is_registered: bool | None = None
    my_qr_token: str | None = None

    image_url_optimized: str | None = None


class PaginatedEvents(BaseModel):
    items: list[EventOut]
    total: int | None = None
    limit: int
    cursor: str | None = None
    next_cursor: str | None = None
    has_more: bool


class EventAttendanceCreate(BaseModel):
    event_id: uuid.UUID | int


class EventAttendanceOut(OrmModel):
    id: uuid.UUID
    user_id: uuid.UUID
    event_id: uuid.UUID
    registered_at: datetime
    qr_token: str | None = None
