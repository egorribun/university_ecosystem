"""In-app notification delivery and dead-letter schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import (
    ConfigDict,
    Field,
    field_validator,
)

from app.schemas.common import BaseModel, OrmModel
from app.schemas.validators import SanitizedInput


class NotificationCreate(BaseModel):
    user_id: uuid.UUID
    title: str
    body: str | None = None
    title_en: SanitizedInput = None
    body_en: SanitizedInput = None
    type: SanitizedInput = None
    url: SanitizedInput = None


class NotificationOut(OrmModel):
    id: uuid.UUID
    title: str
    body: str | None = None
    title_en: SanitizedInput = None
    body_en: SanitizedInput = None
    type: SanitizedInput = None
    url: SanitizedInput = None
    topic: SanitizedInput = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    read: bool
    read_at: datetime | None = None


class NotificationsListOut(BaseModel):
    items: list[NotificationOut]
    unread_count: int
    has_more: bool
    next_cursor: str | None = None


class NotificationMarkReadIn(BaseModel):
    id: uuid.UUID | None = None
    ids: list[str | Any] | None = None


class NotificationDeadLetterJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: uuid.UUID
    kind: str
    record_id: uuid.UUID
    locale: str | None = None
    enqueued_at: datetime
    claimed_at: datetime | None = None
    attempts: int
    last_error: str | None = None
    next_retry_at: datetime | None = None


class NotificationDeadLetterListOut(BaseModel):
    items: list[NotificationDeadLetterJobOut]
    total: int


class _NotificationDeadLetterJobIds(BaseModel):
    job_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)

    @field_validator("job_ids")
    @classmethod
    def _ensure_unique(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(value)) != len(value):
            raise ValueError("job_ids must not contain duplicate values")
        return value


class NotificationDeadLetterReplayIn(_NotificationDeadLetterJobIds):
    pass


class NotificationDeadLetterPurgeIn(_NotificationDeadLetterJobIds):
    pass


class NotificationDeadLetterMutationOut(BaseModel):
    success: Literal[True]
    affected_count: int = Field(ge=0)
    job_ids: list[uuid.UUID]
