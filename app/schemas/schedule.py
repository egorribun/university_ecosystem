"""Timetable schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field, model_validator
from pydantic.json_schema import SkipJsonSchema

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
    group_id: uuid.UUID | SkipJsonSchema[None] = Field(default_factory=lambda: None)
    subject: str | SkipJsonSchema[None] = Field(default_factory=lambda: None)
    teacher: str | None = None
    room: str | None = None
    weekday: str | SkipJsonSchema[None] = Field(default_factory=lambda: None)
    start_time: datetime | SkipJsonSchema[None] = Field(default_factory=lambda: None)
    end_time: datetime | SkipJsonSchema[None] = Field(default_factory=lambda: None)
    parity: str | SkipJsonSchema[None] = Field(default_factory=lambda: None)
    lesson_type: str | None = None

    @model_validator(mode="after")
    def _reject_null_storage_fields(self) -> ScheduleUpdate:
        required_fields = (
            "group_id",
            "subject",
            "weekday",
            "start_time",
            "end_time",
            "parity",
        )
        explicitly_null = [
            field
            for field in required_fields
            if field in self.model_fields_set and getattr(self, field) is None
        ]
        if explicitly_null:
            raise ValueError(
                "Schedule fields cannot be null: " + ", ".join(explicitly_null)
            )
        return self


class ScheduleOut(OrmModel, ScheduleBase):
    id: uuid.UUID
    lesson_type_display: str | None = None
