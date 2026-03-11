from __future__ import annotations

from dishka import AsyncContainer, Provider, Scope, provide

from app.core.protocols import AsyncDatabaseSession, UserAnalyticsServiceProtocol
from app.cqrs.bus import CommandBus, LoggingMiddleware, QueryBus
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
from app.deps.cache import BaseCache
from app.services.schedule_service import ScheduleService


class CQRSProvider(Provider):
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
        return GetStatsHandler(db=db, cache=cache, analytics_service=analytics_service)

    @provide(scope=Scope.REQUEST)
    def query_bus(self, container: AsyncContainer) -> QueryBus:
        bus = QueryBus(container, middleware=[LoggingMiddleware()])
        bus.register(GetScheduleQuery, GetScheduleHandler)
        bus.register(GetStatsQuery, GetStatsHandler)
        return bus

    @provide(scope=Scope.REQUEST)
    def command_bus(self, container: AsyncContainer) -> CommandBus:
        bus = CommandBus(container, middleware=[LoggingMiddleware()])
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
