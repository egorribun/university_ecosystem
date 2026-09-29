"""Administrative, audit and time-travel schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from app.schemas.common import BaseModel


class FeatureFlagOut(BaseModel):
    name: str
    enabled: bool
    default: bool
    description: str
    provider: str
    evaluation_reason: str
    management: Literal["gitops"]
    config_path: str


class AuditLogOut(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None = None
    actor_name: str | None = None
    subject_user_id: uuid.UUID | None = None
    subject_name: str | None = None
    resource_type: str
    resource_id: str | None = None
    action: str
    context: dict[str, Any] | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime
    is_valid: bool


class AuditLogListOut(BaseModel):
    items: list[AuditLogOut]
    total: int


class TimeTravelResponse(BaseModel):
    aggregate_type: str
    aggregate_id: uuid.UUID
    target_timestamp: datetime
    state_at_timestamp: dict[str, Any] | None
    version_at_timestamp: int | None = None
    events_replayed: int
    chain_integrity_valid: bool
    tampered_event_id: str | None = None
