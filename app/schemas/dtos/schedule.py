import uuid
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict


class DTOModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)


class GroupDTO(DTOModel):
    id: uuid.UUID
    name: str
    created_at: datetime


class ScheduleDTO(DTOModel):
    id: uuid.UUID
    group_id: uuid.UUID
    weekday: int
    start_time: time
    end_time: time
    subject: str
    teacher: str | None
    room: str | None
    parity: str = "both"
    created_at: datetime
