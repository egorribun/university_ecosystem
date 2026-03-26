from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncSession,  # runtime: FastAPI get_type_hints() resolves annotations
)

from app.core.database import get_db, get_read_db
from app.deps.cache import BaseCache, get_cache
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
from app.services.user.compliance_service import UserComplianceService
from app.services.user.media_service import UserMediaService
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
    from app.repositories.unit_of_work import uow_from_session

    uow = uow_from_session(db)
    return UserService(
        uow=uow,
        audit=audit,
        notifications=notifications,
    )


def get_user_profile_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
    notifications: NotificationService = Depends(get_notification_service),
) -> UserProfileService:
    from app.repositories.unit_of_work import uow_from_session

    uow = uow_from_session(db)
    return UserProfileService(uow=uow, audit=audit, notifications=notifications)


def get_user_compliance_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> UserComplianceService:
    from app.repositories.unit_of_work import uow_from_session

    uow = uow_from_session(db)
    return UserComplianceService(uow=uow, audit=audit)


def get_user_media_service(
    db: AsyncSession = Depends(get_db),
) -> UserMediaService:
    from app.repositories.unit_of_work import uow_from_session

    uow = uow_from_session(db)
    return UserMediaService(uow=uow)


def get_event_service(
    db: AsyncSession = Depends(get_db),
    vector_service: VectorService = Depends(get_vector_service),
) -> EventService:
    from app.repositories.unit_of_work import uow_from_session

    uow = uow_from_session(db)
    return EventService(uow=uow, vector_service=vector_service)


def get_news_service(
    db: AsyncSession = Depends(get_db),
    vector_service: VectorService = Depends(get_vector_service),
) -> NewsService:
    from app.repositories.unit_of_work import uow_from_session

    uow = uow_from_session(db)
    return NewsService(uow=uow, vector_service=vector_service)


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
    from app.repositories.unit_of_work import uow_from_session

    uow = uow_from_session(db)
    return AuthService(
        audit=audit,
        auth_repo=uow.auth,
        user_repo=uow.users,
        session_repo=uow.sessions,
        uow=uow,
    )
