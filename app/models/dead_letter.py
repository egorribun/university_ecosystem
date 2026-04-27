from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    DateTime,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class JobStatus(StrEnum):
    """Status of a job in the dead letter queue."""

    PENDING = "pending"
    RETRYING = "retrying"
    FAILED = "failed"  # Permanently failed after max retries
    COMPLETED = "completed"


class DeadLetterJob(Base):
    """Model for storing failed jobs in the dead letter queue.

    RZ-011 (audit 2026-03-04): migrated from legacy Column() API to
    SQLAlchemy 2.x Mapped[T] = mapped_column() for full type-safety.
    """

    __tablename__ = "dead_letter_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    job_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(default=3, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=JobStatus.PENDING.value, nullable=False, index=True
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (Index("ix_dlq_status_next_retry", "status", "next_retry_at"),)

    def __repr__(self) -> str:
        return f"<DeadLetterJob(id={self.id}, job_type='{self.job_type}', status='{self.status}')>"

    def __init__(self, **kwargs: Any) -> None:
        kwargs.pop("_allow_system_managed_assignment", False)
        super().__init__(**kwargs)
