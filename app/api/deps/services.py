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
    from app.services.chat.command_service import ChatMaintenanceService, ChatMessageDispatcher
    from app.services.chat.creation_service import ChatCreationService
    from app.services.chat.query_service import ChatQueryService
    from app.services.event_service import EventService
    from app.services.geolocation import GeolocationService
    from app.services.news_service import NewsService
    from app.services.schedule_service import ScheduleService
    from app.services.session_service import SessionService
    from app.services.story_service import StoryService


# TD-W9-01/05: ChatService wrapper removed — inject narrow services directly.


def get_chat_message_dispatcher(
    session: Annotated[AsyncDatabaseSession, Depends(get_db)],
) -> "ChatMessageDispatcher":
    """FastAPI dep: ChatMessageDispatcher on write DB."""
    from app.repositories.unit_of_work import uow_from_session
    from app.services.chat.attachment_service import ChatAttachmentService
    from app.services.chat.command_service import ChatMessageDispatcher
    from app.services.chat.notification_service import ChatNotificationService

    uow = uow_from_session(session)
    attachments = ChatAttachmentService()
    notifications = ChatNotificationService(session)
    return ChatMessageDispatcher(uow, attachments, notifications)


def get_chat_maintenance_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_db)],
) -> "ChatMaintenanceService":
    """FastAPI dep: ChatMaintenanceService on write DB."""
    from app.repositories.unit_of_work import uow_from_session
    from app.services.chat.attachment_service import ChatAttachmentService
    from app.services.chat.command_service import ChatMaintenanceService

    uow = uow_from_session(session)
    attachments = ChatAttachmentService()
    return ChatMaintenanceService(uow, attachments)


def get_chat_creation_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_db)],
) -> "ChatCreationService":
    """FastAPI dep: ChatCreationService (DM creation with Redis lock)."""
    from app.deps.cache import get_cache
    from app.repositories.unit_of_work import uow_from_session
    from app.services.chat.creation_service import ChatCreationService

    uow = uow_from_session(session)
    return ChatCreationService(uow=uow, session=session, cache=get_cache())


def get_chat_query_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_db)],
) -> "ChatQueryService":
    """FastAPI dep: ChatQueryService (read-only) on write DB."""
    from app.repositories.unit_of_work import uow_from_session
    from app.services.chat.query_service import ChatQueryService

    uow = uow_from_session(session)
    return ChatQueryService(session=session, repository=uow.chats)


def get_read_chat_query_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_read_db)],
) -> "ChatQueryService":
    """FastAPI dep: ChatQueryService (read-only) on read replica."""
    from app.repositories.unit_of_work import uow_from_session
    from app.services.chat.query_service import ChatQueryService

    uow = uow_from_session(session)
    return ChatQueryService(session=session, repository=uow.chats)


# Legacy aliases — kept temporarily so any other callers outside chat.py
# do not break immediately.  Remove after audit confirms no other usages.
def get_chat_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_db)],
) -> "ChatMessageDispatcher":
    return get_chat_message_dispatcher(session)


def get_read_chat_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_read_db)],
) -> "ChatQueryService":
    return get_read_chat_query_service(session)


def _build_event_service(
    session: AsyncDatabaseSession, vector_service: Any
) -> "EventService":
    from app.repositories.unit_of_work import uow_from_session
    from app.services.event_service import EventService

    uow = uow_from_session(session)
    return EventService(uow, vector_service)


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
    from app.repositories.unit_of_work import uow_from_session
    from app.services.news_service import NewsService

    uow = uow_from_session(session)
    return NewsService(uow, vector_service)


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
    from app.repositories.unit_of_work import uow_from_session
    from app.services.story_service import StoryService

    uow = uow_from_session(session)
    return StoryService(uow)


def get_story_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_db)],
) -> "StoryService":
    return _build_story_service(session)


def get_read_story_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_read_db)],
) -> "StoryService":
    return _build_story_service(session)


def _build_schedule_service(session: AsyncDatabaseSession) -> "ScheduleService":
    from app.repositories.unit_of_work import uow_from_session
    from app.services.schedule_optimizer import ScheduleOptimizerService
    from app.services.schedule_service import ScheduleService

    uow = uow_from_session(session)
    optimizer = ScheduleOptimizerService()
    return ScheduleService(uow, optimizer)


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
    from app.repositories.unit_of_work import uow_from_session
    from app.services.audit_service import audit_service
    from app.services.auth_service import AuthService

    uow = uow_from_session(session)
    return AuthService(
        audit=audit_service,
        auth_repo=uow.auth,
        user_repo=uow.users,
        session_repo=uow.sessions,
        uow=uow,
    )


def get_session_service(
    session: Annotated[AsyncDatabaseSession, Depends(get_db)],
) -> "SessionService":
    from app.repositories.unit_of_work import uow_from_session
    from app.services.session_service import SessionService

    uow = uow_from_session(session)
    return SessionService(uow)


async def get_geolocation_service() -> "GeolocationService":
    from app.services.geolocation import (
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
    geolocation_service: Annotated[
        "GeolocationService", Depends(get_geolocation_service)
    ],
) -> "LoginService":
    from app.repositories.unit_of_work import uow_from_session
    from app.services.auth.credential_validator import CredentialValidator
    from app.services.auth.lockout import LockoutService
    from app.services.auth.login_service import LoginService
    from app.services.auth.login_session_manager import LoginSessionManager
    from app.services.auth.mfa_coordinator import MfaCoordinator
    from app.services.notification_service import NotificationService
    from app.services.user.profile_service import UserProfileService

    uow = uow_from_session(db)
    auth_repo = uow.auth
    user_repo = uow.users
    notifications = NotificationService(db)
    profile_service = UserProfileService(uow, audit, notifications)
    lockout_service = LockoutService(db)

    session_manager = LoginSessionManager(
        session_service=session_service,
        redis_session_service=redis_session_service,
        geolocation_service=geolocation_service,
        audit=audit,
    )
    validator = CredentialValidator(
        uow=uow,
        user_repo=user_repo,
        profile_service=profile_service,
        lockout_service=lockout_service,
        audit=audit,
        session_manager=session_manager,
    )
    mfa_coord = MfaCoordinator(uow=uow, auth_repo=auth_repo)

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
    "get_chat_maintenance_service",
    "get_chat_message_dispatcher",
    "get_chat_creation_service",
    "get_chat_query_service",
    "get_chat_service",  # legacy alias
    "get_event_service",
    "get_geolocation_service",
    "get_login_service",
    "get_news_service",
    "get_read_chat_query_service",
    "get_read_chat_service",  # legacy alias
    "get_read_event_service",
    "get_read_news_service",
    "get_read_schedule_service",
    "get_read_story_service",
    "get_redis_session_service",
    "get_schedule_service",
    "get_session_service",
    "get_story_service",
]
