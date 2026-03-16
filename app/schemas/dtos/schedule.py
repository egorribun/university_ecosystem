import uuid
from datetime import UTC, datetime, time

from pydantic import ConfigDict, Field

from app.schemas.base import SecureBaseModel


class DTOModel(SecureBaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)


class GroupDTO(DTOModel):
    id: uuid.UUID
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ScheduleDTO(DTOModel):
    id: uuid.UUID
    group_id: uuid.UUID
    weekday: int | str
    start_time: datetime | time
    end_time: datetime | time
    subject: str
    teacher: str | None
    room: str | None
    parity: str = "both"
    lesson_type: str | None = None
    creator_id: uuid.UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
