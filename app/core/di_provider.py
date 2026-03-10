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

import logging
from collections.abc import AsyncIterator
from typing import Any, cast

import redis.asyncio as aioredis
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.fingerprint import SuspiciousActivityDetector
from app.auth.redis_session import SessionBackend
from app.core.nats_broker import NatsTaskBroker
from app.core.protocols import AsyncDatabaseSession, UserAnalyticsServiceProtocol
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
from app.deps.cache import BaseCache, create_cache_backend
from app.repositories.active_session_repository import ActiveSessionRepository
from app.repositories.auth_repository import AuthRepository
from app.repositories.chat_repository import ChatRepository
from app.repositories.event_repository import EventRepository, get_event_repository
from app.repositories.news_repository import NewsRepository, get_news_repository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.schedule_repository import GroupRepository, ScheduleRepository
from app.repositories.session_repository import get_session_repository
from app.repositories.story_repository import StoryRepository
from app.repositories.unit_of_work import UnitOfWork, get_unit_of_work
from app.repositories.user_repository import UserRepository
from app.services.audit_service import (
    AuditService,
    SecureAuditService,
    get_secure_audit_service,
)
from app.services.auth.credential_validator import CredentialValidator
from app.services.auth.lockout import LockoutService
from app.services.auth.login_service import LoginService
from app.services.auth.login_session_manager import LoginSessionManager
from app.services.auth.mfa_coordinator import MfaCoordinator
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
from app.services.story_service import StoryService
from app.services.session_service import SessionService
from app.services.user.compliance_service import UserComplianceService
from app.services.user.media_service import UserMediaService
from app.services.user.profile_service import UserProfileService
from app.services.user_service import UserService
from app.services.vector_service import VectorService
from app.workers.outbox import OutboxWorker

_logger = logging.getLogger(__name__)


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

    # ── Background workers (APP singletons) ───────────────────────────────────

    @provide(scope=Scope.APP)
    def outbox_worker(self) -> OutboxWorker:
        """Outbox pattern CDC worker — one instance per process.

        lifespan.py acquires this via the Dishka container and drives the
        asyncio task lifecycle. The container just owns the *object*;
        lifespan owns the *task* that calls run_forever().
        """
        return OutboxWorker()

    @provide(scope=Scope.APP)
    async def nats_broker(
        self,
    ) -> AsyncIterator[NatsTaskBroker]:
        """NATS JetStream broker — connects on container startup, closes on shutdown.

        Using an async generator so Dishka drives the connect/close lifecycle
        rather than lifespan.py doing it manually.  A 5-second timeout guards
        against hung connections during startup.
        """
        import asyncio

        broker = NatsTaskBroker()
        try:
            await asyncio.wait_for(broker.connect(), timeout=5.0)
            _logger.info("Dishka: NatsTaskBroker connected (Scope.APP)")
        except Exception as exc:
            _logger.warning(
                "Dishka: NATS connection failed (%s). Broker in degraded mode.", exc
            )
        try:
            yield broker
        finally:
            await broker.close()
            _logger.info("Dishka: NatsTaskBroker closed (Scope.APP shutdown)")

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
        """Creates an independent cache instance for the DI container.

        Enforces Dependency Inversion by managing the cache lifecycle within
        Dishka rather than delegating to a module-level global singleton.
        """
        return create_cache_backend()

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
    async def fraud_detection_service(self) -> AsyncIterator[FraudDetectionService]:
        """Redis Streams–backed cross-worker fraud event store.

        Durable and multi-worker — events survive pod restarts and are visible
        to all uvicorn workers. (MOD-4: audit 2026-02-24)

        PERF-3 (audit 2026-03-05): Converted to async generator so Dishka drives
        full pool lifecycle. The previous sync provider created the Redis client
        but never closed it on container teardown, leaking file descriptors.
        """
        from app.core.config import settings

        client = cast(Any, aioredis).from_url(
            str(settings.cache_redis_url),
            decode_responses=False,
            # PERF-04 (audit 2026-03-04): Cap the connection pool. Without this,
            # redis-py defaults to unlimited connections — under a login burst
            # every coroutine opens its own socket, exhausting Redis maxclients.
            max_connections=20,
        )
        try:
            yield FraudDetectionService(redis_client=client)
        finally:
            await client.close()

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
        uow: UnitOfWork,
        audit: AuditService,
        notifications: NotificationService,
    ) -> UserService:
        return UserService(
            uow=uow,
            audit=audit,
            notifications=notifications,
        )

    @provide(scope=Scope.REQUEST)
    def user_profile_service(
        self,
        uow: UnitOfWork,
        audit: AuditService,
        notifications: NotificationService,
    ) -> UserProfileService:
        return UserProfileService(
            uow=uow,
            audit=audit,
            notifications=notifications,
        )

    @provide(scope=Scope.REQUEST)
    def user_compliance_service(
        self,
        uow: UnitOfWork,
        audit: AuditService,
    ) -> UserComplianceService:
        return UserComplianceService(uow=uow, audit=audit)

    @provide(scope=Scope.REQUEST)
    def user_media_service(
        self, uow: UnitOfWork
    ) -> UserMediaService:
        return UserMediaService(uow=uow)

    @provide(scope=Scope.REQUEST)
    def event_service(
        self,
        uow: UnitOfWork,
        vector: VectorService,
    ) -> EventService:
        return EventService(
            uow=uow,
            vector_service=vector,
        )

    @provide(scope=Scope.REQUEST)
    def story_service(
        self,
        uow: UnitOfWork,
    ) -> StoryService:
        return StoryService(uow=uow)

    @provide(scope=Scope.REQUEST)
    def news_service(
        self,
        uow: UnitOfWork,
        vector: VectorService,
    ) -> NewsService:
        return NewsService(
            uow=uow,
            vector_service=vector,
        )

    @provide(scope=Scope.REQUEST)
    def unit_of_work(self, db: AsyncDatabaseSession) -> UnitOfWork:
        uow = get_unit_of_work(lambda: db)
        # Eagerly bind the live session so services can access uow.users,
        # uow.events, etc. in __init__ without entering the async context.
        uow._session = db
        uow.users = UserRepository(db)
        uow.auth = AuthRepository(db)
        uow.chats = ChatRepository(db)
        uow.events = EventRepository(db)
        uow.notifications = NotificationRepository(db)
        uow.news = NewsRepository(db)
        uow.stories = StoryRepository(db)
        uow.sessions = ActiveSessionRepository(db)
        uow.schedules = ScheduleRepository(db)
        uow.groups = GroupRepository(db)
        return uow

    @provide(scope=Scope.REQUEST)
    def auth_service(
        self,
        audit: AuditService,
        uow: UnitOfWork,
    ) -> AuthService:
        return AuthService(
            audit=audit,
            auth_repo=uow.auth,
            user_repo=uow.users,
            session_repo=uow.sessions,
            uow=uow,
        )

    @provide(scope=Scope.REQUEST)
    def schedule_service(
        self,
        uow: UnitOfWork,
    ) -> ScheduleService:
        from app.services.schedule_optimizer import (
            ScheduleOptimizerService,
        )

        return ScheduleService(
            uow=uow,
            optimizer=ScheduleOptimizerService(uow=uow),
        )

    @provide(scope=Scope.REQUEST)
    def user_analytics_service(
        self, db: AsyncDatabaseSession
    ) -> UserAnalyticsServiceProtocol:
        # TD-04 (audit 2026-03-04): Ideally this returns `UserAnalyticsService`
        # for mypy/IDE visibility, but Dishka's @provide parser calls
        # get_type_hints() at container-creation time. The class is imported
        # lazily (inside this function) to avoid eager module load of the heavy
        # analytics module — so the name is never in module globals when Dishka
        # introspects. The `object` annotation is the Dishka-required compromise.
        # RESOLUTION PATH (Q3 2026): extract UserAnalyticsServiceProtocol to
        # app/core/protocols.py (already imported at module level) and use it
        # as the return type — Dishka resolves Protocol types correctly.
        from app.services.user.analytics_service import UserAnalyticsService

        return UserAnalyticsService(db=db)

    # ── CQRS Handlers and Buses ───────────────────────────────────────────────

    @provide(scope=Scope.REQUEST)
    def get_schedule_handler(
        self, db: AsyncDatabaseSession, cache: BaseCache
    ) -> GetScheduleHandler:
        return GetScheduleHandler(db=db, cache=cache)

    @provide(scope=Scope.REQUEST)
    def get_stats_handler(
        self,
        db: AsyncDatabaseSession,
        cache: BaseCache,
        analytics_service: UserAnalyticsServiceProtocol,
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
        self, uow: UnitOfWork
    ) -> ChatQueryService:
        return ChatQueryService(session=uow.session, repository=uow.chats)

    @provide(scope=Scope.REQUEST)
    def chat_command_service(
        self,
        uow: UnitOfWork,
        attachments: ChatAttachmentService,
        notifications: ChatWSNotificationService,
    ) -> ChatCommandService:
        return ChatCommandService(
            uow=uow,
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
        self, uow: UnitOfWork
    ) -> SessionService:
        return SessionService(uow=uow)

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

    # ── Login sub-providers (TD-2, audit 2026-03-05) ─────────────────────────
    # Decomposed from the original 9-param god-factory into three cohesive
    # sub-providers, each ≤ 5 parameters (Rule of Three). The assembly is
    # transparent — Dishka wires the sub-objects automatically.

    @provide(scope=Scope.REQUEST)
    def login_session_manager(
        self,
        session_service: SessionService,
        redis_session: RedisSessionService,
        geolocation_service: GeolocationService,
        audit: AuditService,
    ) -> LoginSessionManager:
        from app.services.auth.login_session_manager import (
            LoginSessionManager as _LSM,
        )

        return _LSM(
            session_service=session_service,
            redis_session_service=redis_session,
            geolocation_service=geolocation_service,
            audit=audit,
        )

    @provide(scope=Scope.REQUEST)
    def credential_validator(
        self,
        user_repo: UserRepository,
        profile_service: UserProfileService,
        lockout_service: LockoutService,
        audit: AuditService,
        session_manager: LoginSessionManager,
    ) -> CredentialValidator:
        from app.services.auth.credential_validator import (
            CredentialValidator as _CV,
        )

        return _CV(
            user_repo=user_repo,
            profile_service=profile_service,
            lockout_service=lockout_service,
            audit=audit,
            session_manager=session_manager,
        )

    @provide(scope=Scope.REQUEST)
    def mfa_coordinator(
        self,
        auth_repo: AuthRepository,
    ) -> MfaCoordinator:
        from app.services.auth.mfa_coordinator import MfaCoordinator as _MC

        return _MC(auth_repo=auth_repo)

    @provide(scope=Scope.REQUEST)
    def login_service(
        self,
        db: AsyncDatabaseSession,
        validator: CredentialValidator,
        mfa_coord: MfaCoordinator,
        session_manager: LoginSessionManager,
    ) -> LoginService:
        return LoginService(
            validator=validator,
            mfa_coord=mfa_coord,
            session_manager=session_manager,
            db_session=db,
        )


def create_dishka_container() -> AsyncContainer:
    """Create and return the application-level dishka async container."""
    return make_async_container(AppProvider())
