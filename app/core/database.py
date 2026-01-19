from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import AsyncGenerator
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

if TYPE_CHECKING:
    from app.core.config import Settings
from app.core.config import settings

logger = logging.getLogger(__name__)
slow_query_logger = logging.getLogger("slow_queries")
pool_health_logger = logging.getLogger("pool_health")

# Context variable to store query start time (async-safe)
_query_start_time: ContextVar[float | None] = ContextVar(
    "query_start_time", default=None
)


@dataclass
class PoolHealthMetrics:
    """Thread-safe connection pool health metrics."""

    total_checkouts: int = 0
    total_checkins: int = 0
    total_invalidations: int = 0
    active_connections: int = 0
    peak_active_connections: int = 0
    failed_checkouts: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_checkout(self) -> None:
        with self._lock:
            self.total_checkouts += 1
            self.active_connections += 1
            if self.active_connections > self.peak_active_connections:
                self.peak_active_connections = self.active_connections

    def record_checkin(self) -> None:
        with self._lock:
            self.total_checkins += 1
            self.active_connections = max(0, self.active_connections - 1)

    def record_invalidation(self) -> None:
        with self._lock:
            self.total_invalidations += 1
            self.active_connections = max(0, self.active_connections - 1)

    def record_failed_checkout(self) -> None:
        with self._lock:
            self.failed_checkouts += 1

    def get_snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "total_checkouts": self.total_checkouts,
                "total_checkins": self.total_checkins,
                "total_invalidations": self.total_invalidations,
                "active_connections": self.active_connections,
                "peak_active_connections": self.peak_active_connections,
                "failed_checkouts": self.failed_checkouts,
            }


# Global pool metrics instance
_pool_metrics = PoolHealthMetrics()


def get_pool_health_metrics() -> dict[str, int]:
    """Get current pool health metrics snapshot."""
    return _pool_metrics.get_snapshot()


def _build_engine_kwargs(current_settings: Settings) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "pool_pre_ping": True,
        "echo": False,
    }
    if current_settings.database_url.startswith("sqlite"):
        kwargs["poolclass"] = NullPool
    else:
        if current_settings.database_pool_size is not None:
            kwargs["pool_size"] = current_settings.database_pool_size
        if current_settings.database_max_overflow is not None:
            kwargs["max_overflow"] = current_settings.database_max_overflow
        if current_settings.database_pool_timeout is not None:
            kwargs["pool_timeout"] = current_settings.database_pool_timeout
        if current_settings.database_pool_recycle is not None:
            kwargs["pool_recycle"] = current_settings.database_pool_recycle
    return kwargs


def _before_cursor_execute(
    conn, cursor, statement, parameters, context, executemany
) -> None:
    """Store the start time before query execution."""
    _query_start_time.set(time.perf_counter())


def _after_cursor_execute(
    conn, cursor, statement, parameters, context, executemany
) -> None:
    """Log if query execution time exceeded threshold."""
    start_time = _query_start_time.get()
    if start_time is None:
        return

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    _query_start_time.set(None)

    threshold = getattr(settings, "slow_query_threshold_ms", 500.0)
    if elapsed_ms >= threshold:
        # Truncate statement for logging (avoid huge log entries)
        truncated_statement = (
            statement[:500] + "..." if len(statement) > 500 else statement
        )

        # Capture query plan for SELECT statements
        query_plan: str | None = None
        if getattr(
            settings, "slow_query_explain_enabled", False
        ) and statement.strip().upper().startswith("SELECT"):
            try:
                cursor.execute(f"EXPLAIN (FORMAT TEXT) {statement}", parameters)
                plan_rows = cursor.fetchall()
                query_plan = "\n".join(row[0] for row in plan_rows)
            except Exception:
                query_plan = "EXPLAIN failed"

        slow_query_logger.warning(
            "Slow query detected: %.2fms - %s",
            elapsed_ms,
            truncated_statement.replace("\n", " ").strip(),
            extra={
                "elapsed_ms": elapsed_ms,
                "statement_length": len(statement),
                "executemany": executemany,
                "threshold_ms": threshold,
                "query_plan": query_plan,
            },
        )


def _setup_slow_query_logging(engine: AsyncEngine, current_settings: Settings) -> None:
    """
    Set up slow query logging for the given engine.

    Now enabled in all environments when slow_query_logging_enabled is True.
    Uses configurable threshold from settings.
    """
    if not getattr(current_settings, "slow_query_logging_enabled", False):
        return

    sync_engine = engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", _before_cursor_execute)
    event.listen(sync_engine, "after_cursor_execute", _after_cursor_execute)
    threshold = getattr(current_settings, "slow_query_threshold_ms", 500.0)
    logger.info(
        "Slow query logging enabled (threshold: %.0fms)",
        threshold,
    )


def _on_checkout(
    dbapi_connection,
    connection_record,
    connection_proxy,
) -> None:
    """Handle connection checkout from pool."""
    _pool_metrics.record_checkout()
    pool_health_logger.debug(
        "Connection checkout: active=%d",
        _pool_metrics.active_connections,
    )


def _on_checkin(dbapi_connection, connection_record) -> None:
    """Handle connection checkin to pool."""
    _pool_metrics.record_checkin()
    pool_health_logger.debug(
        "Connection checkin: active=%d",
        _pool_metrics.active_connections,
    )


def _on_invalidate(dbapi_connection, connection_record, exception) -> None:
    """Handle connection invalidation."""
    _pool_metrics.record_invalidation()
    pool_health_logger.warning(
        "Connection invalidated: active=%d, exception=%s",
        _pool_metrics.active_connections,
        type(exception).__name__ if exception else "None",
    )


def _on_checkout_failed(exception, pool) -> None:
    """Handle failed checkout (pool exhausted)."""
    _pool_metrics.record_failed_checkout()
    pool_health_logger.error(
        "Pool checkout failed (exhausted): failed_total=%d, pool_size=%d",
        _pool_metrics.failed_checkouts,
        pool.size(),
    )


def _setup_pool_health_monitoring(engine: AsyncEngine) -> None:
    """Set up connection pool health monitoring."""
    sync_engine = engine.sync_engine
    pool = sync_engine.pool

    event.listen(pool, "checkout", _on_checkout)
    event.listen(pool, "checkin", _on_checkin)
    event.listen(pool, "invalidate", _on_invalidate)

    logger.info(
        "Pool health monitoring enabled (size=%s, overflow=%s)",
        getattr(pool, "size", lambda: "N/A")(),
        getattr(pool, "overflow", lambda: "N/A")(),
    )


def create_session_factory(
    current_settings: Settings = settings,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession], AsyncEngine | None]:
    engine_kwargs = _build_engine_kwargs(current_settings)
    engine = create_async_engine(current_settings.database_url, **engine_kwargs)

    # Enable slow query logging
    _setup_slow_query_logging(engine, current_settings)

    # Enable pool health monitoring
    _setup_pool_health_monitoring(engine)

    # Create read replica engine if configured
    read_replica_engine: AsyncEngine | None = None
    replica_url = getattr(current_settings, "database_read_replica_url", None)
    if replica_url:
        read_replica_engine = create_async_engine(replica_url, **engine_kwargs)
        _setup_pool_health_monitoring(read_replica_engine)
        logger.info("Read replica engine configured")

    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    return engine, session_factory, read_replica_engine


engine, async_session, read_replica_engine = create_session_factory()


def get_read_engine() -> AsyncEngine:
    """Get the engine for read operations (replica if available, otherwise primary)."""
    return read_replica_engine if read_replica_engine is not None else engine


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    while True:
        try:
            async with async_session() as session:
                yield session
            break
        except DBAPIError as exc:  # pragma: no cover - defensive guard
            if exc.connection_invalidated:
                logger.warning("Database connection invalidated; retrying session")
                continue
            raise


async def get_read_db() -> AsyncGenerator[AsyncSession, None]:
    """Get a read-only session (uses replica if configured, otherwise primary)."""
    read_engine = get_read_engine()
    read_session_factory = async_sessionmaker(
        read_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with read_session_factory() as session:
        yield session


async def wait_db(max_attempts: int = 5, delay: float = 1.0) -> None:
    """Ensure the database is reachable before continuing."""

    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return
        except Exception as exc:  # pragma: no cover - defensive logging
            last_exc = exc
            log_func = logger.error if attempt == max_attempts else logger.warning
            log_func(
                "Database unavailable on attempt %s/%s: %s",
                attempt,
                max_attempts,
                exc,
                exc_info=attempt == max_attempts,
            )
            if attempt < max_attempts:
                await asyncio.sleep(delay)
    if last_exc is not None:
        raise RuntimeError(
            f"Database connection failed after {max_attempts} attempts: {last_exc}"
        ) from last_exc
