from __future__ import annotations

import asyncio
from threading import Lock
from typing import Optional

from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import PushSubscription

_async_ready = False
_async_lock = asyncio.Lock()
_sync_ready = False
_sync_lock = Lock()


def _create_schema(bind) -> None:
    PushSubscription.__table__.create(bind=bind, checkfirst=True)


async def ensure_push_subscription_schema(db: AsyncSession) -> None:
    global _async_ready, _sync_ready
    if _async_ready:
        return
    async with _async_lock:
        if _async_ready:
            return

        def _sync_create(sync_session) -> None:
            connection = sync_session.connection()
            _create_schema(connection)

        await db.run_sync(_sync_create)
        _async_ready = True
        _sync_ready = True


def ensure_push_subscription_schema_sync(engine: Optional[Engine]) -> None:
    global _sync_ready, _async_ready
    if engine is None or _sync_ready:
        return
    with _sync_lock:
        if _sync_ready:
            return
        _create_schema(engine)
        _sync_ready = True
        _async_ready = True
