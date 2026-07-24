from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

import app.models as models
from app.api.deps import get_current_admin_user
from app.core.container import get_secure_audit_service_dep
from app.core.database import get_db
from app.models.logs import DataAccessLog
from app.schemas import schemas
from app.services.audit_service import SecureAuditService

router = APIRouter(prefix="/audit", tags=["admin-audit"])

# TD-W5-03: Whitelist for audit filter params prevents enumeration of
# arbitrary DB column values and self-documents the data model.
_ALLOWED_RESOURCE_TYPES: frozenset[str] = frozenset(
    {"event", "profile", "semester", "file", "chat", "news", "notification", "session"}
)
_ALLOWED_ACTIONS: frozenset[str] = frozenset(
    {
        "auth.login.success",
        "auth.login.failure",
        "auth.logout",
        "auth.logout.revoked",
        "auth.register",
        "auth.token.refresh",
        "mfa.enroll.start",
        "mfa.enroll.complete",
        "mfa.verify.success",
        "mfa.verify.failure",
        "mfa.disable",
        "mfa.recovery_code.used",
        "password.change",
        "password.reset.request",
        "password.reset.complete",
        "users.profile.update",
        "users.email.change",
        "users.avatar.upload",
        "users.delete",
        "admin.user.create",
        "admin.user.modify",
        "admin.user.delete",
        "admin.role.change",
        "access.denied",
        "access.rate_limit",
        "data.view",
        "data.export",
        "data.modify",
        "data.delete",
    }
)


@router.get("", response_model=schemas.AuditLogListOut)
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    actor_id: UUID | None = None,
    subject_id: UUID | None = None,
    resource_type: str | None = None,
    action: str | None = None,
    db: AsyncSession = Depends(get_db),
    secure_audit: SecureAuditService = Depends(get_secure_audit_service_dep),
    _: models.User = Depends(get_current_admin_user),
) -> schemas.AuditLogListOut:
    """List audit logs with filtering and integrity verification."""

    # Aliases for joining users and their profiles for both actor and subject
    Actor = aliased(models.User)
    ActorProfile = aliased(models.UserProfile)
    Subject = aliased(models.User)
    SubjectProfile = aliased(models.UserProfile)

    stmt = (
        select(
            DataAccessLog,
            ActorProfile.full_name.label("actor_name"),
            SubjectProfile.full_name.label("subject_name"),
        )
        .outerjoin(Actor, DataAccessLog.actor_user_id == Actor.id)
        .outerjoin(ActorProfile, Actor.id == ActorProfile.user_id)
        .outerjoin(Subject, DataAccessLog.subject_user_id == Subject.id)
        .outerjoin(SubjectProfile, Subject.id == SubjectProfile.user_id)
        .order_by(DataAccessLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    if actor_id:
        stmt = stmt.where(DataAccessLog.actor_user_id == actor_id)
    if subject_id:
        stmt = stmt.where(DataAccessLog.subject_user_id == subject_id)
    if resource_type:
        if resource_type not in _ALLOWED_RESOURCE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_resource_type",
                    "allowed": sorted(_ALLOWED_RESOURCE_TYPES),
                },
            )
        stmt = stmt.where(DataAccessLog.resource_type == resource_type)
    if action:
        if action not in _ALLOWED_ACTIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_action",
                    "allowed": sorted(_ALLOWED_ACTIONS),
                },
            )
        stmt = stmt.where(DataAccessLog.action == action)

    # Count total — filters mirror stmt exactly (no silent coercion above)
    count_stmt = select(func.count(DataAccessLog.id))
    if actor_id:
        count_stmt = count_stmt.where(DataAccessLog.actor_user_id == actor_id)
    if subject_id:
        count_stmt = count_stmt.where(DataAccessLog.subject_user_id == subject_id)
    if resource_type:
        count_stmt = count_stmt.where(DataAccessLog.resource_type == resource_type)
    if action:
        count_stmt = count_stmt.where(DataAccessLog.action == action)

    # Execute queries
    result = await db.execute(stmt)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    items = []

    for row in result:
        log, actor_name, subject_name = row

        # Verify cryptographic signature
        is_valid = secure_audit.verify_integrity(log)

        items.append(
            schemas.AuditLogOut(
                id=log.id,
                actor_user_id=log.actor_user_id,
                actor_name=actor_name,
                subject_user_id=log.subject_user_id,
                subject_name=subject_name,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                action=log.action,
                context=log.context,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                created_at=log.created_at,
                is_valid=is_valid,
            )
        )

    return schemas.AuditLogListOut(items=items, total=total)


@router.get("/time-travel", response_model=schemas.TimeTravelResponse)
async def get_time_travel_state(
    aggregate_type: str = Query(
        ..., description="Aggregate type: 'schedule', 'grade', 'user', 'assessment'"
    ),
    aggregate_id: UUID = Query(..., description="UUID of the aggregate entity"),
    target_timestamp: datetime | None = Query(
        None, alias="target_timestamp", description="Target timestamp in ISO format"
    ),
    timestamp: datetime | None = Query(
        None, alias="timestamp", description="Target timestamp alias"
    ),
    verify_chain: bool = Query(
        True, description="Verify HMAC chain integrity up to target timestamp"
    ),
    db: AsyncSession = Depends(get_db),
    secure_audit: SecureAuditService = Depends(get_secure_audit_service_dep),
    _: models.User = Depends(get_current_admin_user),
) -> schemas.TimeTravelResponse:
    """Reconstruct state of an aggregate entity at a target timestamp in history."""
    ts = target_timestamp or timestamp
    if not ts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required query parameter: target_timestamp or timestamp",
        )

    allowed_types = {"schedule", "grade", "user", "assessment"}
    if aggregate_type.lower() not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_aggregate_type",
                "allowed": sorted(allowed_types),
            },
        )

    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)

    state, count, is_valid = await secure_audit.reconstruct_state(
        db,
        aggregate_type=aggregate_type.lower(),
        aggregate_id=aggregate_id,
        target_timestamp=ts,
        verify_chain=verify_chain,
    )

    if state is None and count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No event history found for {aggregate_type}:{aggregate_id} prior to {ts.isoformat()}",
        )

    version_at_t = state.get("_version") if isinstance(state, dict) else None

    return schemas.TimeTravelResponse(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        target_timestamp=ts,
        state_at_timestamp=state,
        version_at_timestamp=version_at_t,
        events_replayed=count,
        chain_integrity_valid=is_valid,
    )
