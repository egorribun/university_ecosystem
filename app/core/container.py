from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps.cache import BaseCache, get_cache
from app.services.audit_service import (
    AuditService,
    SecureAuditService,
    get_secure_audit_service,
)
from app.services.auth_service import AuthService
from app.services.group_service import GroupService
from app.services.notification_service import NotificationService
from app.services.user_service import UserService
from app.services.vector_service import VectorService

if TYPE_CHECKING:
    from app.cqrs.queries import GetScheduleHandler, GetStatsHandler


def get_audit_service() -> AuditService:
    return AuditService()


def get_secure_audit_service_dep() -> SecureAuditService:
    return get_secure_audit_service()


def get_group_service(
    db: AsyncSession = Depends(get_db),
) -> GroupService:
    return GroupService(db=db)


def get_notification_service(
    db: AsyncSession = Depends(get_db),
) -> NotificationService:
    return NotificationService(db=db)


def get_vector_service(
    db: AsyncSession = Depends(get_db),
) -> VectorService:
    return VectorService(db=db)


def get_user_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
    notifications: NotificationService = Depends(get_notification_service),
) -> UserService:
    return UserService(db=db, audit=audit, notifications=notifications)


def get_schedule_handler(
    db: AsyncSession = Depends(get_db),
    cache: BaseCache = Depends(get_cache),
) -> GetScheduleHandler:
    from app.cqrs.queries import GetScheduleHandler

    return GetScheduleHandler(db=db, cache=cache)


def get_stats_handler(
    db: AsyncSession = Depends(get_db),
    cache: BaseCache = Depends(get_cache),
) -> GetStatsHandler:
    from app.cqrs.queries import GetStatsHandler

    return GetStatsHandler(db=db, cache=cache)


def get_auth_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> AuthService:
    return AuthService(db=db, audit=audit)
