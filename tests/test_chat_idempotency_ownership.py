"""Real Redis transaction semantics around concurrent dispatcher sends."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest
from fakeredis import _basefakesocket
from fastapi import HTTPException

from app.deps import cache as cache_module
from app.services.chat import command_service
from app.services.chat.command_service import (
    ChatMessageDispatcher,
    _make_idempotency_key,
)


def dispatcher(user, chat_id, created, *, upload=None):
    uow = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
    uow.session = AsyncMock()
    repo = uow.chats
    repo.get_by_id = AsyncMock(return_value=SimpleNamespace(id=chat_id))
    repo.check_participant = AsyncMock(return_value=True)
    repo.update_timestamp_by_id = AsyncMock()

    async def create(message):
        message.id = uuid.uuid4()
        message.created_at = datetime.now(UTC)
        message.read_status = False
        message.sender = None
        message.attachments = []
        created.append(message)

    repo.create_message = AsyncMock(side_effect=create)

    def dto(message):
        item = MagicMock(replied_to=None)
        item.model_dump.return_value = dict(
            id=message.id,
            chat_id=chat_id,
            sender_id=user.id,
            content=message.content,
            created_at=message.created_at,
            read_status=False,
            sender=None,
            attachments=[],
        )
        item.sender_id = user.id
        return item

    async def last(ids, **kwargs):
        return {message.id: dto(message) for message in created if message.id in ids}

    async def by_id(message_id, **kwargs):
        return next(
            (dto(message) for message in created if message.id == message_id), None
        )

    repo.get_last_messages = AsyncMock(side_effect=last)
    repo.get_message_by_id = AsyncMock(side_effect=by_id)
    attachments = SimpleNamespace(
        process_upload=AsyncMock(side_effect=upload), cleanup_files=AsyncMock()
    )
    return ChatMessageDispatcher(uow, attachments, MagicMock())


@pytest.fixture
async def redis(monkeypatch):
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(
        cache_module, "get_cache_client", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(
        command_service, "ws_manager", SimpleNamespace(is_online=lambda _: False)
    )
    yield client
    await client.aclose()


@pytest.fixture
def redis_clock(monkeypatch):
    clock = SimpleNamespace(now=1_000_000.0)
    # Scope the clock to FakeRedis commands, leaving asyncio deadlines unchanged.
    monkeypatch.setattr(
        _basefakesocket, "time", SimpleNamespace(time=lambda: clock.now)
    )
    return clock


async def test_completed_send_replays_until_24_hour_window_expires(redis, redis_clock):
    user = SimpleNamespace(id=uuid.uuid4())
    chat_id = uuid.uuid4()
    created = []
    sender = dispatcher(user, chat_id, created)
    completed_at = redis_clock.now

    committed = await sender.send_message(
        chat_id, user, "hello", [], "en", idempotency_key="same"
    )
    # FakeRedis expires only after its deadline; straddle it by one millisecond.
    redis_clock.now = completed_at + 24 * 60 * 60 - 0.001
    replay = await sender.send_message(
        chat_id, user, "hello", [], "en", idempotency_key="same"
    )
    assert replay.id == committed.id
    assert len(created) == 1
    sender.uow.commit.assert_awaited_once()

    redis_clock.now = completed_at + 24 * 60 * 60 + 0.001
    fresh = await sender.send_message(
        chat_id, user, "hello", [], "en", idempotency_key="same"
    )
    assert fresh.id != committed.id
    assert [message.id for message in created] == [committed.id, fresh.id]
    assert sender.uow.commit.await_count == 2
    fresh_replay = await sender.send_message(
        chat_id, user, "hello", [], "en", idempotency_key="same"
    )
    assert fresh_replay.id == fresh.id
    assert len(created) == 2


async def test_upload_outliving_pending_lease_cannot_replace_completed_retry(
    redis, redis_clock
):
    user = SimpleNamespace(id=uuid.uuid4())
    chat_id = uuid.uuid4()
    created = []
    replacement = dispatcher(user, chat_id, created)
    replacement_results = []
    reserved_at = redis_clock.now

    async def upload(*args, **kwargs):
        redis_clock.now = reserved_at + 5 * 60 - 0.001
        with pytest.raises(HTTPException) as exc:
            await replacement.send_message(
                chat_id, user, "hello", [], "en", idempotency_key="same"
            )
        assert exc.value.status_code == 409
        replacement.repository.create_message.assert_not_awaited()

        # Let the pending lease expire while this upload is still in progress.
        redis_clock.now = reserved_at + 5 * 60 + 0.001
        replacement_results.append(
            await replacement.send_message(
                chat_id, user, "hello", [], "en", idempotency_key="same"
            )
        )
        return dict(url="/owned", file_type="text/plain", filename="a.txt", size=1)

    owner = dispatcher(user, chat_id, created, upload=upload)
    with pytest.raises(HTTPException) as exc:
        await owner.send_message(
            chat_id,
            user,
            "hello",
            [SimpleNamespace(size=1)],
            "en",
            idempotency_key="same",
        )
    assert exc.value.status_code == 409
    owner.repository.create_message.assert_not_awaited()
    owner.uow.commit.assert_not_awaited()
    owner.attachment_service.cleanup_files.assert_awaited_once_with(["/owned"])
    replacement.uow.commit.assert_awaited_once()
    assert [message.id for message in created] == [replacement_results[0].id]

    replay = await owner.send_message(
        chat_id, user, "hello", [], "en", idempotency_key="same"
    )
    assert replay.id == replacement_results[0].id
    assert len(created) == 1
    owner.repository.create_message.assert_not_awaited()
    owner.uow.commit.assert_not_awaited()


async def test_simultaneous_send_loser_cannot_insert_or_change_owner(redis):
    user = SimpleNamespace(id=uuid.uuid4())
    chat_id = uuid.uuid4()
    created = []
    started, finish = asyncio.Event(), asyncio.Event()

    async def upload(*args, **kwargs):
        started.set()
        await finish.wait()
        return dict(url="/owned", file_type="text/plain", filename="a.txt", size=1)

    owner = dispatcher(user, chat_id, created, upload=upload)
    loser = dispatcher(user, chat_id, created)
    key = _make_idempotency_key(chat_id, user.id, "same")
    task = asyncio.create_task(
        owner.send_message(
            chat_id,
            user,
            "hello",
            [SimpleNamespace(size=1)],
            "en",
            idempotency_key="same",
        )
    )
    try:
        await started.wait()
        pending = await redis.get(key)
        with pytest.raises(HTTPException) as exc:
            await loser.send_message(
                chat_id, user, "hello", [], "en", idempotency_key="same"
            )
        assert exc.value.status_code == 409
        assert exc.value.headers["Retry-After"] == "1"
        if exc.value.detail != {
            "error": "idempotency_in_progress",
            "message": "This message is already being processed; retry with the same key",
        }:
            raise AssertionError("idempotency_conflict_detail_contract")
        assert await redis.get(key) == pending
        loser.repository.create_message.assert_not_awaited()
        loser.uow.commit.assert_not_awaited()
    finally:
        finish.set()
        result = await task
    assert len(created) == 1
    assert json.loads(await redis.get(key))["message_id"] == str(result.id)
    retry = await loser.send_message(
        chat_id, user, "hello", [], "en", idempotency_key="same"
    )
    assert retry.id == result.id
    assert len(created) == 1


@pytest.mark.parametrize("failure", [True, False])
async def test_expired_owner_neither_deletes_nor_promotes_replacement(redis, failure):
    user = SimpleNamespace(id=uuid.uuid4())
    chat_id = uuid.uuid4()
    key = _make_idempotency_key(chat_id, user.id, "same")
    replacement = json.dumps({"status": "pending", "owner": "other-request"})

    async def upload(*args, **kwargs):
        await redis.set(key, replacement, ex=300)
        if failure:
            raise ValueError("upload failed")
        return dict(url="/owned", file_type="text/plain", filename="a.txt", size=1)

    sender = dispatcher(user, chat_id, [], upload=upload)
    if failure:
        with pytest.raises(ExceptionGroup):
            await sender.send_message(
                chat_id,
                user,
                "hello",
                [SimpleNamespace(size=1)],
                "en",
                idempotency_key="same",
            )
    else:
        with pytest.raises(HTTPException) as exc:
            await sender.send_message(
                chat_id,
                user,
                "hello",
                [SimpleNamespace(size=1)],
                "en",
                idempotency_key="same",
            )
        assert exc.value.status_code == 409
        sender.repository.create_message.assert_not_awaited()
    assert await redis.get(key) == replacement


async def test_failed_owner_releases_slot_for_retry(redis):
    user = SimpleNamespace(id=uuid.uuid4())
    chat_id = uuid.uuid4()
    created = []
    owner = dispatcher(user, chat_id, created)
    owner.repository.create_message.side_effect = ValueError("write failed")
    with pytest.raises(ValueError, match="write failed"):
        await owner.send_message(
            chat_id, user, "hello", [], "en", idempotency_key="same"
        )
    assert await redis.get(_make_idempotency_key(chat_id, user.id, "same")) is None
    retry = dispatcher(user, chat_id, created)
    await retry.send_message(chat_id, user, "hello", [], "en", idempotency_key="same")
    assert len(created) == 1


@pytest.mark.parametrize("replace_owner", [False, True])
async def test_watch_conflict_rechecks_actual_ownership(
    redis, monkeypatch, replace_owner
):
    key, owner, replacement = "idem:test", "owner", "other"
    await redis.set(key, owner)
    original_pipeline = redis.pipeline
    raced = False

    def pipeline(*args, **kwargs):
        nonlocal raced
        pipe = original_pipeline(*args, **kwargs)
        if not raced:
            raced = True
            execute = pipe.execute

            async def conflicting_execute(*args, **kwargs):
                await redis.set(key, replacement if replace_owner else owner)
                return await execute(*args, **kwargs)

            pipe.execute = conflicting_execute
        return pipe

    monkeypatch.setattr(redis, "pipeline", pipeline)
    changed = await command_service._change_idempotency_slot(key, owner)
    assert changed is (not replace_owner)
    assert await redis.get(key) == (replacement if replace_owner else None)


async def test_owner_safe_completion_handles_bytes(monkeypatch):
    client = fakeredis.aioredis.FakeRedis(decode_responses=False)
    monkeypatch.setattr(
        cache_module, "get_cache_client", AsyncMock(return_value=client)
    )
    try:
        await client.set("idem:test", "owner")
        assert await command_service._change_idempotency_slot(
            "idem:test", "owner", "done", ttl=86400
        )
        assert await client.get("idem:test") == b"done"
        assert await client.ttl("idem:test") > 86000
    finally:
        await client.aclose()


async def test_committed_message_survives_response_hydration_failure(redis):
    user = SimpleNamespace(id=uuid.uuid4())
    chat_id = uuid.uuid4()
    created = []
    owner = dispatcher(user, chat_id, created)
    owner.repository.get_last_messages.side_effect = ValueError("hydrate failed")
    with pytest.raises(ValueError, match="hydrate failed"):
        await owner.send_message(
            chat_id, user, "hello", [], "en", idempotency_key="same"
        )
    owner.uow.commit.assert_awaited_once()
    retried = await owner.send_message(
        chat_id, user, "hello", [], "en", idempotency_key="same"
    )
    assert retried.id == created[0].id
    assert len(created) == 1


async def test_completed_promotion_cannot_overwrite_replacement(redis):
    user = SimpleNamespace(id=uuid.uuid4())
    chat_id = uuid.uuid4()
    created = []
    owner = dispatcher(user, chat_id, created)
    key = _make_idempotency_key(chat_id, user.id, "same")
    replacement = json.dumps({"status": "pending", "owner": "another-request"})

    async def commit():
        await redis.set(key, replacement, ex=300)

    owner.uow.commit.side_effect = commit
    await owner.send_message(chat_id, user, "hello", [], "en", idempotency_key="same")
    assert len(created) == 1
    assert await redis.get(key) == replacement


async def test_simultaneous_dispatchers_persist_one_real_message(
    redis, db_session, user_factory
):
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models import Attachment, Chat, Message
    from app.repositories.unit_of_work import uow_from_session

    user = await user_factory()
    other = await user_factory()
    chat = Chat(participants=[user, other])
    db_session.add(chat)
    await db_session.commit()
    chat_id = chat.id
    started, finish = asyncio.Event(), asyncio.Event()

    async def upload(*args, **kwargs):
        started.set()
        await finish.wait()
        return dict(
            url="https://example.com/private-test-attachment",
            file_type="text/plain",
            filename="a.txt",
            size=1,
        )

    attachments = SimpleNamespace(
        process_upload=AsyncMock(side_effect=upload), cleanup_files=AsyncMock()
    )
    async with (
        AsyncSession(db_session.bind, expire_on_commit=False) as owner_session,
        AsyncSession(db_session.bind, expire_on_commit=False) as loser_session,
    ):
        owner = ChatMessageDispatcher(
            uow_from_session(owner_session), attachments, MagicMock()
        )
        loser = ChatMessageDispatcher(
            uow_from_session(loser_session), attachments, MagicMock()
        )
        task = asyncio.create_task(
            owner.send_message(
                chat_id,
                user,
                "only once",
                [SimpleNamespace(size=1)],
                "en",
                idempotency_key="same",
            )
        )
        try:
            await asyncio.wait_for(started.wait(), timeout=5)
            with pytest.raises(HTTPException) as exc:
                await loser.send_message(
                    chat_id, user, "only once", [], "en", idempotency_key="same"
                )
            assert exc.value.status_code == 409
            await loser_session.rollback()
        finally:
            finish.set()
            result = await task
        retry = await loser.send_message(
            chat_id, user, "only once", [], "en", idempotency_key="same"
        )
        assert retry.id == result.id
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Message).where(Message.chat_id == chat_id)
        )
        == 1
    )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(Attachment)
            .where(Attachment.message_id == result.id)
        )
        == 1
    )
    attachments.process_upload.assert_awaited_once()
