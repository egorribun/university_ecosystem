from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

from app.core.config import settings
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

_engine_kwargs: dict[str, object] = {
    "pool_pre_ping": True,
    "echo": False,
}

if settings.is_development:
    _engine_kwargs["poolclass"] = NullPool

engine = create_async_engine(settings.database_url, **_engine_kwargs)

async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


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
            logger.warning(
                "Database unavailable on attempt %s/%s", attempt, max_attempts
            )
            await asyncio.sleep(delay)
    if last_exc is not None:
        raise RuntimeError("Database connection failed") from last_exc
