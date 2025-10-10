from __future__ import annotations

import asyncio
import logging
from threading import Lock
from typing import Optional

from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.models.models import PushSubscription

_async_ready = False
_async_lock = asyncio.Lock()
_sync_ready = False
_sync_lock = Lock()

logger = logging.getLogger(__name__)


def _create_schema(bind) -> None:
    PushSubscription.__table__.create(bind=bind, checkfirst=True)


async def ensure_push_subscription_schema(db: AsyncSession) -> None:
    global _async_ready, _sync_ready
    if _async_ready:
        return
    async with _async_lock:
        if _async_ready:
            return

        try:
            def _sync_create(sync_session) -> None:
                connection = sync_session.connection()
                _create_schema(connection)

            await db.run_sync(_sync_create)
        except SQLAlchemyError:
            logger.exception("Failed to ensure push subscription schema using async session")
            return
        else:
            _async_ready = True
            _sync_ready = True


def ensure_push_subscription_schema_sync(engine: Optional[Engine]) -> None:
    global _sync_ready, _async_ready
    if engine is None or _sync_ready:
        return
    with _sync_lock:
        if _sync_ready:
            return
        try:
            _create_schema(engine)
        except SQLAlchemyError:
            logger.exception("Failed to ensure push subscription schema using sync engine")
            return
        else:
            _sync_ready = True
            _async_ready = True
