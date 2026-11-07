"""AUD-262 durable replay contracts against the real PostgreSQL dispatcher.

These tests intentionally import only today's production objects. Redis is an
owned FakeRedis boundary; all message, outbox, commit and rollback operations
use real repositories and independent PostgreSQL sessions.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from types import SimpleNamespace

import fakeredis.aioredis
import pytest
import pytest_asyncio
from fakeredis._socket import _base
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import event as sa_event
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import app.deps.cache as cache_module
import app.services.chat.command_service as command_service
from app.core import database
from app.core.events import (
    MessageSent,
    _persist_captured_events,
    capture_domain_events,
    capture_on_commit,
)
from app.models import Chat, Message, User
from app.models.domain_events import StoredEvent
from app.repositories.chat_repository import ChatRepository
from app.repositories.unit_of_work import uow_from_session
from app.schemas.chat import MessageResponse
from app.services.chat.attachment_service import ChatAttachmentService
from app.services.chat.notification_service import ChatNotificationService

_RUN = os.getenv("RUN_INTEGRATION_TESTS") == "1"
_WAIT_SECONDS = 10

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _RUN,
        reason="Set RUN_INTEGRATION_TESTS=1 to run owned PostgreSQL regressions",
    ),
]


@pytest.fixture(autouse=True)
def _owned_outbox_listeners(prepare_database: None) -> Iterator[None]:
    """Install real capture hooks, retaining every pre-existing registration."""
    listeners = (
        ("after_flush", capture_domain_events),
        ("after_flush_postexec", _persist_captured_events),
        ("before_commit", capture_on_commit),
    )
    added = []
    try:
        for name, listener in listeners:
            if not sa_event.contains(Session, name, listener):
                sa_event.listen(Session, name, listener)
                added.append((name, listener))
        yield
    finally:
        for name, listener in reversed(added):
            sa_event.remove(Session, name, listener)


@pytest_asyncio.fixture
async def redis_state(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[fakeredis.aioredis.FakeRedis, SimpleNamespace]]:
    clock = SimpleNamespace(now=1_000_000.0)
    # Advance only FakeRedis command time, never asyncio's barrier deadlines.
    monkeypatch.setattr(_base, "time", SimpleNamespace(time=lambda: clock.now))
    cache = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def cache_client():
        return cache

    monkeypatch.setattr(cache_module, "get_cache_client", cache_client)
    monkeypatch.setattr(command_service.ws_manager, "is_online", lambda _user_id: False)
    try:
        yield cache, clock
    finally:
        await cache.aclose()


async def _seed_chat(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> tuple[uuid.UUID, User]:
    bind = db_session.get_bind()
    if bind.dialect.name != "postgresql" or bind.dialect.driver != "asyncpg":
        pytest.fail("AUD-262 requires real PostgreSQL through asyncpg")
    user = await user_factory()
    peer = await user_factory()
    chat = Chat(participants=[user, peer])
    db_session.add(chat)
    await db_session.commit()
    return chat.id, user


def _dispatcher(session: AsyncSession) -> command_service.ChatMessageDispatcher:
    return command_service.ChatMessageDispatcher(
        uow_from_session(session),
        ChatAttachmentService(),
        ChatNotificationService(session),
    )


async def _send(
    chat_id: uuid.UUID, user: User, content: str, client_key: str
) -> MessageResponse:
    async with AsyncSession(database.engine, expire_on_commit=False) as session:
        await ChatRepository(session).set_message_rls_user(user.id)
        return await _dispatcher(session).send_message(
            chat_id, user, content, [], "en", idempotency_key=client_key
        )


async def _counts(
    session: AsyncSession, chat_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[int, int]:
    await ChatRepository(session).set_message_rls_user(user_id)
    message_count = await session.scalar(
        select(func.count()).select_from(Message).where(Message.chat_id == chat_id)
    )
    event_count = await session.scalar(
        select(func.count())
        .select_from(StoredEvent)
        .where(
            StoredEvent.event_type == MessageSent.EVENT_TYPE,
            StoredEvent.aggregate_type == "Message",
            StoredEvent.payload["chat_id"].as_string() == str(chat_id),
        )
    )
    return int(message_count or 0), int(event_count or 0)


async def _committed_counts(chat_id: uuid.UUID, user_id: uuid.UUID) -> tuple[int, int]:
    # A new connection/session cannot see another request's uncommitted rows.
    async with AsyncSession(database.engine, expire_on_commit=False) as session:
        return await _counts(session, chat_id, user_id)


async def _finish_tasks(
    release: asyncio.Event, tasks: list[asyncio.Task[MessageResponse]]
) -> None:
    release.set()
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=_WAIT_SECONDS
        )


@pytest.mark.parametrize("state_loss", ["deleted", "expired"])
async def test_committed_send_replays_after_pending_state_loss(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    redis_state: tuple[fakeredis.aioredis.FakeRedis, SimpleNamespace],
    monkeypatch: pytest.MonkeyPatch,
    state_loss: str,
) -> None:
    chat_id, user = await _seed_chat(db_session, user_factory)
    cache, clock = redis_state
    real_change = command_service._change_idempotency_slot

    async def fail_completed_promotion(
        key: str, expected: str, replacement: str | None = None, *, ttl: int = 300
    ) -> bool:
        if (
            replacement is not None
            and json.loads(replacement).get("status") == "completed"
        ):
            raise RedisConnectionError("AUD-262 injected completion transport failure")
        return await real_change(key, expected, replacement, ttl=ttl)

    monkeypatch.setattr(
        command_service, "_change_idempotency_slot", fail_completed_promotion
    )
    client_key = uuid.uuid4().hex
    original = await _send(chat_id, user, "original fixture", client_key)
    assert await _committed_counts(chat_id, user.id) == (1, 1)

    cache_key = command_service._make_idempotency_key(chat_id, user.id, client_key)
    pending = await cache.get(cache_key)
    assert pending is not None
    assert json.loads(pending)["status"] == "pending"
    assert 0 < await cache.ttl(cache_key) <= 300
    if state_loss == "deleted":
        await cache.delete(cache_key)
    else:
        clock.now += 301
    assert await cache.get(cache_key) is None

    replay = await _send(chat_id, user, "different retry fixture", client_key)
    assert await _committed_counts(chat_id, user.id) == (1, 1), (
        "committed retry duplicated a message or outbox event after Redis state loss"
    )
    assert replay.id == original.id
    if replay.content != original.content:
        raise AssertionError("first successful message payload was not preserved")


async def test_overlapping_sends_survive_redis_lease_loss(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    redis_state: tuple[fakeredis.aioredis.FakeRedis, SimpleNamespace],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id, user = await _seed_chat(db_session, user_factory)
    cache, _clock = redis_state
    client_key = uuid.uuid4().hex
    cache_key = command_service._make_idempotency_key(chat_id, user.id, client_key)
    owner_ready, replacement_started, release = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )
    tasks: list[asyncio.Task[MessageResponse]] = []

    async with AsyncSession(database.engine, expire_on_commit=False) as owner_session:
        await ChatRepository(owner_session).set_message_rls_user(user.id)
        owner = _dispatcher(owner_session)
        real_create = owner.repository.create_message

        async def pause_owner_before_insert(message: Message):
            owner_ready.set()
            await asyncio.wait_for(release.wait(), timeout=_WAIT_SECONDS)
            return await real_create(message)

        monkeypatch.setattr(
            owner.repository, "create_message", pause_owner_before_insert
        )
        try:
            tasks.append(
                asyncio.create_task(
                    owner.send_message(
                        chat_id,
                        user,
                        "overlap fixture",
                        [],
                        "en",
                        idempotency_key=client_key,
                    )
                )
            )
            await asyncio.wait_for(owner_ready.wait(), timeout=_WAIT_SECONDS)
            owner_pending = await cache.get(cache_key)
            assert owner_pending is not None
            assert json.loads(owner_pending)["status"] == "pending"
            assert await _committed_counts(chat_id, user.id) == (0, 0)

            # A has passed its lease check but has not inserted. Its deleted
            # token cannot promote a completed cache entry. Start a real second
            # request without requiring it to pass any future durable guard.
            await cache.delete(cache_key)

            async def start_replacement() -> MessageResponse:
                replacement_started.set()
                return await _send(chat_id, user, "overlap fixture", client_key)

            tasks.append(asyncio.create_task(start_replacement()))
            await asyncio.wait_for(replacement_started.wait(), timeout=_WAIT_SECONDS)
            release.set()
            results = await asyncio.wait_for(
                asyncio.gather(*tasks), timeout=_WAIT_SECONDS
            )
        finally:
            await _finish_tasks(release, tasks)

    assert await _committed_counts(chat_id, user.id) == (1, 1), (
        "overlapping Redis admissions committed duplicate messages or outbox events"
    )
    assert results[0].id == results[1].id


async def test_live_pending_lease_rejects_overlapping_send(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    redis_state: tuple[fakeredis.aioredis.FakeRedis, SimpleNamespace],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id, user = await _seed_chat(db_session, user_factory)
    _cache, _clock = redis_state
    client_key = uuid.uuid4().hex
    owner_ready, release = asyncio.Event(), asyncio.Event()
    tasks: list[asyncio.Task[MessageResponse]] = []

    async with AsyncSession(database.engine, expire_on_commit=False) as owner_session:
        await ChatRepository(owner_session).set_message_rls_user(user.id)
        owner = _dispatcher(owner_session)
        real_create = owner.repository.create_message

        async def pause_owner_before_insert(message: Message):
            owner_ready.set()
            await asyncio.wait_for(release.wait(), timeout=_WAIT_SECONDS)
            return await real_create(message)

        monkeypatch.setattr(
            owner.repository, "create_message", pause_owner_before_insert
        )
        try:
            tasks.append(
                asyncio.create_task(
                    owner.send_message(
                        chat_id,
                        user,
                        "live lease fixture",
                        [],
                        "en",
                        idempotency_key=client_key,
                    )
                )
            )
            await asyncio.wait_for(owner_ready.wait(), timeout=_WAIT_SECONDS)
            with pytest.raises(HTTPException) as conflict:
                await asyncio.wait_for(
                    _send(chat_id, user, "live lease fixture", client_key),
                    timeout=_WAIT_SECONDS,
                )
            assert conflict.value.status_code == 409
            assert conflict.value.detail["error"] == "idempotency_in_progress"
            assert conflict.value.headers["Retry-After"] == "1"
            assert await _committed_counts(chat_id, user.id) == (0, 0)
            release.set()
            result = await asyncio.wait_for(tasks[0], timeout=_WAIT_SECONDS)
        finally:
            await _finish_tasks(release, tasks)

    assert await _committed_counts(chat_id, user.id) == (1, 1)
    replay = await _send(chat_id, user, "ignored retry fixture", client_key)
    assert replay.id == result.id
    assert await _committed_counts(chat_id, user.id) == (1, 1)


async def test_rolled_back_send_succeeds_after_pending_lease_expiry(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    redis_state: tuple[fakeredis.aioredis.FakeRedis, SimpleNamespace],
) -> None:
    """A failed commit attempt rolls back SQL but retains its bounded Redis lease."""
    chat_id, user = await _seed_chat(db_session, user_factory)
    cache, clock = redis_state
    client_key = uuid.uuid4().hex

    async with AsyncSession(database.engine, expire_on_commit=False) as session:
        await ChatRepository(session).set_message_rls_user(user.id)
        sender = _dispatcher(session)

        def fail_before_commit(sync_session: Session) -> None:
            # The production class listeners have already captured MessageSent.
            # Flush those real pending rows, then fail before any DB COMMIT.
            sync_session.flush()
            message_count = sync_session.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.chat_id == chat_id)
            )
            event_count = sync_session.scalar(
                select(func.count())
                .select_from(StoredEvent)
                .where(
                    StoredEvent.event_type == MessageSent.EVENT_TYPE,
                    StoredEvent.aggregate_type == "Message",
                    StoredEvent.payload["chat_id"].as_string() == str(chat_id),
                )
            )
            assert (message_count, event_count) == (1, 1)
            raise RuntimeError("AUD-262 injected precommit failure")

        sa_event.listen(session.sync_session, "before_commit", fail_before_commit)
        try:
            with pytest.raises(
                RuntimeError, match="AUD-262 injected precommit failure"
            ):
                await sender.send_message(
                    chat_id,
                    user,
                    "rollback fixture",
                    [],
                    "en",
                    idempotency_key=client_key,
                )
        finally:
            sa_event.remove(session.sync_session, "before_commit", fail_before_commit)

    assert await _committed_counts(chat_id, user.id) == (0, 0)
    cache_key = command_service._make_idempotency_key(chat_id, user.id, client_key)
    pending = await cache.get(cache_key)
    assert pending is not None
    pending_payload = json.loads(pending)
    assert pending_payload["status"] == "pending"
    assert pending_payload["owner"]
    assert 0 < await cache.ttl(cache_key) <= 300
    # commit_attempted is already true when the hook raises. Existing behavior
    # intentionally retains this lease, even though the SQL rollback succeeded.
    clock.now += 301
    assert await cache.get(cache_key) is None
    result = await _send(chat_id, user, "rollback fixture", client_key)
    assert result.chat_id == chat_id
    assert await _committed_counts(chat_id, user.id) == (1, 1)
