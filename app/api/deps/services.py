from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends

from app.core.container import get_audit_service, get_vector_service
from app.core.database import get_db, get_read_db
from app.core.protocols import AsyncDatabaseSession

if TYPE_CHECKING:
    from app.services.analytics import AnalyticsService
    from app.services.auth.login_service import LoginService
    from app.services.auth.redis_session import RedisSessionService
    from app.services.auth_service import AuthService
    from app.services.chat_service import ChatService
    from app.services.event_service import EventService
    from app.services.geolocation import GeolocationService
    from app.services.news_service import NewsService
    from app.services.schedule_service import ScheduleService
    from app.services.session_service import SessionService
    from app.services.story_service import StoryService


def _build_chat_service(session: AsyncDatabaseSession) -> "ChatService":
    from app.repositories.chat_repository import ChatRepository
    from app.services.chat.attachment_service import ChatAttachmentService
    from app.services.chat.command_service import ChatCommandService
    from app.services.chat.notification_service import ChatNotificationService
    from app.services.chat.query_service import ChatQueryService
    from app.services.chat_service import ChatService

    repo = ChatRepository(session)
    attachments = ChatAttachmentService()
    notifications = ChatNotificationService(session)
    queries = ChatQueryService(session, repo)
    commands = ChatCommandService(session, repo, attachments, notifications)

    return ChatService(session, attachments, notifications, queries, commands)


def get_chat_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_db)]
) -> "ChatService":
    return _build_chat_service(session)


def get_read_chat_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_read_db)],
) -> "ChatService":
    return _build_chat_service(session)


def _build_event_service(
    session: AsyncDatabaseSession, vector_service: Any
) -> "EventService":
    from app.repositories.event_repository import EventRepository
    from app.services.event_service import EventService

    repo = EventRepository(session)
    return EventService(repo, vector_service)


def get_event_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_db)],
    vector_service: Annotated[Any, Depends(get_vector_service)],
) -> "EventService":
    return _build_event_service(session, vector_service)


def get_read_event_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_read_db)],
    vector_service: Annotated[Any, Depends(get_vector_service)],
) -> "EventService":
    return _build_event_service(session, vector_service)


def _build_news_service(
    session: AsyncDatabaseSession, vector_service: Any
) -> "NewsService":
    from app.repositories.news_repository import NewsRepository
    from app.services.news_service import NewsService

    repo = NewsRepository(session)
    return NewsService(repo, vector_service)


def get_news_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_db)],
    vector_service: Annotated[Any, Depends(get_vector_service)],
) -> "NewsService":
    return _build_news_service(session, vector_service)


def get_read_news_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_read_db)],
    vector_service: Annotated[Any, Depends(get_vector_service)],
) -> "NewsService":
    return _build_news_service(session, vector_service)


def _build_story_service(session: AsyncDatabaseSession) -> "StoryService":
    from app.repositories.story_repository import StoryRepository
    from app.services.story_service import StoryService

    repo = StoryRepository(session)
    return StoryService(repo)


def get_story_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_db)]
) -> "StoryService":
    return _build_story_service(session)


def get_read_story_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_read_db)],
) -> "StoryService":
    return _build_story_service(session)


def _build_schedule_service(session: AsyncDatabaseSession) -> "ScheduleService":
    from app.repositories.schedule_repository import GroupRepository, ScheduleRepository
    from app.services.schedule_optimizer import ScheduleOptimizerService
    from app.services.schedule_service import ScheduleService

    repo = ScheduleRepository(session)
    group_repo = GroupRepository(session)
    optimizer = ScheduleOptimizerService()
    return ScheduleService(repo, group_repo, optimizer)


def get_schedule_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_db)],
) -> "ScheduleService":
    return _build_schedule_service(session)


def get_read_schedule_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_read_db)],
) -> "ScheduleService":
    return _build_schedule_service(session)


def get_auth_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_db)],
) -> "AuthService":
    from app.repositories.auth_repository import AuthRepository
    from app.repositories.session_repository import SessionRepository
    from app.repositories.user_repository import UserRepository
    from app.services.audit_service import audit_service
    from app.services.auth_service import AuthService

    auth_repo = AuthRepository(session)
    user_repo = UserRepository(session)
    session_repo = SessionRepository(session)
    return AuthService(audit_service, auth_repo, user_repo, session_repo)


def get_session_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_db)],
) -> "SessionService":
    from app.repositories.active_session_repository import ActiveSessionRepository
    from app.services.session_service import SessionService

    repo = ActiveSessionRepository(session)
    return SessionService(session, repo)


async def get_geolocation_service() -> "GeolocationService":
    from app.services.geolocation import (
        GeolocationService,
        get_geolocation_service_instance,
    )

    return await get_geolocation_service_instance()


async def get_redis_session_service() -> "RedisSessionService":
    from app.services.auth.redis_session import RedisSessionService

    return RedisSessionService()


async def get_login_service(
    db: Annotated[AsyncDatabaseSession, Depends(get_db)],
    session_service: Annotated["SessionService", Depends(get_session_service)],
    audit: Annotated[Any, Depends(get_audit_service)],
    redis_session_service: Annotated[
        "RedisSessionService", Depends(get_redis_session_service)
    ],
    geolocation_service: Annotated["GeolocationService", Depends(get_geolocation_service)],
) -> "LoginService":
    from app.repositories.auth_repository import AuthRepository
    from app.repositories.user_repository import UserRepository
    from app.services.auth.credential_validator import CredentialValidator
    from app.services.auth.lockout import LockoutService
    from app.services.auth.login_service import LoginService
    from app.services.auth.login_session_manager import LoginSessionManager
    from app.services.auth.mfa_coordinator import MfaCoordinator
    from app.services.notification_service import NotificationService
    from app.services.user.profile_service import UserProfileService

    auth_repo = AuthRepository(db)
    user_repo = UserRepository(db)
    notifications = NotificationService(db)
    profile_service = UserProfileService(user_repo, audit, notifications)
    lockout_service = LockoutService(db)

    session_manager = LoginSessionManager(
        session_service=session_service,
        redis_session_service=redis_session_service,
        geolocation_service=geolocation_service,
        audit=audit,
    )
    validator = CredentialValidator(
        user_repo=user_repo,
        profile_service=profile_service,
        lockout_service=lockout_service,
        audit=audit,
        session_manager=session_manager,
    )
    mfa_coord = MfaCoordinator(auth_repo=auth_repo)

    return LoginService(
        validator=validator,
        mfa_coord=mfa_coord,
        session_manager=session_manager,
        db_session=db,
    )


def get_analytics_service() -> "AnalyticsService":
    from app.services.analytics import get_analytics_service

    return get_analytics_service()


__all__ = [
    "get_analytics_service",
    "get_audit_service",
    "get_auth_service",
    "get_chat_service",
    "get_event_service",
    "get_geolocation_service",
    "get_login_service",
    "get_news_service",
    "get_read_chat_service",
    "get_read_event_service",
    "get_read_news_service",
    "get_read_schedule_service",
    "get_read_story_service",
    "get_redis_session_service",
    "get_schedule_service",
    "get_session_service",
    "get_story_service",
]
