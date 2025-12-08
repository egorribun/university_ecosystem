from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
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


def _build_engine_kwargs(current_settings: Settings) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "pool_pre_ping": True,
        "echo": False,
    }
    if current_settings.is_development and current_settings.database_url.startswith(
        "sqlite"
    ):
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


def create_session_factory(
    current_settings: Settings = settings,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine_kwargs = _build_engine_kwargs(current_settings)
    engine = create_async_engine(current_settings.database_url, **engine_kwargs)
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
