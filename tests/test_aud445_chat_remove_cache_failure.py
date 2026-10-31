"""A committed removal owns durable cache-repair intent."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest
from fastapi import HTTPException
from nats.errors import (
    BadSubjectError,
    ConnectionClosedError,
    ConnectionDrainingError,
    ConnectionReconnectingError,
    NoRespondersError,
    NoServersError,
    StaleConnectionError,
)
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.ws import presence
from app.core.events import ChatParticipantCacheInvalidation, ChatParticipantRemoved
from app.deps.cache import (
    MemoryCache,
    RedisCache,
    StrictCacheInvalidationError,
    versioned_key,
)
from app.models.chat import chat_participants
from app.models.domain_events import StoredEvent
from app.models.users import User
from app.repositories.chat_repository import ChatRepository
from app.repositories.unit_of_work import uow_from_session
from app.services.chat.attachment_service import ChatAttachmentService
from app.services.chat.command_service import ChatMaintenanceService
from app.services.event_handlers import handle_chat_participant_cache_invalidation

_CACHE_EVENT = "chat.participant_cache_invalidation"


class FailOnceCache(MemoryCache):
    def __init__(self, failed_key: str) -> None:
        super().__init__(default_ttl=3600)
        self.failed_key = failed_key
        self.failed = False

    async def invalidate(self, *keys: str) -> None:
        if self.failed_key in keys and not self.failed:
            self.failed = True
            raise ConnectionError("owned cache outage")
        await super().invalidate(*keys)


async def _stored_events(db_session: AsyncSession) -> list[StoredEvent]:
    return list(
        (
            await db_session.scalars(
                select(StoredEvent).where(
                    StoredEvent.event_type.in_(
                        [ChatParticipantRemoved.EVENT_TYPE, _CACHE_EVENT]
                    )
                )
            )
        ).all()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_kind", ["chat", "presence"])
async def test_committed_removal_survives_cache_outage_and_owner_retry(
    failed_kind: str,
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, member = await user_factory(), await user_factory()
    repo = ChatRepository(db_session)
    chat = await repo.create_group(owner, "aud445-outage", [member])
    await db_session.commit()
    chat_key = versioned_key(f"chat:{chat.id}:participants")
    audience_key = versioned_key(f"user:{owner.id}:presence_audience")
    failed_key = chat_key if failed_kind == "chat" else audience_key
    cache = FailOnceCache(failed_key)
    await cache.set(chat_key, [str(owner.id), str(member.id)])
    await cache.set(audience_key, [str(member.id)])
    monkeypatch.setattr(presence, "get_cache", lambda: cache)
    hub = AsyncMock()
    monkeypatch.setattr("app.services.ws_hub_client.invalidate_ws_hub_cache", hub)
    service = ChatMaintenanceService(
        uow_from_session(db_session), ChatAttachmentService()
    )

    await service.remove_participant(chat.id, owner, member.id, "en")

    assert cache.failed
    assert not await repo.check_participant(chat.id, member.id)
    events = await _stored_events(db_session)
    assert [event.event_type for event in events].count(
        ChatParticipantRemoved.EVENT_TYPE
    ) == 1
    assert [event.event_type for event in events].count(_CACHE_EVENT) == 1
    assert await cache.get(failed_key) is not None
    hub.assert_awaited_once()

    for _ in range(3):
        await service.remove_participant(chat.id, owner, member.id, "en")
    assert await cache.get(failed_key) is None
    assert len(await _stored_events(db_session)) == len(events)
    hub.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_commit_rolls_back_membership_and_all_events(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, member = await user_factory(), await user_factory()
    repo = ChatRepository(db_session)
    chat = await repo.create_group(owner, "aud445-rollback", [member])
    await db_session.commit()
    chat_id, owner_id, member_id = chat.id, owner.id, member.id
    uow = uow_from_session(db_session)
    monkeypatch.setattr(
        uow, "commit", AsyncMock(side_effect=RuntimeError("owned commit failure"))
    )
    strict = AsyncMock()
    monkeypatch.setattr(presence, "get_cache", lambda: SimpleCache(strict))
    hub = AsyncMock()
    monkeypatch.setattr("app.services.ws_hub_client.invalidate_ws_hub_cache", hub)
    service = ChatMaintenanceService(uow, ChatAttachmentService())

    with pytest.raises(RuntimeError, match="owned commit failure"):
        await service.remove_participant(chat_id, owner, member_id, "en")

    assert await repo.check_participant(chat_id, owner_id)
    assert await repo.check_participant(chat_id, member_id)
    assert await _stored_events(db_session) == []
    strict.assert_not_awaited()
    hub.assert_not_awaited()


class SimpleCache:
    enabled = True

    def __init__(self, strict: AsyncMock) -> None:
        self.invalidate_strict = strict
        self.invalidate = AsyncMock()


@pytest.mark.asyncio
async def test_removal_stages_bounded_cache_jobs_for_large_roster(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, member = await user_factory(), await user_factory()
    repo = ChatRepository(db_session)
    chat = await repo.create_group(owner, "aud445-large", [member])
    additions = [
        User(
            email=f"aud445-{uuid.uuid4().hex}@example.test",
            hashed_password=uuid.uuid4().hex,
        )
        for _ in range(130)
    ]
    db_session.add_all(additions)
    await db_session.flush()
    await db_session.execute(
        insert(chat_participants),
        [{"chat_id": chat.id, "user_id": user.id} for user in additions],
    )
    await db_session.commit()
    strict = AsyncMock(return_value="process_only")
    monkeypatch.setattr(presence, "get_cache", lambda: SimpleCache(strict))
    monkeypatch.setattr(
        "app.services.ws_hub_client.invalidate_ws_hub_cache", AsyncMock()
    )
    service = ChatMaintenanceService(
        uow_from_session(db_session), ChatAttachmentService()
    )

    await service.remove_participant(chat.id, owner, member.id, "en")

    cache_events = [
        row
        for row in await _stored_events(db_session)
        if row.event_type == _CACHE_EVENT
    ]
    assert len(cache_events) == 2
    chunks = [row.payload["participant_ids"] for row in cache_events]
    assert all(1 <= len(chunk) <= 128 for chunk in chunks)
    captured = [user_id for chunk in chunks for user_id in chunk]
    assert set(captured) == {
        str(owner.id),
        str(member.id),
        *(str(user.id) for user in additions),
    }
    assert len(captured) == len(set(captured))
    assert all(row.payload["cache_key_version"] == 1 for row in cache_events)
    assert all(row.aggregate_type == "ChatMembershipCache" for row in cache_events)
    assert all(row.aggregate_id == str(row.id) for row in cache_events)
    assert all(row.id.version == 7 for row in cache_events)


@pytest.mark.asyncio
async def test_postcommit_cancellation_propagates_with_durable_intent(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, member = await user_factory(), await user_factory()
    repo = ChatRepository(db_session)
    chat = await repo.create_group(owner, "aud445-cancel", [member])
    await db_session.commit()
    strict = AsyncMock(side_effect=asyncio.CancelledError())
    monkeypatch.setattr(presence, "get_cache", lambda: SimpleCache(strict))
    hub = AsyncMock()
    monkeypatch.setattr("app.services.ws_hub_client.invalidate_ws_hub_cache", hub)
    service = ChatMaintenanceService(
        uow_from_session(db_session), ChatAttachmentService()
    )

    with pytest.raises(asyncio.CancelledError):
        await service.remove_participant(chat.id, owner, member.id, "en")

    assert not await repo.check_participant(chat.id, member.id)
    assert len(await _stored_events(db_session)) == 2
    hub.assert_awaited_once()


@pytest.mark.asyncio
async def test_persistent_outage_and_repeated_owner_noops_do_not_grow_outbox(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, member = await user_factory(), await user_factory()
    repo = ChatRepository(db_session)
    chat = await repo.create_group(owner, "aud445-repeated", [member])
    await db_session.commit()
    strict = AsyncMock(side_effect=StrictCacheInvalidationError("owned outage"))
    monkeypatch.setattr(presence, "get_cache", lambda: SimpleCache(strict))
    hub = AsyncMock()
    monkeypatch.setattr("app.services.ws_hub_client.invalidate_ws_hub_cache", hub)
    service = ChatMaintenanceService(
        uow_from_session(db_session), ChatAttachmentService()
    )

    await service.remove_participant(chat.id, owner, member.id, "en")
    first_ids = {row.id for row in await _stored_events(db_session)}
    assert len(first_ids) == 2
    for _ in range(10):
        await service.remove_participant(chat.id, owner, member.id, "en")

    assert {row.id for row in await _stored_events(db_session)} == first_ids
    assert strict.await_count == 11
    hub.assert_awaited_once()


@pytest.mark.asyncio
async def test_lost_commit_ack_preserves_removal_and_original_durable_events(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, member = await user_factory(), await user_factory()
    repo = ChatRepository(db_session)
    chat = await repo.create_group(owner, "aud445-lost-ack", [member])
    await db_session.commit()
    chat_id, member_id = chat.id, member.id
    strict = AsyncMock(return_value="process_only")
    monkeypatch.setattr(presence, "get_cache", lambda: SimpleCache(strict))
    hub = AsyncMock()
    monkeypatch.setattr("app.services.ws_hub_client.invalidate_ws_hub_cache", hub)
    uow = uow_from_session(db_session)
    original_commit = uow.commit

    async def commit_then_fail() -> None:
        await original_commit()
        raise ConnectionError("owned lost commit acknowledgement")

    monkeypatch.setattr(uow, "commit", commit_then_fail)
    service = ChatMaintenanceService(uow, ChatAttachmentService())
    with pytest.raises(ConnectionError, match="owned lost commit acknowledgement"):
        await service.remove_participant(chat_id, owner, member_id, "en")
    assert not await repo.check_participant(chat_id, member_id)
    events = await _stored_events(db_session)
    assert {row.event_type for row in events} == {
        ChatParticipantRemoved.EVENT_TYPE,
        _CACHE_EVENT,
    }
    strict.assert_not_awaited()
    hub.assert_not_awaited()

    await db_session.refresh(owner)
    monkeypatch.setattr(uow, "commit", original_commit)
    await service.remove_participant(chat_id, owner, member_id, "en")
    assert {row.id for row in await _stored_events(db_session)} == {
        row.id for row in events
    }
    strict.assert_awaited_once()
    hub.assert_not_awaited()


@pytest.mark.asyncio
async def test_self_leave_retry_does_not_authorize_a_former_member(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, member = await user_factory(), await user_factory()
    repo = ChatRepository(db_session)
    chat = await repo.create_group(owner, "aud445-self-leave", [member])
    await db_session.commit()
    member_id, chat_id = member.id, chat.id
    strict = AsyncMock(return_value="process_only")
    monkeypatch.setattr(presence, "get_cache", lambda: SimpleCache(strict))
    monkeypatch.setattr(
        "app.services.ws_hub_client.invalidate_ws_hub_cache", AsyncMock()
    )
    service = ChatMaintenanceService(
        uow_from_session(db_session), ChatAttachmentService()
    )

    await service.remove_participant(chat_id, member, member_id, "en")
    before = {row.id for row in await _stored_events(db_session)}
    with pytest.raises(HTTPException) as denied:
        await service.remove_participant(chat_id, member, member_id, "en")
    assert denied.value.status_code == 403
    assert {row.id for row in await _stored_events(db_session)} == before


@pytest.mark.asyncio
async def test_unexpected_cache_error_propagates_after_commit_with_intent_saved(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, member = await user_factory(), await user_factory()
    repo = ChatRepository(db_session)
    chat = await repo.create_group(owner, "aud445-unexpected", [member])
    await db_session.commit()
    strict = AsyncMock(side_effect=ValueError("owned unexpected error"))
    monkeypatch.setattr(presence, "get_cache", lambda: SimpleCache(strict))
    hub = AsyncMock()
    monkeypatch.setattr("app.services.ws_hub_client.invalidate_ws_hub_cache", hub)
    service = ChatMaintenanceService(
        uow_from_session(db_session), ChatAttachmentService()
    )

    with pytest.raises(ValueError, match="owned unexpected error"):
        await service.remove_participant(chat.id, owner, member.id, "en")
    assert not await repo.check_participant(chat.id, member.id)
    assert len(await _stored_events(db_session)) == 2
    hub.assert_awaited_once()


@pytest.mark.asyncio
async def test_unavailable_jetstream_does_not_turn_committed_removal_into_failure(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, member = await user_factory(), await user_factory()
    repo = ChatRepository(db_session)
    chat = await repo.create_group(owner, "aud445-hub-outage", [member])
    await db_session.commit()
    strict = AsyncMock(return_value="process_only")
    monkeypatch.setattr(presence, "get_cache", lambda: SimpleCache(strict))
    hub = AsyncMock(side_effect=RuntimeError("NATS JetStream not available"))
    monkeypatch.setattr("app.services.ws_hub_client.invalidate_ws_hub_cache", hub)
    service = ChatMaintenanceService(
        uow_from_session(db_session), ChatAttachmentService()
    )

    await service.remove_participant(chat.id, owner, member.id, "en")

    assert not await repo.check_participant(chat.id, member.id)
    assert len(await _stored_events(db_session)) == 2
    strict.assert_awaited_once()
    hub.assert_awaited_once()


@pytest.mark.asyncio
async def test_unexpected_hub_runtime_error_still_propagates_after_commit(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, member = await user_factory(), await user_factory()
    repo = ChatRepository(db_session)
    chat = await repo.create_group(owner, "aud445-hub-unexpected", [member])
    await db_session.commit()
    strict = AsyncMock(return_value="process_only")
    monkeypatch.setattr(presence, "get_cache", lambda: SimpleCache(strict))
    hub = AsyncMock(side_effect=RuntimeError("unexpected bug"))
    monkeypatch.setattr("app.services.ws_hub_client.invalidate_ws_hub_cache", hub)
    service = ChatMaintenanceService(
        uow_from_session(db_session), ChatAttachmentService()
    )

    with pytest.raises(RuntimeError, match="unexpected bug"):
        await service.remove_participant(chat.id, owner, member.id, "en")
    assert not await repo.check_participant(chat.id, member.id)
    assert len(await _stored_events(db_session)) == 2
    strict.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_chat_has_no_locked_membership_snapshot(
    db_session: AsyncSession,
) -> None:
    assert (
        await ChatRepository(db_session).lock_membership_snapshot(uuid.uuid4()) is None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["add", "remove"])
async def test_membership_rollback_failure_preserves_original_error(
    operation: str,
) -> None:
    failure = RuntimeError("owned original transaction failure")
    uow = MagicMock()
    uow.chats.lock_membership_snapshot = AsyncMock(side_effect=failure)
    uow.rollback = AsyncMock(side_effect=RuntimeError("owned rollback failure"))
    uow.commit = AsyncMock()
    user = SimpleNamespace(id=uuid.uuid4())
    service = ChatMaintenanceService(uow, ChatAttachmentService())

    with pytest.raises(RuntimeError) as caught:
        await getattr(service, f"{operation}_participant")(
            uuid.uuid4(), user, uuid.uuid4(), "en"
        )
    assert caught.value is failure
    uow.rollback.assert_awaited_once()
    uow.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_cleanup_event_repairs_cache_without_client_retry(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, member = await user_factory(), await user_factory()
    repo = ChatRepository(db_session)
    chat = await repo.create_group(owner, "aud445-redis-recovery", [member])
    await db_session.commit()
    key = versioned_key(f"user:{owner.id}:presence_audience")
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = RedisCache("redis://localhost:6379/0", default_ttl=3600)
    cache._client = client
    await cache.set(key, [str(member.id)])
    real_delete = client.delete
    failed = False

    async def fail_once(*keys: str) -> int:
        nonlocal failed
        if key in keys and not failed:
            failed = True
            raise RedisConnectionError("owned cache outage")
        return await real_delete(*keys)

    monkeypatch.setattr(client, "delete", fail_once)
    monkeypatch.setattr(presence, "get_cache", lambda: cache)
    hub = AsyncMock()
    monkeypatch.setattr("app.services.ws_hub_client.invalidate_ws_hub_cache", hub)
    service = ChatMaintenanceService(
        uow_from_session(db_session), ChatAttachmentService()
    )
    try:
        await service.remove_participant(chat.id, owner, member.id, "en")
        assert failed
        assert not await repo.check_participant(chat.id, member.id)
        assert await cache.get(key) is not None
        rows = [
            row
            for row in await _stored_events(db_session)
            if row.event_type == _CACHE_EVENT
        ]
        assert len(rows) == 1
        monkeypatch.setattr(client, "delete", real_delete)
        await handle_chat_participant_cache_invalidation(
            ChatParticipantCacheInvalidation(**rows[0].payload)
        )
        assert await cache.get(key) is None
        hub.assert_awaited_once()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_cache_event_staging_failure_rolls_back_deletion_and_hub_event(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, member = await user_factory(), await user_factory()
    repo = ChatRepository(db_session)
    chat = await repo.create_group(owner, "aud445-stage-fault", [member])
    await db_session.commit()
    chat_id, owner_id, member_id = chat.id, owner.id, member.id
    strict = AsyncMock()
    monkeypatch.setattr(presence, "get_cache", lambda: SimpleCache(strict))
    hub = AsyncMock()
    monkeypatch.setattr("app.services.ws_hub_client.invalidate_ws_hub_cache", hub)
    service = ChatMaintenanceService(
        uow_from_session(db_session), ChatAttachmentService()
    )
    original_add = service.repository.add

    def fail_cache_event(event: StoredEvent) -> None:
        if event.event_type == _CACHE_EVENT:
            raise RuntimeError("owned outbox staging failure")
        original_add(event)

    monkeypatch.setattr(service.repository, "add", fail_cache_event)
    with pytest.raises(RuntimeError, match="owned outbox staging failure"):
        await service.remove_participant(chat_id, owner, member_id, "en")
    assert await repo.check_participant(chat_id, owner_id)
    assert await repo.check_participant(chat_id, member_id)
    assert await _stored_events(db_session) == []
    strict.assert_not_awaited()
    hub.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_type",
    [
        ConnectionClosedError,
        ConnectionDrainingError,
        ConnectionReconnectingError,
        NoRespondersError,
        NoServersError,
        StaleConnectionError,
    ],
)
async def test_nats_transport_failure_does_not_hide_committed_removal(
    failure_type: type[Exception],
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, member = await user_factory(), await user_factory()
    repo = ChatRepository(db_session)
    chat = await repo.create_group(owner, "aud445-nats-fault", [member])
    await db_session.commit()
    strict = AsyncMock(return_value="process_only")
    monkeypatch.setattr(presence, "get_cache", lambda: SimpleCache(strict))
    hub = AsyncMock(side_effect=failure_type())
    monkeypatch.setattr("app.services.ws_hub_client.invalidate_ws_hub_cache", hub)
    service = ChatMaintenanceService(
        uow_from_session(db_session), ChatAttachmentService()
    )

    await service.remove_participant(chat.id, owner, member.id, "en")

    assert not await repo.check_participant(chat.id, member.id)
    assert len(await _stored_events(db_session)) == 2
    strict.assert_awaited_once()
    hub.assert_awaited_once()


@pytest.mark.asyncio
async def test_nats_bad_subject_error_is_not_hidden(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, member = await user_factory(), await user_factory()
    repo = ChatRepository(db_session)
    chat = await repo.create_group(owner, "aud445-nats-invalid", [member])
    await db_session.commit()
    strict = AsyncMock(return_value="process_only")
    monkeypatch.setattr(presence, "get_cache", lambda: SimpleCache(strict))
    monkeypatch.setattr(
        "app.services.ws_hub_client.invalidate_ws_hub_cache",
        AsyncMock(side_effect=BadSubjectError()),
    )
    service = ChatMaintenanceService(
        uow_from_session(db_session), ChatAttachmentService()
    )

    with pytest.raises(BadSubjectError):
        await service.remove_participant(chat.id, owner, member.id, "en")
    assert not await repo.check_participant(chat.id, member.id)
    assert len(await _stored_events(db_session)) == 2
    strict.assert_awaited_once()
