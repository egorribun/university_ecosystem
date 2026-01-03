from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import models
from app.models.logs import DataAccessLog
from app.schemas import schemas
from app.services.audit_service import get_secure_audit_service

router = APIRouter(prefix="/audit", tags=["admin-audit"])

def require_admin(user: models.User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user

@router.get("", response_model=schemas.AuditLogListOut)
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    actor_id: Optional[int] = None,
    subject_id: Optional[int] = None,
    resource_type: Optional[str] = None,
    action: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """List audit logs with filtering and integrity verification."""

    # Aliases for joining users table
    Actor = aliased(models.User)
    Subject = aliased(models.User)

    stmt = (
        select(
            DataAccessLog,
            Actor.full_name.label("actor_name"),
            Subject.full_name.label("subject_name")
        )
        .outerjoin(Actor, DataAccessLog.actor_user_id == Actor.id)
        .outerjoin(Subject, DataAccessLog.subject_user_id == Subject.id)
        .order_by(DataAccessLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    if actor_id:
        stmt = stmt.where(DataAccessLog.actor_user_id == actor_id)
    if subject_id:
        stmt = stmt.where(DataAccessLog.subject_user_id == subject_id)
    if resource_type:
        stmt = stmt.where(DataAccessLog.resource_type == resource_type)
    if action:
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

    # Verify integrity and map to output schema
    secure_audit = get_secure_audit_service()
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
                is_valid=is_valid
            )
        )

    return schemas.AuditLogListOut(items=items, total=total)
