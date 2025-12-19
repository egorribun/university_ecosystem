"""
Dead Letter Queue (DLQ) for failed background job processing.

This module provides:
- Storage for failed jobs with retry metadata
- Job deduplication to prevent duplicate processing
- Metrics for monitoring DLQ health
- Automatic retry with exponential backoff
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    delete,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Status of a job in the dead letter queue."""

    PENDING = "pending"
    RETRYING = "retrying"
    FAILED = "failed"  # Permanently failed after max retries
    COMPLETED = "completed"


class DeadLetterJob(Base):
    """Model for storing failed jobs in the dead letter queue."""

    __tablename__ = "dead_letter_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_type = Column(String(100), nullable=False, index=True)
    job_hash = Column(String(64), nullable=False, unique=True)  # For deduplication
    payload = Column(Text, nullable=False)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    status = Column(String(20), default=JobStatus.PENDING.value, nullable=False, index=True)
    next_retry_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (Index("ix_dlq_status_next_retry", "status", "next_retry_at"),)


def compute_job_hash(job_type: str, payload: dict[str, Any]) -> str:
    """Compute a unique hash for job deduplication."""
    content = json.dumps({"type": job_type, "payload": payload}, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


class DeadLetterQueue:
    """Manager for the dead letter queue."""

    BASE_BACKOFF_SECONDS = 60  # 1 minute
    MAX_BACKOFF_SECONDS = 3600  # 1 hour

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_failed_job(
        self,
        job_type: str,
        payload: dict[str, Any],
        error_message: str,
        max_retries: int = 3,
    ) -> DeadLetterJob | None:
        """
        Add a failed job to the dead letter queue.

        Returns the created job, or None if a duplicate already exists.
        """
        job_hash = compute_job_hash(job_type, payload)

        # Check for duplicate
        existing = await self.session.execute(
            select(DeadLetterJob).where(DeadLetterJob.job_hash == job_hash)
        )
        if existing.scalar_one_or_none():
            logger.debug(
                "Duplicate job detected, skipping: type=%s, hash=%s",
                job_type,
                job_hash[:8],
            )
            return None

        # Calculate next retry time with exponential backoff
        next_retry = datetime.now(UTC) + timedelta(seconds=self.BASE_BACKOFF_SECONDS)

        job = DeadLetterJob(
            job_type=job_type,
            job_hash=job_hash,
            payload=json.dumps(payload),
            error_message=error_message,
            max_retries=max_retries,
            next_retry_at=next_retry,
        )

        self.session.add(job)
        await self.session.commit()

        logger.info(
            "Added job to DLQ: type=%s, hash=%s, next_retry=%s",
            job_type,
            job_hash[:8],
            next_retry.isoformat(),
        )

        return job

    async def get_jobs_ready_for_retry(self, limit: int = 10) -> list[DeadLetterJob]:
        """Get jobs that are ready to be retried."""
        now = datetime.now(UTC)

        result = await self.session.execute(
            select(DeadLetterJob)
            .where(
                DeadLetterJob.status.in_([JobStatus.PENDING.value, JobStatus.RETRYING.value]),
                DeadLetterJob.next_retry_at <= now,
            )
            .order_by(DeadLetterJob.next_retry_at)
            .limit(limit)
        )

        return list(result.scalars().all())

    async def mark_job_retrying(self, job: DeadLetterJob) -> None:
        """Mark a job as currently being retried."""
        job.status = JobStatus.RETRYING.value
        job.retry_count += 1
        job.updated_at = datetime.now(UTC)
        await self.session.commit()

    async def mark_job_completed(self, job: DeadLetterJob) -> None:
        """Mark a job as successfully completed after retry."""
        job.status = JobStatus.COMPLETED.value
        job.updated_at = datetime.now(UTC)
        await self.session.commit()

        logger.info(
            "DLQ job completed: type=%s, hash=%s, retries=%d",
            job.job_type,
            job.job_hash[:8],
            job.retry_count,
        )

    async def mark_job_failed(
        self,
        job: DeadLetterJob,
        error_message: str,
    ) -> None:
        """Mark a job as failed after a retry attempt."""
        job.error_message = error_message
        job.updated_at = datetime.now(UTC)

        if job.retry_count >= job.max_retries:
            job.status = JobStatus.FAILED.value
            job.next_retry_at = None
            logger.error(
                "DLQ job permanently failed: type=%s, hash=%s, retries=%d, error=%s",
                job.job_type,
                job.job_hash[:8],
                job.retry_count,
                error_message[:200],
            )
        else:
            job.status = JobStatus.PENDING.value
            backoff = min(
                self.BASE_BACKOFF_SECONDS * (2**job.retry_count),
                self.MAX_BACKOFF_SECONDS,
            )
            job.next_retry_at = datetime.now(UTC) + timedelta(seconds=backoff)
            logger.warning(
                "DLQ job failed, will retry: type=%s, hash=%s, retry=%d/%d, next=%s",
                job.job_type,
                job.job_hash[:8],
                job.retry_count,
                job.max_retries,
                job.next_retry_at.isoformat(),
            )

        await self.session.commit()

    async def get_queue_stats(self) -> dict[str, int]:
        """Get statistics about the dead letter queue."""
        result = await self.session.execute(
            select(
                DeadLetterJob.status,
                func.count(DeadLetterJob.id).label("count"),
            ).group_by(DeadLetterJob.status)
        )

        stats: dict[str, int] = {
            JobStatus.PENDING.value: 0,
            JobStatus.RETRYING.value: 0,
            JobStatus.FAILED.value: 0,
            JobStatus.COMPLETED.value: 0,
        }

        for row in result:
            stats[row.status] = row.count

        return stats

    async def cleanup_completed_jobs(self, older_than_days: int = 7) -> int:
        """Remove completed jobs older than the specified number of days."""
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)

        result = await self.session.execute(
            delete(DeadLetterJob).where(
                DeadLetterJob.status == JobStatus.COMPLETED.value,
                DeadLetterJob.updated_at < cutoff,
            )
        )

        await self.session.commit()
        deleted = result.rowcount or 0

        if deleted > 0:
            logger.info("Cleaned up %d completed DLQ jobs", deleted)

        return deleted


async def check_duplicate_job(
    session: AsyncSession,
    job_type: str,
    payload: dict[str, Any],
) -> bool:
    """
    Check if a job with the same type and payload already exists.

    Returns True if a duplicate exists (job should be skipped).
    """
    job_hash = compute_job_hash(job_type, payload)

    result = await session.execute(
        select(DeadLetterJob.id).where(
            DeadLetterJob.job_hash == job_hash,
            DeadLetterJob.status.in_(
                [
                    JobStatus.PENDING.value,
                    JobStatus.RETRYING.value,
                ]
            ),
        )
    )

    return result.scalar_one_or_none() is not None
