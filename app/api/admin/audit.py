from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import get_current_admin_user
from app.core.container import get_secure_audit_service_dep
from app.core.database import get_db
from app.models import models
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
            resource_type = None  # silently ignore unknown; prevents value enumeration
        else:
            stmt = stmt.where(DataAccessLog.resource_type == resource_type)
    if action:
        if action not in _ALLOWED_ACTIONS:
            action = None
        else:
            stmt = stmt.where(DataAccessLog.action == action)

    # Count total
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
