"""
Admin API endpoints for Dead Letter Queue monitoring.

These endpoints provide visibility into failed background jobs
and allow manual intervention for job processing.
"""

from __future__ import annotations

from datetime import UTC
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user
from app.core.database import get_db
from app.models import models
from app.workers.dead_letter_queue import DeadLetterQueue, JobStatus

router = APIRouter(prefix="/admin/dlq", tags=["admin"])


class DLQStatsResponse(BaseModel):
    """Response model for DLQ statistics."""

    pending: int
    retrying: int
    failed: int
    completed: int
    total_active: int


class DLQJobResponse(BaseModel):
    """Response model for a single DLQ job."""

    id: int
    job_type: str
    job_hash: str
    error_message: str | None
    retry_count: int
    max_retries: int
    status: str
    next_retry_at: str | None
    created_at: str
    updated_at: str


class DLQJobsListResponse(BaseModel):
    """Response model for listing DLQ jobs."""

    jobs: list[DLQJobResponse]
    total: int


@router.get(
    "/stats",
    response_model=DLQStatsResponse,
    summary="Get DLQ Statistics",
    description="Returns counts of jobs by status (pending, retrying, failed, completed) for monitoring dashboards.",
)
async def get_dlq_stats(
    db: AsyncSession = Depends(get_db),
    _: models.User = Depends(get_current_admin_user),
) -> DLQStatsResponse:
    """
    Get Dead Letter Queue statistics.

    Returns counts of jobs by status for monitoring dashboards.
    """
    dlq = DeadLetterQueue(db)
    stats = await dlq.get_queue_stats()

    return DLQStatsResponse(
        pending=stats.get(JobStatus.PENDING.value, 0),
        retrying=stats.get(JobStatus.RETRYING.value, 0),
        failed=stats.get(JobStatus.FAILED.value, 0),
        completed=stats.get(JobStatus.COMPLETED.value, 0),
        total_active=stats.get(JobStatus.PENDING.value, 0)
        + stats.get(JobStatus.RETRYING.value, 0),
    )


@router.get(
    "/jobs",
    response_model=DLQJobsListResponse,
    summary="List DLQ Jobs",
    description="Returns a paginated list of jobs in the dead letter queue with optional status filtering.",
)
async def list_dlq_jobs(
    status: str | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _: models.User = Depends(get_current_admin_user),
) -> DLQJobsListResponse:
    """
    List jobs in the Dead Letter Queue.

    Optionally filter by status (pending, retrying, failed, completed).
    """
    from sqlalchemy import func, select

    from app.workers.dead_letter_queue import DeadLetterJob

    query = select(DeadLetterJob)

    if status:
        # Validate status
        valid_statuses = [s.value for s in JobStatus]
        if status not in valid_statuses:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
            )
        query = query.where(DeadLetterJob.status == status)

    query = query.order_by(DeadLetterJob.created_at.desc()).limit(limit)
    result = await db.execute(query)
    jobs = result.scalars().all()

    # Get total count
    count_query = select(func.count(DeadLetterJob.id))
    if status:
        count_query = count_query.where(DeadLetterJob.status == status)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return DLQJobsListResponse(
        jobs=[
            DLQJobResponse(
                id=job.id,
                job_type=job.job_type,
                job_hash=job.job_hash[:16] + "...",  # Truncate for display
                error_message=job.error_message[:200] if job.error_message else None,
                retry_count=job.retry_count,
                max_retries=job.max_retries,
                status=job.status,
                next_retry_at=(
                    job.next_retry_at.isoformat() if job.next_retry_at else None
                ),
                created_at=job.created_at.isoformat(),
                updated_at=job.updated_at.isoformat(),
            )
            for job in jobs
        ],
        total=total,
    )


@router.post(
    "/retry/{job_id}",
    summary="Retry DLQ Job",
    description="Manually triggers a retry for a specific failed job by resetting its status to pending.",
)
async def retry_dlq_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    _: models.User = Depends(get_current_admin_user),
) -> dict[str, Any]:
    """
    Manually trigger a retry for a specific DLQ job.

    Resets the job status to pending for immediate retry.
    """
    from datetime import datetime

    from sqlalchemy import select

    from app.workers.dead_letter_queue import DeadLetterJob

    result = await db.execute(select(DeadLetterJob).where(DeadLetterJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID {job_id} not found",
        )

    # Reset for retry
    job.status = JobStatus.PENDING.value
    job.next_retry_at = datetime.now(UTC)
    job.updated_at = datetime.now(UTC)

    await db.commit()

    return {
        "success": True,
        "message": f"Job {job_id} queued for retry",
        "job_type": job.job_type,
    }


@router.delete(
    "/cleanup",
    summary="Cleanup DLQ",
    description="Removes completed jobs older than the specified number of days (default: 7) to free up storage.",
)
async def cleanup_dlq(
    older_than_days: int = 7,
    db: AsyncSession = Depends(get_db),
    _: models.User = Depends(get_current_admin_user),
) -> dict[str, Any]:
    """
    Clean up completed jobs from the Dead Letter Queue.

    Removes completed jobs older than the specified number of days.
    """
    dlq = DeadLetterQueue(db)
    deleted = await dlq.cleanup_completed_jobs(older_than_days=older_than_days)

    return {
        "success": True,
        "deleted_count": deleted,
        "older_than_days": older_than_days,
    }
