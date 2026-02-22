import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AttendanceStatsDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    current_total: int
    previous_total: int
    current_attended: int
    previous_attended: int
    recent_attended_events: list[dict] = []  # Can be further refined if needed

class ParticipationStatsDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: uuid.UUID
    title: str
    event_type: str
    starts_at: datetime
    ends_at: datetime

class HealthStatsDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    active_connections: int
    commits: int
    rollbacks: int
    cache_hit_ratio: float
