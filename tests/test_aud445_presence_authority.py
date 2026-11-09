"""Presence authorization must use the current primary membership snapshot."""

from __future__ import annotations

import asyncio
import uuid
from collections import OrderedDict
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import websocket as websocket_api
from app.api.ws import connection_manager, presence
from app.api.ws.dispatcher import MessageDispatcher
from app.deps.cache import MemoryCache, versioned_key
from app.models.users import User
from app.repositories.chat_repository import ChatRepository


@pytest.mark.asyncio
async def test_removed_member_is_not_authorized_by_stale_shared_audience(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, removed = await user_factory(), await user_factory()
    repo = ChatRepository(db_session)
    chat = await repo.create_group(owner, "aud445-authority", [removed])
    await db_session.commit()
    cache = MemoryCache(default_ttl=3600)
    await cache.set(
        versioned_key(f"user:{owner.id}:presence_audience"), [str(removed.id)]
    )
    monkeypatch.setattr(presence, "get_cache", lambda: cache)

    @asynccontextmanager
    async def session_factory() -> AsyncIterator[AsyncSession]:
        yield db_session

    monkeypatch.setattr(presence, "async_session", session_factory)
    await repo.remove_participant(chat.id, removed.id)
    await db_session.commit()
    assert removed.id not in await repo.get_presence_audience(owner.id)

    audience = await presence._get_presence_audience(owner.id)
    assert str(removed.id) not in {str(user_id) for user_id in audience}


@pytest.mark.asyncio
async def test_database_failure_does_not_fall_back_to_a_cached_audience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id, removed_id = uuid.uuid4(), uuid.uuid4()
    cache = MemoryCache(default_ttl=3600)
    await cache.set(versioned_key(f"user:{owner_id}:presence_audience"), [removed_id])
    monkeypatch.setattr(presence, "get_cache", lambda: cache)
    failure = OSError("owned audience database outage")
    repository = SimpleNamespace(get_presence_audience=AsyncMock(side_effect=failure))

    @asynccontextmanager
    async def session_factory() -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(presence, "async_session", session_factory)
    monkeypatch.setattr(presence, "ChatRepository", lambda _session: repository)

    with pytest.raises(OSError, match="owned audience database outage"):
        await presence._get_presence_audience(owner_id)
    repository.get_presence_audience.assert_awaited_once_with(owner_id)


@pytest.mark.asyncio
async def test_old_inflight_lookup_cannot_poison_a_later_presence_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id, removed_id = uuid.uuid4(), uuid.uuid4()
    audience = {removed_id}
    snapshot_taken, release = asyncio.Event(), asyncio.Event()
    reads = 0
    cache = MemoryCache(default_ttl=3600)
    monkeypatch.setattr(presence, "get_cache", lambda: cache)
    monkeypatch.setattr(presence, "_PRESENCE_DB_CACHE", OrderedDict(), raising=False)

    class Repository:
        def __init__(self, _session: object) -> None:
            pass

        async def get_presence_audience(self, user_id: uuid.UUID) -> set[uuid.UUID]:
            nonlocal reads
            assert user_id == owner_id
            reads += 1
            snapshot = set(audience)
            if reads == 1:
                snapshot_taken.set()
                await release.wait()
            return snapshot

    @asynccontextmanager
    async def session_factory() -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(presence, "async_session", session_factory)
    monkeypatch.setattr(presence, "ChatRepository", Repository)
    old = asyncio.create_task(presence._get_presence_audience(owner_id))
    try:
        await asyncio.wait_for(snapshot_taken.wait(), timeout=3)
        audience.clear()  # Model membership removal committed after the first read.
    finally:
        release.set()
        assert await asyncio.wait_for(old, timeout=3) == {removed_id}

    assert await presence._get_presence_audience(owner_id) == set()
    assert reads == 2


@pytest.mark.asyncio
async def test_other_shared_chat_still_authorizes_presence(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, peer = await user_factory(), await user_factory()
    repo = ChatRepository(db_session)
    first = await repo.create_group(owner, "aud445-one", [peer])
    await repo.create_group(owner, "aud445-two", [peer])
    await db_session.commit()

    @asynccontextmanager
    async def session_factory() -> AsyncIterator[AsyncSession]:
        yield db_session

    monkeypatch.setattr(presence, "async_session", session_factory)
    monkeypatch.setattr(presence, "get_cache", lambda: MemoryCache())
    monkeypatch.setattr(presence, "_PRESENCE_DB_CACHE", OrderedDict(), raising=False)
    await repo.remove_participant(first.id, peer.id)
    await db_session.commit()

    assert await presence._get_presence_audience(owner.id) == {peer.id}


@pytest.mark.asyncio
async def test_broadcast_and_online_list_ignore_stale_cached_membership(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, member = await user_factory(), await user_factory()
    repo = ChatRepository(db_session)
    chat = await repo.create_group(owner, "aud445-consumers", [member])
    await db_session.commit()
    cache = MemoryCache(default_ttl=3600)
    await cache.set(
        versioned_key(f"user:{owner.id}:presence_audience"), [str(member.id)]
    )
    monkeypatch.setattr(presence, "get_cache", lambda: cache)

    @asynccontextmanager
    async def session_factory() -> AsyncIterator[AsyncSession]:
        yield db_session

    monkeypatch.setattr(presence, "async_session", session_factory)
    await repo.remove_participant(chat.id, member.id)
    await db_session.commit()
    manager = connection_manager.ConnectionManager()
    manager.send_to_user = AsyncMock(return_value=1)
    monkeypatch.setattr(manager, "is_online", lambda _user_id: True)
    monkeypatch.setattr(websocket_api, "manager", manager)

    assert await websocket_api._get_online_users_for_user(owner.id) == []
    assert await MessageDispatcher(manager)._get_online_users_for_user(owner.id) == []
    assert (
        await manager.broadcast_presence(
            owner.id,
            True,
            None,
            source=presence.PRESENCE_SOURCE_CONNECT,
            force=True,
            publish=False,
        )
        == 0
    )
    manager.send_to_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_database_outage_blocks_local_presence_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id = uuid.uuid4()
    repository = SimpleNamespace(
        get_presence_audience=AsyncMock(side_effect=OSError("database unavailable"))
    )

    @asynccontextmanager
    async def session_factory() -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(presence, "async_session", session_factory)
    monkeypatch.setattr(presence, "ChatRepository", lambda _session: repository)
    manager = connection_manager.ConnectionManager()
    manager.send_to_user = AsyncMock(return_value=1)

    with pytest.raises(OSError, match="database unavailable"):
        await manager.broadcast_presence(
            owner_id,
            True,
            None,
            source=presence.PRESENCE_SOURCE_CONNECT,
            force=True,
            publish=False,
        )
    manager.send_to_user.assert_not_awaited()
