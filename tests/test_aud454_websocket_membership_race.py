"""The local fanout must not authorize from a stale participants cache."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from app.api.ws import connection_manager, presence
from app.core import nats_broker
from app.deps.cache import MemoryCache, versioned_key


@pytest.mark.asyncio
async def test_inflight_old_roster_cannot_poison_next_broadcast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id, owner_id, removed_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    current = [owner_id, removed_id]
    db_read_started, resume_db_read = asyncio.Event(), asyncio.Event()
    cache = MemoryCache(default_ttl=120)
    reads = 0

    class Repository:
        def __init__(self, _session: object) -> None:
            pass

        async def get_participants(self, _chat_id: uuid.UUID) -> list[uuid.UUID]:
            nonlocal reads
            reads += 1
            snapshot = list(current)
            if reads == 1:
                db_read_started.set()
                await resume_db_read.wait()
            return snapshot

    @asynccontextmanager
    async def open_session() -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(presence, "get_cache", lambda: cache)
    monkeypatch.setattr(connection_manager, "ChatRepository", Repository)
    monkeypatch.setattr(nats_broker.broker, "publish_core", AsyncMock())
    manager = connection_manager.ConnectionManager(session_factory=open_session)
    manager.send_to_user = AsyncMock(return_value=1)

    first = asyncio.create_task(manager.broadcast_to_chat(chat_id, {"type": "first"}))
    try:
        await asyncio.wait_for(db_read_started.wait(), timeout=2)
        current.remove(removed_id)  # committed removal
        await presence.invalidate_chat_participants_cache(chat_id)
    finally:
        resume_db_read.set()
        await asyncio.wait_for(first, timeout=2)

    manager.send_to_user.reset_mock()
    await manager.broadcast_to_chat(chat_id, {"type": "after-removal"})
    targets = {call.args[0] for call in manager.send_to_user.await_args_list}
    assert targets == {owner_id}
    assert reads == 2


@pytest.mark.asyncio
async def test_existing_stale_cache_cannot_authorize_chat_fanout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id, owner_id, removed_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    cache = MemoryCache(default_ttl=120)
    await cache.set(
        versioned_key(f"chat:{chat_id}:participants"),
        [str(owner_id), str(removed_id)],
        ttl=3600,
    )

    class Repository:
        def __init__(self, _session: object) -> None:
            pass

        async def get_participants(self, _chat_id: uuid.UUID) -> list[uuid.UUID]:
            return [owner_id]

    @asynccontextmanager
    async def open_session() -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(connection_manager, "ChatRepository", Repository)
    monkeypatch.setattr(nats_broker.broker, "publish_core", AsyncMock())
    manager = connection_manager.ConnectionManager(session_factory=open_session)
    manager.send_to_user = AsyncMock(return_value=1)

    await manager.broadcast_to_chat(chat_id, {"type": "after-removal"})

    manager.send_to_user.assert_awaited_once_with(owner_id, {"type": "after-removal"})


@pytest.mark.asyncio
async def test_roster_storage_failure_stops_local_and_nats_fanout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id = uuid.uuid4()

    class Repository:
        def __init__(self, _session: object) -> None:
            pass

        async def get_participants(self, _chat_id: uuid.UUID) -> list[uuid.UUID]:
            raise OSError("roster storage unavailable")

    @asynccontextmanager
    async def open_session() -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(connection_manager, "ChatRepository", Repository)
    publish = AsyncMock()
    monkeypatch.setattr(nats_broker.broker, "publish_core", publish)
    manager = connection_manager.ConnectionManager(session_factory=open_session)
    manager.send_to_user = AsyncMock(return_value=1)

    with pytest.raises(OSError, match="roster storage unavailable"):
        await manager.broadcast_to_chat(chat_id, {"type": "message"})

    manager.send_to_user.assert_not_awaited()
    publish.assert_not_awaited()
