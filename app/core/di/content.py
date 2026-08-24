from __future__ import annotations

from dishka import Provider, Scope, provide

from app.core.protocols import AsyncDatabaseSession, UserAnalyticsServiceProtocol
from app.repositories.schedule_repository import GroupRepository
from app.repositories.unit_of_work import UnitOfWork
from app.services.event_service import EventService
from app.services.group_service import GroupService
from app.services.news_service import NewsService
from app.services.notification_service import NotificationService
from app.services.schedule_service import ScheduleService
from app.services.story_service import StoryService
from app.services.vector_service import VectorService


class ContentProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def notification_service(self, db: AsyncDatabaseSession) -> NotificationService:
        return NotificationService(db=db)

    @provide(scope=Scope.REQUEST)
    def vector_service(self, db: AsyncDatabaseSession) -> VectorService:
        return VectorService(db=db)

    @provide(scope=Scope.REQUEST)
    def group_service(self, db: AsyncDatabaseSession) -> GroupService:
        return GroupService(db=db, repo=GroupRepository(db))

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
    def schedule_service(
        self,
        uow: UnitOfWork,
    ) -> ScheduleService:
        from app.services.schedule_optimizer import (
            ScheduleOptimizerService,
        )

        return ScheduleService(
            uow=uow,
            optimizer=ScheduleOptimizerService(),
        )

    @provide(scope=Scope.REQUEST)
    def user_analytics_service(
        self, db: AsyncDatabaseSession
    ) -> UserAnalyticsServiceProtocol:
        from app.services.user.analytics_service import UserAnalyticsService

        return UserAnalyticsService(db=db)
