"""Cache cleanup retries must not suppress the separate hub revocation."""

from __future__ import annotations

import contextlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.ws import presence
from app.core import events
from app.deps import cache as cache_module
from app.deps.cache import RedisCache, StrictCacheInvalidationError
from app.models.domain_events import StoredEvent
from app.services import event_handlers
from app.workers.outbox import OutboxWorker


@pytest.mark.asyncio
async def test_cache_outbox_failure_is_retried_without_blocking_hub(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert hasattr(events, "ChatParticipantCacheInvalidation")
    assert hasattr(event_handlers, "handle_chat_participant_cache_invalidation")
    chat_id, member_id = uuid.uuid4(), uuid.uuid4()
    cache_id, hub_id = uuid.uuid4(), uuid.uuid4()
    cleanup = StoredEvent(
        id=cache_id,
        event_type=events.ChatParticipantCacheInvalidation.EVENT_TYPE,
        aggregate_type="ChatMembershipCache",
        aggregate_id=str(cache_id),
        payload={
            "chat_id": str(chat_id),
            "cache_key_version": 1,
            "participant_ids": [str(member_id)],
        },
    )
    hub = StoredEvent(
        id=hub_id,
        event_type=events.ChatParticipantRemoved.EVENT_TYPE,
        aggregate_type="Chat",
        aggregate_id=str(chat_id),
        payload={"chat_id": str(chat_id), "user_id": str(member_id)},
    )
    db_session.add_all([cleanup, hub])
    await db_session.commit()
    strict = AsyncMock(
        side_effect=[StrictCacheInvalidationError("owned outage"), "shared"]
    )
    monkeypatch.setattr(
        presence, "get_cache", lambda: SimpleNamespace(invalidate_strict=strict)
    )
    hub_delivery = AsyncMock()
    monkeypatch.setattr(
        "app.services.ws_hub_client.invalidate_ws_hub_cache", hub_delivery
    )

    @contextlib.asynccontextmanager
    async def session():
        yield db_session

    bus = events.EventBus()
    bus.subscribe(
        events.ChatParticipantCacheInvalidation.EVENT_TYPE,
        event_handlers.handle_chat_participant_cache_invalidation,
    )
    bus.subscribe(
        events.ChatParticipantRemoved.EVENT_TYPE,
        event_handlers.handle_chat_participant_removed,
    )
    monkeypatch.setattr("app.workers.outbox.async_session", session)
    monkeypatch.setattr("app.workers.outbox.event_bus", bus)
    worker = OutboxWorker(batch_size=2, max_retries=1)

    assert await worker.process_batch() == 1
    await db_session.refresh(cleanup)
    await db_session.refresh(hub)
    assert cleanup.processed_at is None
    assert cleanup.error_count == 1
    assert hub.processed_at is not None
    hub_delivery.assert_awaited_once_with(
        str(member_id),
        str(chat_id),
        evict_room=True,
        event_id=str(hub_id),
        raise_on_failure=True,
    )

    assert await worker.process_batch() == 1
    await db_session.refresh(cleanup)
    assert cleanup.processed_at is not None
    assert strict.await_count == 2
    assert strict.await_args_list[0].args == strict.await_args_list[1].args


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "override",
    [
        {"cache_key_version": True},
        {"cache_key_version": 0},
        {"participant_ids": []},
        {"participant_ids": ["not-a-uuid"]},
        {"participant_ids": ["ABCDEFAB-CDEF-4ABC-8DEF-ABCDEFABCDEF"]},
        {"participant_ids": ["00000000-0000-0000-0000-000000000001"] * 2},
        {"participant_ids": [str(uuid.uuid4())] * 129},
    ],
)
async def test_malformed_cache_event_cannot_delete_any_key(
    monkeypatch: pytest.MonkeyPatch, override: dict[str, object]
) -> None:
    assert hasattr(events, "ChatParticipantCacheInvalidation")
    assert hasattr(event_handlers, "handle_chat_participant_cache_invalidation")
    strict = AsyncMock()
    monkeypatch.setattr(
        presence, "get_cache", lambda: SimpleNamespace(invalidate_strict=strict)
    )
    payload = {
        "chat_id": str(uuid.uuid4()),
        "cache_key_version": 1,
        "participant_ids": [str(uuid.uuid4())],
    }
    payload.update(override)
    event = events.ChatParticipantCacheInvalidation(**payload)

    with pytest.raises(ValueError):
        await event_handlers.handle_chat_participant_cache_invalidation(event)
    strict.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_uses_persisted_version_not_current_namespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id, member_id = uuid.uuid4(), uuid.uuid4()
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = RedisCache("redis://localhost:6379/0", default_ttl=60)
    cache._client = client
    old_key = f"v1:user:{member_id}:presence_audience"
    new_key = f"v2:user:{member_id}:presence_audience"
    await client.set(old_key, "old")
    await client.set(new_key, "new")
    monkeypatch.setattr(cache_module, "_cache_key_version", 2)
    monkeypatch.setattr(presence, "get_cache", lambda: cache)
    try:
        await event_handlers.handle_chat_participant_cache_invalidation(
            events.ChatParticipantCacheInvalidation(
                chat_id=chat_id,
                participant_ids=[member_id],
                cache_key_version=1,
            )
        )
        assert await client.get(old_key) is None
        assert await client.get(new_key) == "new"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_unknown_strict_backend_outcome_does_not_acknowledge_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    strict = AsyncMock(return_value=None)
    monkeypatch.setattr(
        presence, "get_cache", lambda: SimpleNamespace(invalidate_strict=strict)
    )
    event = events.ChatParticipantCacheInvalidation(
        chat_id=uuid.uuid4(),
        participant_ids=[uuid.uuid4()],
        cache_key_version=1,
    )
    with pytest.raises(StrictCacheInvalidationError):
        await event_handlers.handle_chat_participant_cache_invalidation(event)


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["process_only", "disabled"])
async def test_local_or_disabled_scope_is_classified_without_claiming_shared_cleanup(
    monkeypatch: pytest.MonkeyPatch, scope: str
) -> None:
    strict = AsyncMock(return_value=scope)
    monkeypatch.setattr(
        presence, "get_cache", lambda: SimpleNamespace(invalidate_strict=strict)
    )
    event = events.ChatParticipantCacheInvalidation(
        chat_id=uuid.uuid4(), participant_ids=[uuid.uuid4()], cache_key_version=1
    )
    log = SimpleNamespace(info=MagicMock())
    monkeypatch.setattr(event_handlers, "logger", log)
    await event_handlers.handle_chat_participant_cache_invalidation(event)
    log.info.assert_called_once_with("chat_cache_invalidation_local_scope", scope=scope)


@pytest.mark.asyncio
async def test_crash_before_outbox_ack_retries_same_cache_job(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    event_id, chat_id, member_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    row = StoredEvent(
        id=event_id,
        event_type=events.ChatParticipantCacheInvalidation.EVENT_TYPE,
        aggregate_type="ChatMembershipCache",
        aggregate_id=str(event_id),
        payload={
            "chat_id": str(chat_id),
            "cache_key_version": 1,
            "participant_ids": [str(member_id)],
        },
    )
    db_session.add(row)
    await db_session.commit()
    strict = AsyncMock(return_value="shared")
    monkeypatch.setattr(
        presence, "get_cache", lambda: SimpleNamespace(invalidate_strict=strict)
    )

    @contextlib.asynccontextmanager
    async def session():
        yield db_session

    bus = events.EventBus()
    bus.subscribe(
        events.ChatParticipantCacheInvalidation.EVENT_TYPE,
        event_handlers.handle_chat_participant_cache_invalidation,
    )
    monkeypatch.setattr("app.workers.outbox.async_session", session)
    monkeypatch.setattr("app.workers.outbox.event_bus", bus)
    worker = OutboxWorker(batch_size=1)
    real_commit = db_session.commit
    monkeypatch.setattr(
        db_session,
        "commit",
        AsyncMock(side_effect=ConnectionError("owned acknowledgement loss")),
    )
    with pytest.raises(ConnectionError, match="owned acknowledgement loss"):
        await worker.process_batch()
    await db_session.rollback()
    await db_session.refresh(row)
    assert row.processed_at is None
    assert strict.await_count == 1

    monkeypatch.setattr(db_session, "commit", real_commit)
    assert await worker.process_batch() == 1
    await db_session.refresh(row)
    assert row.processed_at is not None
    assert strict.await_count == 2
    assert strict.await_args_list[0].args == strict.await_args_list[1].args


@pytest.mark.asyncio
async def test_invalid_cache_job_stays_pending_after_normal_retry_limit(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    event_id = uuid.uuid4()
    row = StoredEvent(
        id=event_id,
        event_type=events.ChatParticipantCacheInvalidation.EVENT_TYPE,
        aggregate_type="ChatMembershipCache",
        aggregate_id=str(event_id),
        payload={
            "chat_id": str(uuid.uuid4()),
            "cache_key_version": 1,
            "participant_ids": ["invalid"],
        },
    )
    db_session.add(row)
    await db_session.commit()
    strict = AsyncMock()
    monkeypatch.setattr(
        presence, "get_cache", lambda: SimpleNamespace(invalidate_strict=strict)
    )

    @contextlib.asynccontextmanager
    async def session():
        yield db_session

    bus = events.EventBus()
    bus.subscribe(
        events.ChatParticipantCacheInvalidation.EVENT_TYPE,
        event_handlers.handle_chat_participant_cache_invalidation,
    )
    monkeypatch.setattr("app.workers.outbox.async_session", session)
    monkeypatch.setattr("app.workers.outbox.event_bus", bus)
    worker = OutboxWorker(batch_size=1, max_retries=1)
    assert await worker.process_batch() == 0
    assert await worker.process_batch() == 0
    await db_session.refresh(row)
    assert row.processed_at is None
    assert row.error_count == 2
    strict.assert_not_awaited()
