"""Timetable schemas."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime

from pydantic import model_validator

from app.schemas.common import BaseModel, OrmModel


class ScheduleBase(BaseModel):
    group_id: uuid.UUID
    subject: str
    teacher: str | None = None
    room: str | None = None
    weekday: str
    start_time: datetime
    end_time: datetime
    parity: str | None = "both"
    lesson_type: str | None = None


class ScheduleCreate(ScheduleBase):
    pass


class ScheduleUpdate(BaseModel):
    # Keep nullable input types for older PATCH clients. Explicit null means
    # "leave unchanged" for fields that must be stored as non-null.
    group_id: uuid.UUID | None = None
    subject: str | None = None
    teacher: str | None = None
    room: str | None = None
    weekday: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    parity: str | None = None
    lesson_type: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _ignore_null_storage_fields(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value

        normalized = dict(value)
        required_fields = (
            "group_id",
            "subject",
            "weekday",
            "start_time",
            "end_time",
            "parity",
        )
        for field in required_fields:
            if field in normalized and normalized[field] is None:
                normalized.pop(field)
        return normalized


class ScheduleOut(OrmModel, ScheduleBase):
    id: uuid.UUID
    lesson_type_display: str | None = None
