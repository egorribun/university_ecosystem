from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

import redis.asyncio as aioredis
from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.fingerprint import SuspiciousActivityDetector
from app.auth.redis_session import SessionBackend
from app.core.logging import get_logger
from app.core.nats_broker import NatsTaskBroker
from app.core.protocols import AsyncDatabaseSession
from app.deps.cache import BaseCache, get_cache
from app.services.audit_service import (
    AuditService,
    SecureAuditService,
    get_secure_audit_service,
)
from app.services.auth.redis_session import RedisSessionService
from app.services.fraud_detection_service import FraudDetectionService
from app.services.geolocation import GeolocationService
from app.workers.outbox import OutboxWorker

_logger = get_logger(__name__)


class InfrastructureProvider(Provider):
    @provide(scope=Scope.APP)
    def _session_factory(self) -> async_sessionmaker[AsyncSession]:
        from app.core.database import engine

        return async_sessionmaker(engine, expire_on_commit=False)

    @provide(scope=Scope.APP)
    def outbox_worker(self) -> OutboxWorker:
        from app.core.config import settings

        return OutboxWorker(
            poll_interval=settings.outbox_poll_interval_seconds,
            batch_size=settings.outbox_batch_size,
        )

    @provide(scope=Scope.APP)
    async def nats_broker(self) -> AsyncIterator[NatsTaskBroker]:
        import asyncio

        from app.core.config import settings
        from app.core.nats_broker import broker as global_broker

        if settings.environment != "testing":
            try:
                await asyncio.wait_for(global_broker.connect(), timeout=5.0)
                _logger.info("Dishka: NatsTaskBroker connected (Scope.APP)")
            except (
                OSError,
                ConnectionError,
                TimeoutError,
            ) as exc:  # RZ-22-01: narrowed — NATS connection errors
                _logger.warning("Dishka: NATS connection failed (%s).", exc)
        yield global_broker
        await global_broker.close()

    @provide(scope=Scope.REQUEST)
    async def db(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncIterator[AsyncDatabaseSession]:
        async with session_factory() as session:
            yield session

    @provide(scope=Scope.APP)
    def cache(self) -> BaseCache:
        return get_cache()

    @provide(scope=Scope.APP)
    def audit_service(self) -> AuditService:
        return AuditService()

    @provide(scope=Scope.APP)
    def secure_audit_service(self) -> SecureAuditService:
        return get_secure_audit_service()

    @provide(scope=Scope.APP)
    def suspicious_activity_detector(self) -> SuspiciousActivityDetector:
        return SuspiciousActivityDetector()

    @provide(scope=Scope.APP)
    async def fraud_detection_service(self) -> AsyncIterator[FraudDetectionService]:
        from app.core.config import settings

        client = cast(Any, aioredis).from_url(
            str(settings.cache_redis_url),
            decode_responses=False,
            max_connections=20,
        )
        try:
            yield FraudDetectionService(redis_client=client)
        finally:
            await client.close()

    @provide(scope=Scope.APP)
    async def session_backend(self) -> SessionBackend:
        from app.auth.redis_session import get_session_backend

        return await get_session_backend()

    @provide(scope=Scope.APP)
    def redis_session_service(self) -> RedisSessionService:
        return RedisSessionService()

    @provide(scope=Scope.REQUEST)
    async def geolocation_service(self) -> GeolocationService:
        from app.services.geolocation import get_geolocation_service_instance

        return await get_geolocation_service_instance()
