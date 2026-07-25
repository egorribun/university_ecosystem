"""
Admin API endpoints for Dead Letter Queue monitoring.

These endpoints provide visibility into failed background jobs
and allow manual intervention for job processing.
"""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import get_current_admin_user, get_locale
from app.api.validation import raise_not_found, raise_validation_error
from app.core.database import get_db, get_read_db
from app.core.event_dlq import dead_letter_queue as in_memory_dlq
from app.core.ratelimit.circuit_breaker import get_circuit_breaker
from app.models import DeadLetterJob, JobStatus
from app.workers.dead_letter_queue import DeadLetterQueue

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    import app.models as models

router = APIRouter(prefix="/admin/dlq", tags=["admin"])


class DLQStatsResponse(BaseModel):
    """Response model for DLQ statistics."""

    pending: int
    retrying: int
    failed: int
    completed: int
    total_active: int


class DLQStatusResponse(BaseModel):
    """Response model for detailed DLQ & Circuit Breaker status."""

    in_memory_queue_depth: int
    in_memory_max_size: int
    in_memory_is_replaying: bool
    db_pending: int
    db_retrying: int
    db_failed: int
    db_completed: int
    db_total_active: int
    circuit_breaker_state: str
    circuit_breaker_failures: int
    is_replaying: bool


class DLQReplayRequest(BaseModel):
    """Request model for manual DLQ replay trigger."""

    batch_size: int = 20
    force: bool = False
    target: str = "all"  # "all", "in_memory", or "db"


class DLQReplayResponse(BaseModel):
    """Response model for DLQ replay execution."""

    success: bool
    target: str
    in_memory_replayed: int
    in_memory_failed: int
    db_replayed: int
    db_failed: int
    message: str


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
    "/status",
    response_model=DLQStatusResponse,
    summary="Get Detailed DLQ Status & Circuit Breaker Metrics",
    description=(
        "Returns comprehensive metrics on in-memory event DLQ queue depth, "
        "DB-backed dead letter jobs, circuit breaker state, and replay status."
    ),
)
async def get_dlq_status(
    db: AsyncSession = Depends(get_read_db),
    _: models.User = Depends(get_current_admin_user),
) -> DLQStatusResponse:
    """Get comprehensive DLQ status and circuit breaker metrics."""
    db_dlq = DeadLetterQueue(db)
    db_stats = await db_dlq.get_queue_stats()

    in_mem_status = await in_memory_dlq.get_replay_status()
    cb = get_circuit_breaker()
    cb_state = cb.state.name

    db_pending = db_stats.get(JobStatus.PENDING.value, 0)
    db_retrying = db_stats.get(JobStatus.RETRYING.value, 0)
    db_failed = db_stats.get(JobStatus.FAILED.value, 0)
    db_completed = db_stats.get(JobStatus.COMPLETED.value, 0)
    db_active = db_pending + db_retrying

    is_replaying = bool(in_mem_status.get("is_replaying", False)) or bool(
        getattr(DeadLetterQueue, "_is_replaying", False)
    )

    return DLQStatusResponse(
        in_memory_queue_depth=in_mem_status.get("size", 0),
        in_memory_max_size=in_mem_status.get("max_size", 1000),
        in_memory_is_replaying=bool(in_mem_status.get("is_replaying", False)),
        db_pending=db_pending,
        db_retrying=db_retrying,
        db_failed=db_failed,
        db_completed=db_completed,
        db_total_active=db_active,
        circuit_breaker_state=cb_state,
        circuit_breaker_failures=getattr(cb, "_failure_count", 0),
        is_replaying=is_replaying,
    )


@router.post(
    "/replay",
    response_model=DLQReplayResponse,
    summary="Trigger Manual DLQ Replay",
    description=(
        "Manually triggers DLQ replay for in-memory events, DB dead letter jobs, "
        "or both, with options for batch size and forcing execution regardless of circuit breaker state."
    ),
)
async def trigger_dlq_replay(
    request: DLQReplayRequest = DLQReplayRequest(),
    db: AsyncSession = Depends(get_db),
    locale: str = Depends(get_locale),
    _: models.User = Depends(get_current_admin_user),
) -> DLQReplayResponse:
    """Manually trigger DLQ replay for in-memory domain events and/or DB jobs."""
    if request.target not in ("all", "in_memory", "db"):
        raise_validation_error(
            "errors.dlq.invalid_target",
            locale,
            targets="all, in_memory, db",
        )

    in_mem_success, in_mem_failed = 0, 0
    db_success, db_failed = 0, 0

    if request.target in ("all", "in_memory"):
        in_mem_success, in_mem_failed = await in_memory_dlq.auto_replay(
            batch_size=request.batch_size,
            force=request.force,
        )

    if request.target in ("all", "db"):
        db_dlq = DeadLetterQueue(db)
        cb = get_circuit_breaker()
        db_success, db_failed = await db_dlq.auto_replay_jobs(
            batch_size=request.batch_size,
            circuit_breaker=cb,
            force=request.force,
        )
        await db.commit()

    total_replayed = in_mem_success + db_success
    total_failed = in_mem_failed + db_failed

    return DLQReplayResponse(
        success=total_failed == 0,
        target=request.target,
        in_memory_replayed=in_mem_success,
        in_memory_failed=in_mem_failed,
        db_replayed=db_success,
        db_failed=db_failed,
        message=f"Replayed {total_replayed} items ({total_failed} failures)",
    )


@router.get(
    "/stats",
    response_model=DLQStatsResponse,
    summary="Get DLQ Statistics",
    description=(
        "Returns counts of jobs by status (pending, retrying, failed, completed) "
        "for monitoring dashboards."
    ),
)
async def get_dlq_stats(
    db: AsyncSession = Depends(get_read_db),
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
    description=(
        "Returns a paginated list of jobs in the dead letter queue "
        "with optional status filtering."
    ),
)
async def list_dlq_jobs(
    status: str | None = None,
    limit: int = Query(
        default=20, ge=1, le=500
    ),  # MED-W19: cap at 500 to prevent large scans
    db: AsyncSession = Depends(get_read_db),
    locale: str = Depends(get_locale),
    _: models.User = Depends(get_current_admin_user),
) -> DLQJobsListResponse:
    """
    List jobs in the Dead Letter Queue.

    Optionally filter by status (pending, retrying, failed, completed).
    """
    from sqlalchemy import func, select

    query = select(DeadLetterJob)

    if status:
        # Validate status
        valid_statuses = [s.value for s in JobStatus]
        if status not in valid_statuses:
            raise_validation_error(
                "errors.dlq.invalid_status",
                locale,
                statuses=", ".join(valid_statuses),
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
    description=(
        "Manually triggers a retry for a specific failed job by resetting "
        "its status to pending."
    ),
)
async def retry_dlq_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    locale: str = Depends(get_locale),
    _: models.User = Depends(get_current_admin_user),
) -> dict[str, Any]:
    """
    Manually trigger a retry for a specific DLQ job.

    Resets the job status to pending for immediate retry.
    """
    from datetime import datetime

    from sqlalchemy import select

    result = await db.execute(select(DeadLetterJob).where(DeadLetterJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise_not_found(
            "dlq_job", locale, resource_id=job_id, exact_key="errors.events.not_found"
        )
        raise ValueError("Unreachable")

    # Reset for retry
    job.status = JobStatus.PENDING.value
    job.retry_count = (
        0  # MED-W19: reset counter so the worker gets a clean retry budget
    )
    job.next_retry_at = datetime.now(UTC)
    job.updated_at = datetime.now(UTC)

    await db.commit()

    from app.core.localization import translate

    return {
        "success": True,
        "message": translate("success.dlq.retry_queued", locale=locale, job_id=job_id),
        "job_type": job.job_type,
    }


@router.delete(
    "/cleanup",
    summary="Cleanup DLQ",
    description=(
        "Removes completed jobs older than the specified number of days "
        "(default: 7) to free up storage."
    ),
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
