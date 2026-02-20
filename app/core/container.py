from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_read_db
from app.deps.cache import BaseCache, get_cache
from app.repositories.auth_repository import get_auth_repository
from app.repositories.event_repository import get_event_repository
from app.repositories.news_repository import get_news_repository
from app.repositories.user_repository import get_user_repository
from app.services.audit_service import (
    AuditService,
    SecureAuditService,
    get_secure_audit_service,
)
from app.services.auth_service import AuthService
from app.services.event_service import EventService
from app.services.group_service import GroupService
from app.services.news_service import NewsService
from app.services.notification_service import NotificationService
from app.services.user.admin_service import UserAdminService
from app.services.user.data_service import UserDataService
from app.services.user.profile_service import UserProfileService
from app.services.user_service import UserService
from app.services.vector_service import VectorService

if TYPE_CHECKING:
    from app.cqrs.queries import GetScheduleHandler, GetStatsHandler
    from app.services.user.analytics_service import UserAnalyticsService


def get_audit_service() -> AuditService:
    return AuditService()


def get_secure_audit_service_dep() -> SecureAuditService:
    return get_secure_audit_service()


def get_group_service(
    db: AsyncSession = Depends(get_db),
) -> GroupService:
    from app.repositories.schedule_repository import GroupRepository

    repo = GroupRepository(db)
    return GroupService(db=db, repo=repo)


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
    repo = get_user_repository(db)
    return UserService(
        user_repo=repo,
        audit=audit,
        notifications=notifications,
    )


def get_user_profile_service(
    db: AsyncSession = Depends(get_db),
) -> UserProfileService:
    repo = get_user_repository(db)
    return UserProfileService(repo=repo)


def get_user_admin_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
    notifications: NotificationService = Depends(get_notification_service),
) -> UserAdminService:
    repo = get_user_repository(db)
    return UserAdminService(repo=repo, audit=audit, notifications=notifications)


def get_user_data_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> UserDataService:
    repo = get_user_repository(db)
    return UserDataService(repo=repo, audit=audit)


def get_event_service(
    db: AsyncSession = Depends(get_db),
    vector_service: VectorService = Depends(get_vector_service),
) -> EventService:
    repo = get_event_repository(db)
    return EventService(repo=repo, vector_service=vector_service)


def get_news_service(
    db: AsyncSession = Depends(get_db),
    vector_service: VectorService = Depends(get_vector_service),
) -> NewsService:
    repo = get_news_repository(db)
    return NewsService(repo=repo, vector_service=vector_service)


def get_schedule_handler(
    db: AsyncSession = Depends(get_db),
    cache: BaseCache = Depends(get_cache),
) -> GetScheduleHandler:
    from app.cqrs.queries import GetScheduleHandler

    return GetScheduleHandler(db=db, cache=cache)


def get_read_schedule_handler(
    db: AsyncSession = Depends(get_read_db),
    cache: BaseCache = Depends(get_cache),
) -> GetScheduleHandler:
    from app.cqrs.queries import GetScheduleHandler

    return GetScheduleHandler(db=db, cache=cache)


def get_user_analytics_service(
    db: AsyncSession = Depends(get_db),
) -> UserAnalyticsService:
    from app.services.user.analytics_service import UserAnalyticsService

    return UserAnalyticsService(db=db)


def get_stats_handler(
    db: AsyncSession = Depends(get_db),
    cache: BaseCache = Depends(get_cache),
    analytics_service: UserAnalyticsService = Depends(get_user_analytics_service),
) -> GetStatsHandler:
    from app.cqrs.queries import GetStatsHandler

    return GetStatsHandler(db=db, cache=cache, analytics_service=analytics_service)


def get_read_stats_handler(
    db: AsyncSession = Depends(get_read_db),
    cache: BaseCache = Depends(get_cache),
    analytics_service: UserAnalyticsService = Depends(get_user_analytics_service),
) -> GetStatsHandler:
    from app.cqrs.queries import GetStatsHandler

    return GetStatsHandler(db=db, cache=cache, analytics_service=analytics_service)


def get_auth_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> AuthService:
    auth_repo = get_auth_repository(db)
    user_repo = get_user_repository(db)
    return AuthService(audit=audit, auth_repo=auth_repo, user_repo=user_repo)
