"""Dead Letter Queue for unrecoverable outbox events.

MOD-08 (audit 2026-03-14): Events that exceed max_retries are moved here for
manual inspection and replay rather than being silently abandoned.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, UUID, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import UUID7PrimaryKeyMixin


class FailedOutboxEvent(Base, UUID7PrimaryKeyMixin):
    """Stores outbox events that could not be delivered after max_retries attempts."""

    __tablename__ = "failed_outbox_events"

    original_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(
        String(128), nullable=False
    )  # LOW-W19: bounded String (was 50, too tight)
    aggregate_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<FailedOutboxEvent(event_type={self.event_type!r}, "
            f"aggregate={self.aggregate_type}:{self.aggregate_id}, "
            f"retries={self.retry_count})>"
        )
