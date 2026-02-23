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

from dishka import Provider, Scope, make_async_container, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.deps.cache import BaseCache, get_cache
from app.repositories.auth_repository import get_auth_repository
from app.repositories.event_repository import get_event_repository
from app.repositories.news_repository import get_news_repository
from app.repositories.session_repository import get_session_repository
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
    ) -> AsyncIterator[AsyncSession]:
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

    # ── REQUEST-scoped services ───────────────────────────────────────────────

    @provide(scope=Scope.REQUEST)
    def notification_service(self, db: AsyncSession) -> NotificationService:
        return NotificationService(db=db)

    @provide(scope=Scope.REQUEST)
    def vector_service(self, db: AsyncSession) -> VectorService:
        return VectorService(db=db)

    @provide(scope=Scope.REQUEST)
    def group_service(self, db: AsyncSession) -> GroupService:
        from app.repositories.schedule_repository import (
            GroupRepository,
        )

        return GroupService(db=db, repo=GroupRepository(db))

    @provide(scope=Scope.REQUEST)
    def user_service(
        self,
        db: AsyncSession,
        audit: AuditService,
        notifications: NotificationService,
    ) -> UserService:
        return UserService(
            user_repo=get_user_repository(db),
            audit=audit,
            notifications=notifications,
        )

    @provide(scope=Scope.REQUEST)
    def user_profile_service(
        self,
        db: AsyncSession,
        audit: AuditService,
        notifications: NotificationService,
    ) -> UserProfileService:
        return UserProfileService(
            user_repo=get_user_repository(db),
            audit=audit,
            notifications=notifications,
        )

    @provide(scope=Scope.REQUEST)
    def user_compliance_service(
        self,
        db: AsyncSession,
        audit: AuditService,
    ) -> UserComplianceService:
        return UserComplianceService(user_repo=get_user_repository(db), audit=audit)

    @provide(scope=Scope.REQUEST)
    def user_media_service(self, db: AsyncSession) -> UserMediaService:
        return UserMediaService(user_repo=get_user_repository(db))

    @provide(scope=Scope.REQUEST)
    def event_service(
        self,
        db: AsyncSession,
        vector: VectorService,
    ) -> EventService:
        return EventService(repo=get_event_repository(db), vector_service=vector)

    @provide(scope=Scope.REQUEST)
    def news_service(
        self,
        db: AsyncSession,
        vector: VectorService,
    ) -> NewsService:
        return NewsService(repo=get_news_repository(db), vector_service=vector)

    @provide(scope=Scope.REQUEST)
    def auth_service(
        self,
        db: AsyncSession,
        audit: AuditService,
    ) -> AuthService:
        return AuthService(
            audit=audit,
            auth_repo=get_auth_repository(db),
            user_repo=get_user_repository(db),
            session_repo=get_session_repository(db),
        )

    @provide(scope=Scope.REQUEST)
    def user_analytics_service(self, db: AsyncSession) -> object:
        # Typed via string to avoid eager import of optional analytics module
        from app.services.user.analytics_service import (
            UserAnalyticsService,
        )

        return UserAnalyticsService(db=db)


def create_dishka_container():  # type: ignore[return]
    """Create and return the application-level dishka async container."""
    return make_async_container(AppProvider())
