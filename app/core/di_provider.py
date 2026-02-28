"""
dishka AppProvider — additive DI alongside the existing Depends()-based container.

Existing routes using FastAPI Depends() continue to work unchanged (Strangler Fig).
New routes can adopt FromDishka[] for cleaner, scope-managed dependency injection.

Usage in a new route handler:
    from dishka.integrations.fastapi import FromDishka
    from typing import Annotated

    async def my_route(service: Annotated[UserService, FromDishka()]):
        ...
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.fingerprint import SuspiciousActivityDetector
from app.auth.redis_session import SessionBackend
from app.core.protocols import AsyncDatabaseSession
from app.cqrs.bus import CommandBus, QueryBus
from app.cqrs.commands.schedule import (
    CreateScheduleCommand,
    CreateScheduleHandler,
    DeleteScheduleCommand,
    DeleteScheduleHandler,
    UpdateScheduleCommand,
    UpdateScheduleHandler,
)
from app.cqrs.queries import (
    GetScheduleHandler,
    GetScheduleQuery,
    GetStatsHandler,
    GetStatsQuery,
)
from app.deps.cache import BaseCache, get_cache
from app.repositories.active_session_repository import ActiveSessionRepository
from app.repositories.auth_repository import AuthRepository
from app.repositories.chat_repository import ChatRepository
from app.repositories.event_repository import get_event_repository
from app.repositories.news_repository import get_news_repository
from app.repositories.session_repository import get_session_repository
from app.repositories.user_repository import UserRepository
from app.services.audit_service import (
    AuditService,
    SecureAuditService,
    get_secure_audit_service,
)
from app.services.auth.lockout import LockoutService
from app.services.auth.login_service import LoginService
from app.services.auth.redis_session import RedisSessionService
from app.services.auth_service import AuthService
from app.services.chat.attachment_service import ChatAttachmentService
from app.services.chat.command_service import ChatCommandService
from app.services.chat.notification_service import (
    ChatNotificationService as ChatWSNotificationService,
)
from app.services.chat.query_service import ChatQueryService
from app.services.chat_service import ChatService
from app.services.event_service import EventService
from app.services.fraud_detection_service import FraudDetectionService
from app.services.geolocation import GeolocationService
from app.services.group_service import GroupService
from app.services.news_service import NewsService
from app.services.notification_service import NotificationService
from app.services.schedule_service import ScheduleService
from app.services.session_service import SessionService
from app.services.user.compliance_service import UserComplianceService
from app.services.user.media_service import UserMediaService
from app.services.user.profile_service import UserProfileService
from app.services.user_service import UserService
from app.services.vector_service import VectorService


class AppProvider(Provider):
    """
    Application-wide DI provider.

    Scope rules:
    - Scope.APP  — created once per process lifetime (stateless singletons).
    - Scope.REQUEST — created once per HTTP request, torn down after response.
    """

    # ── Session factory (APP) ─────────────────────────────────────────────────

    @provide(scope=Scope.APP)
    def _session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Reuses the module-level write engine; late import avoids circular deps."""
        from app.core.database import engine

        return async_sessionmaker(engine, expire_on_commit=False)

    @provide(scope=Scope.REQUEST)
    async def db(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncIterator[AsyncDatabaseSession]:
        """Open a write session for the request, close it when done."""
        async with session_factory() as session:
            yield session

    # ── Cache (APP singleton) ─────────────────────────────────────────────────

    @provide(scope=Scope.APP)
    def cache(self) -> BaseCache:
        """Wraps the existing module-level cache singleton."""
        return get_cache()

    # ── Stateless APP-scoped singletons ───────────────────────────────────────

    @provide(scope=Scope.APP)
    def audit_service(self) -> AuditService:
        return AuditService()

    @provide(scope=Scope.APP)
    def secure_audit_service(self) -> SecureAuditService:
        return get_secure_audit_service()

    @provide(scope=Scope.APP)
    def suspicious_activity_detector(self) -> SuspiciousActivityDetector:
        """Process-local ring buffer for suspicious session events.

        Replaces the module-level global singleton pattern in fingerprint.py.
        Tests can override this provider without any module-level monkey-patching.
        (TD-4: audit 2026-02-24)
        """
        return SuspiciousActivityDetector()

    @provide(scope=Scope.APP)
    def fraud_detection_service(self) -> FraudDetectionService:
        """Redis Streams–backed cross-worker fraud event store.

        Durable and multi-worker — events survive pod restarts and are visible
        to all uvicorn workers. (MOD-4: audit 2026-02-24)
        """
        # Use a local import to avoid adding redis-py to the top-level DI
        # module import graph — it would create a hard startup dependency even
        # when running in environments without Redis.
        import redis.asyncio as aioredis

        from app.core.config import settings

        client = aioredis.from_url(
            str(settings.cache_redis_url),
            decode_responses=False,
        )
        return FraudDetectionService(redis_client=client)

    # ── REQUEST-scoped services ───────────────────────────────────────────────

    @provide(scope=Scope.REQUEST)
    def notification_service(self, db: AsyncDatabaseSession) -> NotificationService:
        return NotificationService(db=db)

    @provide(scope=Scope.REQUEST)
    def vector_service(self, db: AsyncDatabaseSession) -> VectorService:
        return VectorService(db=db)

    @provide(scope=Scope.REQUEST)
    def group_service(self, db: AsyncDatabaseSession) -> GroupService:
        from app.repositories.schedule_repository import (
            GroupRepository,
        )

        return GroupService(db=db, repo=GroupRepository(db))

    @provide(scope=Scope.REQUEST)
    def user_service(
        self,
        db: AsyncDatabaseSession,
        audit: AuditService,
        notifications: NotificationService,
        user_repo: UserRepository,
    ) -> UserService:
        return UserService(
            user_repo=user_repo,
            audit=audit,
            notifications=notifications,
        )

    @provide(scope=Scope.REQUEST)
    def user_profile_service(
        self,
        db: AsyncDatabaseSession,
        audit: AuditService,
        notifications: NotificationService,
        user_repo: UserRepository,
    ) -> UserProfileService:
        return UserProfileService(
            user_repo=user_repo,
            audit=audit,
            notifications=notifications,
        )

    @provide(scope=Scope.REQUEST)
    def user_compliance_service(
        self,
        db: AsyncDatabaseSession,
        audit: AuditService,
        user_repo: UserRepository,
    ) -> UserComplianceService:
        return UserComplianceService(user_repo=user_repo, audit=audit)

    @provide(scope=Scope.REQUEST)
    def user_media_service(
        self, db: AsyncDatabaseSession, user_repo: UserRepository
    ) -> UserMediaService:
        return UserMediaService(user_repo=user_repo)

    @provide(scope=Scope.REQUEST)
    def event_service(
        self,
        db: AsyncDatabaseSession,
        vector: VectorService,
    ) -> EventService:
        return EventService(repo=get_event_repository(db), vector_service=vector)

    @provide(scope=Scope.REQUEST)
    def news_service(
        self,
        db: AsyncDatabaseSession,
        vector: VectorService,
    ) -> NewsService:
        return NewsService(repo=get_news_repository(db), vector_service=vector)

    @provide(scope=Scope.REQUEST)
    def auth_service(
        self,
        db: AsyncDatabaseSession,
        audit: AuditService,
        auth_repo: AuthRepository,
        user_repo: UserRepository,
    ) -> AuthService:
        return AuthService(
            audit=audit,
            auth_repo=auth_repo,
            user_repo=user_repo,
            session_repo=get_session_repository(db),
        )

    @provide(scope=Scope.REQUEST)
    def schedule_service(
        self,
        db: AsyncDatabaseSession,
    ) -> ScheduleService:
        from app.repositories.schedule_repository import (
            GroupRepository,
            ScheduleRepository,
        )
        from app.services.schedule_optimizer import (
            ScheduleOptimizerService,
        )

        return ScheduleService(
            repo=ScheduleRepository(db),
            group_repo=GroupRepository(db),
            optimizer=ScheduleOptimizerService(),
        )

    @provide(scope=Scope.REQUEST)
    def user_analytics_service(self, db: AsyncDatabaseSession) -> object:
        # Typed via string to avoid eager import of optional analytics module
        from app.services.user.analytics_service import (
            UserAnalyticsService,
        )

        return UserAnalyticsService(db=db)

    # ── CQRS Handlers and Buses ───────────────────────────────────────────────

    @provide(scope=Scope.REQUEST)
    def get_schedule_handler(
        self, db: AsyncDatabaseSession, cache: BaseCache
    ) -> GetScheduleHandler:
        return GetScheduleHandler(db=db, cache=cache)

    @provide(scope=Scope.REQUEST)
    def get_stats_handler(
        self, db: AsyncDatabaseSession, cache: BaseCache, analytics_service: object
    ) -> GetStatsHandler:
        # Cast logic is internal to the handler, but DI handles injection
        return GetStatsHandler(db=db, cache=cache, analytics_service=analytics_service)

    @provide(scope=Scope.REQUEST)
    def query_bus(self, container: AsyncContainer) -> QueryBus:
        bus = QueryBus(container)
        bus.register(GetScheduleQuery, GetScheduleHandler)
        bus.register(GetStatsQuery, GetStatsHandler)
        return bus

    @provide(scope=Scope.REQUEST)
    def command_bus(self, container: AsyncContainer) -> CommandBus:
        bus = CommandBus(container)
        bus.register(CreateScheduleCommand, CreateScheduleHandler)
        bus.register(UpdateScheduleCommand, UpdateScheduleHandler)
        bus.register(DeleteScheduleCommand, DeleteScheduleHandler)
        return bus

    @provide(scope=Scope.REQUEST)
    def create_schedule_handler(
        self, service: ScheduleService, cache: BaseCache
    ) -> CreateScheduleHandler:
        return CreateScheduleHandler(service=service, cache=cache)

    @provide(scope=Scope.REQUEST)
    def update_schedule_handler(
        self, service: ScheduleService, cache: BaseCache
    ) -> UpdateScheduleHandler:
        return UpdateScheduleHandler(service=service, cache=cache)

    @provide(scope=Scope.REQUEST)
    def delete_schedule_handler(
        self, service: ScheduleService, cache: BaseCache
    ) -> DeleteScheduleHandler:
        return DeleteScheduleHandler(service=service, cache=cache)

    @provide(scope=Scope.REQUEST)
    def chat_repository(self, db: AsyncDatabaseSession) -> ChatRepository:
        return ChatRepository(db)

    @provide(scope=Scope.REQUEST)
    def chat_attachment_service(self) -> ChatAttachmentService:
        return ChatAttachmentService()

    @provide(scope=Scope.REQUEST)
    def chat_ws_notification_service(
        self, db: AsyncDatabaseSession
    ) -> ChatWSNotificationService:
        return ChatWSNotificationService(session=db)

    @provide(scope=Scope.REQUEST)
    def chat_query_service(
        self, db: AsyncDatabaseSession, repo: ChatRepository
    ) -> ChatQueryService:
        return ChatQueryService(session=db, repository=repo)

    @provide(scope=Scope.REQUEST)
    def chat_command_service(
        self,
        db: AsyncDatabaseSession,
        repo: ChatRepository,
        attachments: ChatAttachmentService,
        notifications: ChatWSNotificationService,
    ) -> ChatCommandService:
        return ChatCommandService(
            session=db,
            repository=repo,
            attachment_service=attachments,
            notification_service=notifications,
        )

    @provide(scope=Scope.REQUEST)
    def chat_service(
        self,
        db: AsyncDatabaseSession,
        attachments: ChatAttachmentService,
        notifications: ChatWSNotificationService,
        queries: ChatQueryService,
        commands: ChatCommandService,
    ) -> ChatService:
        return ChatService(
            session=db,
            attachments=attachments,
            notifications=notifications,
            queries=queries,
            commands=commands,
        )

    # ── Core Auth & Session services (consolidated for Audit 4.1) ─────────────

    @provide(scope=Scope.REQUEST)
    def user_repository(self, db: AsyncDatabaseSession) -> UserRepository:
        return UserRepository(db)

    @provide(scope=Scope.REQUEST)
    def active_session_repository(
        self, db: AsyncDatabaseSession
    ) -> ActiveSessionRepository:
        return ActiveSessionRepository(db)

    @provide(scope=Scope.REQUEST)
    def auth_repository_explicit(self, db: AsyncDatabaseSession) -> AuthRepository:
        return AuthRepository(db)

    @provide(scope=Scope.REQUEST)
    def session_service(
        self, db: AsyncDatabaseSession, repo: ActiveSessionRepository
    ) -> SessionService:
        return SessionService(db=db, repo=repo)

    @provide(scope=Scope.REQUEST)
    def lockout_service(self, db: AsyncDatabaseSession) -> LockoutService:
        return LockoutService(db=db)

    @provide(scope=Scope.APP)
    async def session_backend(self) -> SessionBackend:
        from app.auth.redis_session import get_session_backend

        return await get_session_backend()

    @provide(scope=Scope.APP)
    def redis_session_service(self) -> RedisSessionService:
        """High-performance Redis session cache for LoginService.create_session.

        This is a separate concern from SessionBackend (which handles revocation
        pub/sub for the Gateway). LoginService needs the full RedisSessionService
        that stores session hash data used by get_current_user (cache-aside path).
        """
        return RedisSessionService()

    @provide(scope=Scope.REQUEST)
    async def geolocation_service(self) -> GeolocationService:
        from app.services.geolocation import get_geolocation_service_instance

        return await get_geolocation_service_instance()

    @provide(scope=Scope.REQUEST)
    def login_service(
        self,
        db: AsyncDatabaseSession,
        user_repo: UserRepository,
        profile_service: UserProfileService,
        session_service: SessionService,
        lockout_service: LockoutService,
        audit: AuditService,
        # Inject RedisSessionService (has create_session) not SessionBackend
        # (has register_session). Both live in different modules; the DI container
        # previously wired the wrong one, causing AttributeError at login. (TD-6)
        redis_session: RedisSessionService,
        geolocation_service: GeolocationService,
    ) -> LoginService:
        return LoginService(
            db=db,
            user_repo=user_repo,
            profile_service=profile_service,
            session_service=session_service,
            lockout_service=lockout_service,
            audit=audit,
            redis_session_service=redis_session,
            geolocation_service=geolocation_service,
        )


def create_dishka_container() -> AsyncContainer:
    """Create and return the application-level dishka async container."""
    return make_async_container(AppProvider())
