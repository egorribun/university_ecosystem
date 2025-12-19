from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from contextvars import ContextVar

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

from app.core.config import Settings, settings

logger = logging.getLogger(__name__)
slow_query_logger = logging.getLogger("slow_queries")

# Configuration for slow query logging
SLOW_QUERY_THRESHOLD_MS: float = 100.0  # Log queries taking longer than 100ms

# Context variable to store query start time (async-safe)
_query_start_time: ContextVar[float | None] = ContextVar("query_start_time", default=None)


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


def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany) -> None:
    """Store the start time before query execution."""
    _query_start_time.set(time.perf_counter())


def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany) -> None:
    """Log if query execution time exceeded threshold."""
    start_time = _query_start_time.get()
    if start_time is None:
        return

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    _query_start_time.set(None)

    if elapsed_ms >= SLOW_QUERY_THRESHOLD_MS:
        # Truncate statement for logging (avoid huge log entries)
        truncated_statement = statement[:500] + "..." if len(statement) > 500 else statement
        slow_query_logger.warning(
            "Slow query detected: %.2fms - %s",
            elapsed_ms,
            truncated_statement.replace("\n", " ").strip(),
            extra={
                "elapsed_ms": elapsed_ms,
                "statement_length": len(statement),
                "executemany": executemany,
            },
        )


def _setup_slow_query_logging(engine: AsyncEngine, current_settings: Settings) -> None:
    """
    Set up slow query logging for the given engine.

    Only active in development mode.
    """
    if not current_settings.is_development:
        return

    sync_engine = engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", _before_cursor_execute)
    event.listen(sync_engine, "after_cursor_execute", _after_cursor_execute)
    logger.info(
        "Slow query logging enabled (threshold: %.0fms)",
        SLOW_QUERY_THRESHOLD_MS,
    )


def create_session_factory(
    current_settings: Settings = settings,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine_kwargs = _build_engine_kwargs(current_settings)
    engine = create_async_engine(current_settings.database_url, **engine_kwargs)

    # Enable slow query logging in development mode
    _setup_slow_query_logging(engine, current_settings)

    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    return engine, session_factory


engine, async_session = create_session_factory()


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
