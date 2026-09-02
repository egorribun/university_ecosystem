"""Admin-only operations for the notification delivery dead-letter queue."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_admin_user
from app.core.container import get_secure_audit_service_dep
from app.core.database import get_db, get_read_db
from app.schemas.schemas import (
    NotificationDeadLetterJobOut,
    NotificationDeadLetterListOut,
    NotificationDeadLetterMutationOut,
    NotificationDeadLetterPurgeIn,
    NotificationDeadLetterReplayIn,
)
from app.services.audit_service import SecureAuditService
from app.services.notification_queue import (
    StaleDeadLetterSelectionError,
    list_dead_lettered_jobs,
    purge_dead_lettered_jobs,
    retry_dead_lettered_jobs,
)

if TYPE_CHECKING:
    import app.models as models
    from app.core.protocols import AsyncDatabaseSession


router = APIRouter(
    prefix="/notifications/admin/dead-letter",
    tags=["admin-notifications"],
)

_ADMIN_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required"},
    status.HTTP_403_FORBIDDEN: {"description": "Administrator access required"},
}
_MUTATION_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_ADMIN_ERROR_RESPONSES,
    status.HTTP_409_CONFLICT: {"description": "Dead-letter selection is stale"},
}


def _to_public_job(job: object) -> NotificationDeadLetterJobOut:
    """Serialize a dead letter without exposing worker error payloads or PII."""
    output = NotificationDeadLetterJobOut.model_validate(job)

    def aware(value: datetime | None) -> datetime | None:
        return (
            value.replace(tzinfo=UTC)
            if value is not None and value.tzinfo is None
            else value
        )

    return output.model_copy(
        update={
            "enqueued_at": aware(output.enqueued_at),
            "claimed_at": aware(output.claimed_at),
            "next_retry_at": aware(output.next_retry_at),
            "last_error": "Delivery failed" if output.last_error else None,
        }
    )


@router.get(
    "",
    response_model=NotificationDeadLetterListOut,
    operation_id="listNotificationDeadLetters",
    summary="List notification queue dead letters",
    responses=_ADMIN_ERROR_RESPONSES,
)
async def list_notification_dead_letters(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
    db: AsyncDatabaseSession = Depends(get_read_db),
    _: models.User = Depends(get_current_admin_user),
) -> NotificationDeadLetterListOut:
    jobs, total = await list_dead_lettered_jobs(db, limit=limit, offset=offset)
    return NotificationDeadLetterListOut(
        items=[_to_public_job(job) for job in jobs],
        total=total,
    )


def _stale_selection() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Dead-letter selection is stale",
    )


@router.post(
    "/retry",
    response_model=NotificationDeadLetterMutationOut,
    operation_id="retryNotificationDeadLetters",
    summary="Retry notification queue dead letters",
    responses=_MUTATION_ERROR_RESPONSES,
)
async def retry_notification_dead_letters(
    payload: NotificationDeadLetterReplayIn,
    db: AsyncDatabaseSession = Depends(get_db),
    user: models.User = Depends(get_current_admin_user),
    audit: SecureAuditService = Depends(get_secure_audit_service_dep),
) -> NotificationDeadLetterMutationOut:
    try:
        affected = await retry_dead_lettered_jobs(
            db,
            payload.job_ids,
            audit=audit,
            actor_id=user.id,
        )
    except StaleDeadLetterSelectionError:
        raise _stale_selection() from None
    return NotificationDeadLetterMutationOut(
        success=True,
        affected_count=affected,
        job_ids=payload.job_ids,
    )


@router.post(
    "/purge",
    response_model=NotificationDeadLetterMutationOut,
    operation_id="purgeNotificationDeadLetters",
    summary="Purge notification queue dead letters",
    responses=_MUTATION_ERROR_RESPONSES,
)
async def purge_notification_dead_letters(
    payload: NotificationDeadLetterPurgeIn,
    db: AsyncDatabaseSession = Depends(get_db),
    user: models.User = Depends(get_current_admin_user),
    audit: SecureAuditService = Depends(get_secure_audit_service_dep),
) -> NotificationDeadLetterMutationOut:
    try:
        affected = await purge_dead_lettered_jobs(
            db,
            payload.job_ids,
            audit=audit,
            actor_id=user.id,
        )
    except StaleDeadLetterSelectionError:
        raise _stale_selection() from None
    return NotificationDeadLetterMutationOut(
        success=True,
        affected_count=affected,
        job_ids=payload.job_ids,
    )
