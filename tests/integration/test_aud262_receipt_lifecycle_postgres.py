"""Receipt lifecycle acceptance with real PostgreSQL transactions and outbox rows."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import app.deps.cache as cache_module
import app.services.chat.command_service as command_service
from app.core import database
from app.models import Chat, Message, User
from app.models.chat import Attachment, chat_participants
from app.models.chat_send_receipt import ChatSendReceipt
from app.repositories.chat_repository import ChatRepository
from app.repositories.unit_of_work import uow_from_session
from app.services.chat.attachment_service import ChatAttachmentService
from tests.test_aud262_durable_replay_postgres import (
    _WAIT_SECONDS,
    _counts,
    _dispatcher,
    _seed_chat,
    _send,
)
from tests.test_aud262_durable_replay_postgres import (
    _owned_outbox_listeners as _owned_outbox_listeners,
)
from tests.test_aud262_durable_replay_postgres import (
    pytestmark as pytestmark,
)
from tests.test_aud262_durable_replay_postgres import (
    redis_state as redis_state,
)


class MemoryUploads:
    """Owned object-storage boundary; SQL attachments and transactions stay real."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def process_upload(
        self,
        upload: UploadFile,
        chat_id: uuid.UUID,
        *,
        locale: str | None,
    ) -> dict[str, str | int]:
        data = await upload.read()
        url = f"https://uploads.example.invalid/{chat_id}/{uuid.uuid4().hex}"
        self.objects[url] = data
        return {
            "url": url,
            "file_type": "file",
            "filename": upload.filename or "fixture.txt",
            "size": len(data),
        }

    async def cleanup_files(self, urls: list[str]) -> None:
        for url in urls:
            self.objects.pop(url, None)
            self.deleted.append(url)


async def _snapshot(
    chat_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[int, int, int, int]:
    async with AsyncSession(database.engine, expire_on_commit=False) as session:
        messages, sent_events = await _counts(session, chat_id, user_id)
        receipts = await session.scalar(
            select(func.count())
            .select_from(ChatSendReceipt)
            .where(
                ChatSendReceipt.chat_id == chat_id,
                ChatSendReceipt.user_id == user_id,
            )
        )
        attachments = await session.scalar(
            select(func.count())
            .select_from(Attachment)
            .join(Message, Attachment.message_id == Message.id)
            .where(Message.chat_id == chat_id)
        )
        return messages, sent_events, int(receipts or 0), int(attachments or 0)


async def _receipt(chat_id: uuid.UUID, user_id: uuid.UUID, key: str):
    async with AsyncSession(database.engine, expire_on_commit=False) as session:
        repository = ChatRepository(session)
        return await repository.get_send_receipt(
            chat_id,
            user_id,
            command_service._make_send_receipt_digest(chat_id, user_id, key),
        )


async def _expire_receipt(chat_id: uuid.UUID, user_id: uuid.UUID, key: str) -> None:
    async with AsyncSession(database.engine, expire_on_commit=False) as session:
        await ChatRepository(session).set_message_rls_user(user_id)
        await session.execute(
            update(ChatSendReceipt)
            .where(
                ChatSendReceipt.chat_id == chat_id,
                ChatSendReceipt.user_id == user_id,
                ChatSendReceipt.key_digest
                == command_service._make_send_receipt_digest(chat_id, user_id, key),
            )
            .values(
                completed_at=func.clock_timestamp() - text("interval '25 hours'"),
                expires_at=func.clock_timestamp() - text("interval '1 hour'"),
            )
        )
        await session.commit()


async def _redis_unavailable():
    raise RedisConnectionError("owned cache transport failure")


async def test_real_commit_lost_ack_replays_and_keeps_referenced_upload(
    db_session: AsyncSession,
    user_factory,
    redis_state,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id, user = await _seed_chat(db_session, user_factory)
    key = uuid.uuid4().hex
    storage = MemoryUploads()
    upload = UploadFile(
        file=BytesIO(b"committed attachment"), filename="ack.txt", size=20
    )
    failure = ConnectionError("owned lost commit acknowledgement")
    async with AsyncSession(database.engine, expire_on_commit=False) as session:
        await ChatRepository(session).set_message_rls_user(user.id)
        sender = _dispatcher(session)
        sender.attachment_service = storage
        real_commit = sender.uow.commit

        async def commit_then_lose_ack() -> None:
            await real_commit()
            raise failure

        monkeypatch.setattr(sender.uow, "commit", commit_then_lose_ack)
        try:
            with pytest.raises(ConnectionError) as caught:
                await sender.send_message(
                    chat_id, user, "first success", [upload], "en", idempotency_key=key
                )
            assert caught.value is failure
        finally:
            await upload.close()

    assert await _snapshot(chat_id, user.id) == (1, 1, 1, 1)
    receipt = await _receipt(chat_id, user.id, key)
    assert receipt is not None and receipt.message_id is not None
    assert len(storage.objects) == 1
    assert storage.deleted == []

    # An acknowledged retry must not need Redis or the original multipart files.
    monkeypatch.setattr(cache_module, "get_cache_client", _redis_unavailable)
    replay = await _send(chat_id, user, "", key)
    assert replay.id == receipt.message_id
    assert replay.content == "first success"
    assert len(replay.attachments) == 1
    assert replay.attachments[0].url in storage.objects
    assert await _snapshot(chat_id, user.id) == (1, 1, 1, 1)


@pytest.mark.parametrize("expired_reuse", [False, True])
@pytest.mark.parametrize("with_uploads", [False, True])
async def test_two_admitted_writers_commit_one_receipt_and_clean_only_loser_upload(
    db_session: AsyncSession,
    user_factory,
    redis_state,
    monkeypatch: pytest.MonkeyPatch,
    expired_reuse: bool,
    with_uploads: bool,
) -> None:
    chat_id, user = await _seed_chat(db_session, user_factory)
    key = uuid.uuid4().hex
    old_id = None
    if expired_reuse:
        old = await _send(chat_id, user, "expired generation", key)
        old_id = old.id
        await _expire_receipt(chat_id, user.id, key)

    cache, _clock = redis_state
    cache_key = command_service._make_idempotency_key(chat_id, user.id, key)
    await cache.delete(cache_key)
    storage = MemoryUploads()
    both_ready = asyncio.Event()
    release = asyncio.Event()
    arrived = 0
    tasks: list[asyncio.Task] = []
    recovered_rls: list[str] = []
    real_set = cache.set

    async def ineffective_set(name, value, *args, **kwargs):
        # Model lost Redis ownership without replacing any database operation.
        kwargs.pop("nx", None)
        return await real_set(name, value, *args, **kwargs)

    async def ineffective_compare(*_args, **_kwargs):
        return True

    monkeypatch.setattr(cache, "set", ineffective_set)
    monkeypatch.setattr(
        command_service, "_change_idempotency_slot", ineffective_compare
    )

    async def writer(label: str):
        nonlocal arrived
        async with AsyncSession(database.engine, expire_on_commit=False) as session:
            bound_user = await session.get(User, user.id)
            assert bound_user is not None
            await ChatRepository(session).set_message_rls_user(user.id)
            sender = _dispatcher(session)
            sender.attachment_service = storage
            real_create = sender.repository.create_message
            real_receipt_read = sender.repository.get_send_receipt
            real_rollback = sender.uow.rollback
            rolled_back = False

            async def observe_rollback() -> None:
                nonlocal rolled_back
                await real_rollback()
                rolled_back = True

            async def observe_recovery_identity(*args, **kwargs):
                if rolled_back:
                    # Query the real transaction-local GUC before the repository
                    # can repair it itself. A privileged CI role cannot hide a
                    # missing recovery SET LOCAL from this assertion.
                    actual = await session.scalar(
                        text("SELECT current_setting('app.current_user_id', true)")
                    )
                    assert actual == str(user.id)
                    recovered_rls.append(actual)
                return await real_receipt_read(*args, **kwargs)

            monkeypatch.setattr(sender.uow, "rollback", observe_rollback)
            monkeypatch.setattr(
                sender.repository, "get_send_receipt", observe_recovery_identity
            )

            async def rendezvous_before_insert(message: Message):
                nonlocal arrived
                arrived += 1
                if arrived == 2:
                    both_ready.set()
                await asyncio.wait_for(release.wait(), timeout=_WAIT_SECONDS)
                return await real_create(message)

            monkeypatch.setattr(
                sender.repository, "create_message", rendezvous_before_insert
            )
            upload = UploadFile(
                file=BytesIO(label.encode()),
                filename=f"{label}.txt",
                size=len(label),
            )
            try:
                result = await sender.send_message(
                    chat_id,
                    bound_user,
                    label,
                    [upload] if with_uploads else [],
                    "en",
                    idempotency_key=key,
                )
                # Reuse even the losing session. Rolled-back emitters must not
                # later publish a phantom MessageSent on an unrelated commit.
                await session.commit()
                return result
            finally:
                await upload.close()

    try:
        tasks = [asyncio.create_task(writer(label)) for label in ("first", "second")]
        await asyncio.wait_for(both_ready.wait(), timeout=_WAIT_SECONDS)
        assert len(storage.objects) == (2 if with_uploads else 0)
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=_WAIT_SECONDS)
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=_WAIT_SECONDS
            )

    assert recovered_rls and set(recovered_rls) == {str(user.id)}
    assert results[0].id == results[1].id
    assert results[0].id != old_id
    assert results[0].content == results[1].content
    if with_uploads:
        assert len(results[0].attachments) == len(results[1].attachments) == 1
        winner_url = results[0].attachments[0].url
        assert results[1].attachments[0].url == winner_url
        assert set(storage.objects) == {winner_url}
        assert len(storage.deleted) == 1 and winner_url not in storage.deleted
    else:
        assert results[0].attachments == results[1].attachments == []
        assert storage.objects == {}
        assert storage.deleted == []
    previous = int(expired_reuse)
    assert await _snapshot(chat_id, user.id) == (
        previous + 1,
        previous + 1,
        1,
        int(with_uploads),
    )


async def test_precommit_failure_rolls_back_message_receipt_attachment_and_event(
    db_session: AsyncSession,
    user_factory,
    redis_state,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id, user = await _seed_chat(db_session, user_factory)
    key = uuid.uuid4().hex
    storage = MemoryUploads()
    failure = RuntimeError("owned precommit failure")
    async with AsyncSession(database.engine, expire_on_commit=False) as session:
        await ChatRepository(session).set_message_rls_user(user.id)
        sender = _dispatcher(session)
        sender.attachment_service = storage

        async def fail_before_commit() -> None:
            await session.flush()
            assert await _counts(session, chat_id, user.id) == (1, 1)
            receipt_count = await session.scalar(
                select(func.count())
                .select_from(ChatSendReceipt)
                .where(ChatSendReceipt.chat_id == chat_id)
            )
            assert receipt_count == 1
            raise failure

        monkeypatch.setattr(sender.uow, "commit", fail_before_commit)
        upload = UploadFile(file=BytesIO(b"rollback"), filename="rollback.txt", size=8)
        try:
            with pytest.raises(RuntimeError) as caught:
                await sender.send_message(
                    chat_id, user, "rollback", [upload], "en", idempotency_key=key
                )
            assert caught.value is failure
            assert await _counts(session, chat_id, user.id) == (0, 0)
            await session.commit()
        finally:
            await upload.close()

    assert await _snapshot(chat_id, user.id) == (0, 0, 0, 0)
    assert storage.objects == {}
    assert len(storage.deleted) == 1


async def test_replay_preserves_fixed_expiry_and_never_refreshes_cache_ttl(
    db_session: AsyncSession,
    user_factory,
    redis_state,
) -> None:
    chat_id, user = await _seed_chat(db_session, user_factory)
    key = uuid.uuid4().hex
    original = await _send(chat_id, user, "fixed lifetime", key)
    before = await _receipt(chat_id, user.id, key)
    assert before is not None
    cache, clock = redis_state
    cache_key = command_service._make_idempotency_key(chat_id, user.id, key)
    cached = await cache.get(cache_key)
    assert cached is not None
    payload = json.loads(cached)
    assert payload["status"] == "completed"
    assert payload["receipt_version"] == 1
    assert payload["message_id"] == str(original.id)
    assert datetime.fromisoformat(payload["expires_at"]) == before.expires_at
    initial_ttl = await cache.ttl(cache_key)
    assert 0 < initial_ttl < 86400

    clock.now += 60
    replay = await _send(chat_id, user, "changed payload", key)
    after = await _receipt(chat_id, user.id, key)
    assert after is not None
    assert replay.id == original.id
    assert replay.content == "fixed lifetime"
    assert after.expires_at == before.expires_at
    assert await cache.get(cache_key) == cached
    assert await cache.ttl(cache_key) == initial_ttl - 60
    assert await _snapshot(chat_id, user.id) == (1, 1, 1, 0)


@pytest.mark.parametrize("removal", ["soft", "hard", "history"])
async def test_message_deletion_does_not_release_unexpired_receipt(
    db_session: AsyncSession,
    user_factory,
    redis_state,
    removal: str,
) -> None:
    user = await user_factory(role="admin")
    chat = Chat(participants=[user])
    db_session.add(chat)
    await db_session.commit()
    chat_id = chat.id
    key = uuid.uuid4().hex
    original = await _send(chat_id, user, "deleted fixture", key)
    before = await _receipt(chat_id, user.id, key)
    assert before is not None

    async with AsyncSession(database.engine, expire_on_commit=False) as session:
        repository = ChatRepository(session)
        await repository.set_message_rls_user(user.id)
        if removal == "soft":
            _, affected = await repository.soft_delete_message(
                original.id, user.id, chat_id=chat_id
            )
            assert affected == 1
            await session.commit()
        elif removal == "hard":
            deleted = await repository.delete_messages(
                [original.id], chat_id=chat_id, user_id=user.id
            )
            assert deleted == 1
            await session.commit()
        else:
            service = command_service.ChatMaintenanceService(
                uow_from_session(session), ChatAttachmentService()
            )
            result = await service.clear_history(chat_id, user, "en")
            assert result.deleted_messages == 1

    after = await _receipt(chat_id, user.id, key)
    assert after is not None and after.expires_at == before.expires_at
    if removal == "soft":
        replay = await _send(chat_id, user, "must not resurrect", key)
        assert replay.id == original.id
        assert replay.deleted_at is not None
        assert replay.content == ""
        assert after.message_id == original.id
        assert await _snapshot(chat_id, user.id) == (1, 1, 1, 0)
    else:
        assert after.message_id is None
        for _ in range(2):
            with pytest.raises(HTTPException) as caught:
                await _send(chat_id, user, "must not recreate", key)
            assert caught.value.status_code == 409
            assert caught.value.detail["error"] == "idempotency_in_progress"
            assert caught.value.headers["Retry-After"] == "1"
        blocked = await _receipt(chat_id, user.id, key)
        assert blocked is not None and blocked.expires_at == before.expires_at
        assert await _snapshot(chat_id, user.id) == (0, 1, 1, 0)


@pytest.mark.parametrize("receipt_state", ["missing", "expired"])
@pytest.mark.parametrize("cache_version", [None, 1])
async def test_stale_cache_cannot_override_observed_receipt_state(
    db_session: AsyncSession,
    user_factory,
    redis_state,
    receipt_state: str,
    cache_version: int | None,
) -> None:
    chat_id, user = await _seed_chat(db_session, user_factory)
    key = uuid.uuid4().hex
    original = await _send(chat_id, user, "old generation", key)
    original_receipt = await _receipt(chat_id, user.id, key)
    assert original_receipt is not None
    if receipt_state == "expired":
        await _expire_receipt(chat_id, user.id, key)
    else:
        async with AsyncSession(database.engine, expire_on_commit=False) as session:
            await ChatRepository(session).set_message_rls_user(user.id)
            await session.execute(
                delete(ChatSendReceipt).where(ChatSendReceipt.chat_id == chat_id)
            )
            await session.commit()

    cache, _clock = redis_state
    payload = {"status": "completed", "message_id": str(original.id)}
    if cache_version is not None:
        payload["receipt_version"] = cache_version
        payload["expires_at"] = original_receipt.expires_at.isoformat()
    await cache.set(
        command_service._make_idempotency_key(chat_id, user.id, key),
        json.dumps(payload),
        ex=86400,
    )
    result = await _send(chat_id, user, "new generation", key)
    if cache_version is None and receipt_state == "missing":
        assert result.id == original.id
        assert await _snapshot(chat_id, user.id) == (1, 1, 0, 0)
    else:
        assert result.id != original.id
        assert result.content == "new generation"
        assert await _snapshot(chat_id, user.id) == (2, 2, 1, 0)


async def test_receipts_remain_scoped_to_current_chat_and_sender(
    db_session: AsyncSession,
    user_factory,
    redis_state,
) -> None:
    user = await user_factory()
    peer = await user_factory()
    first_chat = Chat(participants=[user, peer])
    second_chat = Chat(participants=[user, peer])
    db_session.add_all([first_chat, second_chat])
    await db_session.commit()
    key = uuid.uuid4().hex
    first = await _send(first_chat.id, user, "first sender", key)
    other_sender = await _send(first_chat.id, peer, "other sender", key)
    other_chat = await _send(second_chat.id, user, "other chat", key)
    assert len({first.id, other_sender.id, other_chat.id}) == 3
    assert await _snapshot(first_chat.id, user.id) == (2, 2, 1, 0)
    assert await _snapshot(first_chat.id, peer.id) == (2, 2, 1, 0)
    assert await _snapshot(second_chat.id, user.id) == (1, 1, 1, 0)


async def test_current_membership_and_chat_existence_precede_receipt_and_redis(
    db_session: AsyncSession,
    user_factory,
    redis_state,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id, user = await _seed_chat(db_session, user_factory)
    key = uuid.uuid4().hex
    await _send(chat_id, user, "authorized before removal", key)
    await db_session.execute(
        delete(chat_participants).where(
            chat_participants.c.chat_id == chat_id,
            chat_participants.c.user_id == user.id,
        )
    )
    await db_session.commit()
    monkeypatch.setattr(cache_module, "get_cache_client", _redis_unavailable)
    with pytest.raises(HTTPException) as removed:
        await _send(chat_id, user, "", key)
    assert removed.value.status_code == 403

    await db_session.execute(delete(Chat).where(Chat.id == chat_id))
    await db_session.commit()
    with pytest.raises(HTTPException) as absent:
        await _send(chat_id, user, "", key)
    assert absent.value.status_code == 404


async def test_unrelated_real_unique_violation_is_not_receipt_replay(
    db_session: AsyncSession,
    user_factory,
    redis_state,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id, user = await _seed_chat(db_session, user_factory)
    existing = await _send(chat_id, user, "existing", uuid.uuid4().hex)
    failed_key = uuid.uuid4().hex
    async with AsyncSession(database.engine, expire_on_commit=False) as session:
        await ChatRepository(session).set_message_rls_user(user.id)
        sender = _dispatcher(session)
        real_create = sender.repository.create_message

        async def duplicate_primary_key(message: Message):
            message.id = existing.id
            return await real_create(message)

        monkeypatch.setattr(sender.repository, "create_message", duplicate_primary_key)
        with pytest.raises(IntegrityError):
            await sender.send_message(
                chat_id, user, "must fail", [], "en", idempotency_key=failed_key
            )
    assert await _receipt(chat_id, user.id, failed_key) is None
    assert await _snapshot(chat_id, user.id) == (1, 1, 1, 0)


async def test_cancelled_writer_propagates_cancellation_without_durable_rows(
    db_session: AsyncSession,
    user_factory,
    redis_state,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id, user = await _seed_chat(db_session, user_factory)
    key = uuid.uuid4().hex
    staged = asyncio.Event()
    release = asyncio.Event()
    async with AsyncSession(database.engine, expire_on_commit=False) as session:
        await ChatRepository(session).set_message_rls_user(user.id)
        sender = _dispatcher(session)
        real_receipt = sender.repository.create_send_receipt

        async def pause_before_receipt_insert(*args, **kwargs):
            # The real Message INSERT and record_event already happened. A
            # cancellation must discard this emitter as well as SQL rows.
            staged.set()
            await release.wait()
            return await real_receipt(*args, **kwargs)

        monkeypatch.setattr(
            sender.repository, "create_send_receipt", pause_before_receipt_insert
        )
        task = asyncio.create_task(
            sender.send_message(
                chat_id, user, "cancelled", [], "en", idempotency_key=key
            )
        )
        try:
            await asyncio.wait_for(staged.wait(), timeout=_WAIT_SECONDS)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=_WAIT_SECONDS)
            # Check before session context exit can hide a missing rollback.
            assert await _counts(session, chat_id, user.id) == (0, 0)
            await session.commit()
            assert await _counts(session, chat_id, user.id) == (0, 0)
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert await _snapshot(chat_id, user.id) == (0, 0, 0, 0)


async def test_deleted_message_key_is_reusable_at_database_expiry_boundary(
    db_session: AsyncSession,
    user_factory,
    redis_state,
) -> None:
    chat_id, user = await _seed_chat(db_session, user_factory)
    key = uuid.uuid4().hex
    original = await _send(chat_id, user, "expired deleted fixture", key)
    async with AsyncSession(database.engine, expire_on_commit=False) as session:
        repository = ChatRepository(session)
        await repository.set_message_rls_user(user.id)
        deleted = await repository.delete_messages(
            [original.id], chat_id=chat_id, user_id=user.id
        )
        assert deleted == 1
        await session.execute(
            update(ChatSendReceipt)
            .where(
                ChatSendReceipt.chat_id == chat_id,
                ChatSendReceipt.user_id == user.id,
            )
            .values(
                completed_at=func.transaction_timestamp() - text("interval '24 hours'"),
                expires_at=func.transaction_timestamp(),
            )
        )
        await session.commit()

    expired = await _receipt(chat_id, user.id, key)
    assert expired is not None
    assert expired.message_id is None
    assert expired.expires_at <= expired.observed_at
    replacement = await _send(chat_id, user, "new lifetime", key)
    assert replacement.id != original.id
    assert replacement.content == "new lifetime"
    assert await _snapshot(chat_id, user.id) == (1, 2, 1, 0)


async def test_receipt_cleanup_is_bounded_and_never_deletes_other_scopes(
    db_session: AsyncSession,
    user_factory,
    redis_state,
) -> None:
    chat_id, user = await _seed_chat(db_session, user_factory)
    peer_id = (
        await db_session.execute(
            select(chat_participants.c.user_id).where(
                chat_participants.c.chat_id == chat_id,
                chat_participants.c.user_id != user.id,
            )
        )
    ).scalar_one()
    other_chat = Chat(participants=[user])
    db_session.add(other_chat)
    await db_session.commit()
    other_chat_id = other_chat.id

    async def add_rows(owner_id, target_chat_id, count, *, expired):
        async with AsyncSession(database.engine, expire_on_commit=False) as session:
            await ChatRepository(session).set_message_rls_user(owner_id)
            for _ in range(count):
                session.add(
                    ChatSendReceipt(
                        chat_id=target_chat_id,
                        user_id=owner_id,
                        key_digest=uuid.uuid4().hex + uuid.uuid4().hex,
                        message_id=None,
                        completed_at=(
                            func.clock_timestamp()
                            - text(
                                "interval '25 hours'"
                                if expired
                                else "interval '23 hours'"
                            )
                        ),
                        expires_at=(
                            func.clock_timestamp() - text("interval '1 hour'")
                            if expired
                            else func.clock_timestamp() + text("interval '1 hour'")
                        ),
                    )
                )
            await session.commit()

    await add_rows(user.id, chat_id, 102, expired=True)
    await add_rows(user.id, chat_id, 1, expired=False)
    await add_rows(peer_id, chat_id, 1, expired=True)
    await add_rows(user.id, other_chat_id, 1, expired=True)

    async with AsyncSession(database.engine, expire_on_commit=False) as session:
        repository = ChatRepository(session)
        # A caller cannot expand this request-scoped cleanup into a table sweep.
        deleted = await repository.prune_expired_send_receipts(
            chat_id, user.id, limit=10000
        )
        assert deleted == 100
        await session.commit()

    assert await _snapshot(chat_id, user.id) == (0, 0, 3, 0)
    assert await _snapshot(chat_id, peer_id) == (0, 0, 1, 0)
    assert await _snapshot(other_chat_id, user.id) == (0, 0, 1, 0)
    async with AsyncSession(database.engine, expire_on_commit=False) as session:
        repository = ChatRepository(session)
        assert await repository.prune_expired_send_receipts(chat_id, user.id) == 2
        await session.commit()
    assert await _snapshot(chat_id, user.id) == (0, 0, 1, 0)


async def test_cache_secret_rotation_cannot_change_durable_replay_identity(
    db_session: AsyncSession,
    user_factory,
    redis_state,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id, user = await _seed_chat(db_session, user_factory)
    key = uuid.uuid4().hex
    monkeypatch.setattr(command_service.settings, "idempotency_hmac_secret", "old-key")
    original = await _send(chat_id, user, "rotation fixture", key)
    monkeypatch.setattr(command_service.settings, "idempotency_hmac_secret", "new-key")
    replay = await _send(chat_id, user, "", key)
    assert replay.id == original.id
    assert replay.content == "rotation fixture"
    assert await _snapshot(chat_id, user.id) == (1, 1, 1, 0)


async def test_committed_receipt_precedes_all_retry_payload_validation(
    db_session: AsyncSession,
    user_factory,
    redis_state,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id, user = await _seed_chat(db_session, user_factory)
    key = uuid.uuid4().hex
    original = await _send(chat_id, user, "valid original", key)
    monkeypatch.setattr(cache_module, "get_cache_client", _redis_unavailable)
    upload = UploadFile(
        file=BytesIO(b"ignored"),
        filename="ignored.txt",
        size=command_service.settings.chat_attachment_max_total_bytes + 1,
    )
    uploads = [upload] * (int(command_service.settings.chat_attachment_max_files) + 1)
    try:
        async with AsyncSession(database.engine, expire_on_commit=False) as session:
            await ChatRepository(session).set_message_rls_user(user.id)
            replay = await _dispatcher(session).send_message(
                chat_id,
                user,
                "x" * (command_service.settings.chat_max_message_length + 1),
                uploads,
                "en",
                idempotency_key=key,
                reply_to_message_id=uuid.uuid4(),
            )
    finally:
        await upload.close()
    assert replay.id == original.id
    assert replay.content == "valid original"
    assert replay.attachments == []
    assert await _snapshot(chat_id, user.id) == (1, 1, 1, 0)


async def test_expired_receipt_cache_cleanup_preserves_replacement_owner(
    db_session: AsyncSession,
    user_factory,
    redis_state,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id, user = await _seed_chat(db_session, user_factory)
    key = uuid.uuid4().hex
    await _send(chat_id, user, "old completed generation", key)
    await _expire_receipt(chat_id, user.id, key)
    cache, _clock = redis_state
    cache_key = command_service._make_idempotency_key(chat_id, user.id, key)
    replacement = json.dumps({"status": "pending", "owner": "current-owner"})
    real_get = cache.get
    replaced = False

    async def replace_after_read(name, *args, **kwargs):
        nonlocal replaced
        value = await real_get(name, *args, **kwargs)
        if name == cache_key and not replaced:
            replaced = True
            await cache.set(cache_key, replacement, ex=300)
        return value

    monkeypatch.setattr(cache, "get", replace_after_read)
    with pytest.raises(HTTPException) as caught:
        await _send(chat_id, user, "must not steal slot", key)
    assert caught.value.status_code == 409
    assert caught.value.headers["Retry-After"] == "1"
    assert await real_get(cache_key) == replacement
    assert await _snapshot(chat_id, user.id) == (1, 1, 1, 0)


@pytest.mark.parametrize("revocation", ["membership", "chat"])
async def test_unique_conflict_reauthorizes_after_real_rollback(
    db_session: AsyncSession,
    user_factory,
    redis_state,
    monkeypatch: pytest.MonkeyPatch,
    revocation: str,
) -> None:
    chat_id, user = await _seed_chat(db_session, user_factory)
    key = uuid.uuid4().hex
    cache, _clock = redis_state
    real_set = cache.set
    arrived = 0
    both_ready, release, winner_done = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )
    tasks: list[asyncio.Task] = []

    async def ineffective_set(name, value, *args, **kwargs):
        kwargs.pop("nx", None)
        return await real_set(name, value, *args, **kwargs)

    async def ineffective_compare(*_args, **_kwargs):
        return True

    monkeypatch.setattr(cache, "set", ineffective_set)
    monkeypatch.setattr(
        command_service, "_change_idempotency_slot", ineffective_compare
    )

    async def writer(label: str):
        nonlocal arrived
        async with AsyncSession(database.engine, expire_on_commit=False) as session:
            await ChatRepository(session).set_message_rls_user(user.id)
            sender = _dispatcher(session)
            real_create = sender.repository.create_message
            real_rollback = sender.uow.rollback

            async def rendezvous(message: Message):
                nonlocal arrived
                arrived += 1
                if arrived == 2:
                    both_ready.set()
                await asyncio.wait_for(release.wait(), timeout=_WAIT_SECONDS)
                return await real_create(message)

            async def rollback_then_revoke() -> None:
                await real_rollback()
                # Wait for successful response hydration before revoking rights;
                # otherwise this could turn into an unrelated winner read race.
                await asyncio.wait_for(winner_done.wait(), timeout=_WAIT_SECONDS)
                async with AsyncSession(database.engine) as revoker:
                    if revocation == "membership":
                        await revoker.execute(
                            delete(chat_participants).where(
                                chat_participants.c.chat_id == chat_id,
                                chat_participants.c.user_id == user.id,
                            )
                        )
                    else:
                        await revoker.execute(delete(Chat).where(Chat.id == chat_id))
                    await revoker.commit()
                monkeypatch.setattr(
                    cache_module, "get_cache_client", _redis_unavailable
                )

            monkeypatch.setattr(sender.repository, "create_message", rendezvous)
            monkeypatch.setattr(sender.uow, "rollback", rollback_then_revoke)
            try:
                result = await sender.send_message(
                    chat_id, user, label, [], "en", idempotency_key=key
                )
            except HTTPException:
                # Even a rejected loser must not leave a send event behind.
                await session.commit()
                raise
            winner_done.set()
            return result

    try:
        tasks = [asyncio.create_task(writer(label)) for label in ("one", "two")]
        await asyncio.wait_for(both_ready.wait(), timeout=_WAIT_SECONDS)
        release.set()
        outcomes = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=_WAIT_SECONDS
        )
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=_WAIT_SECONDS
            )

    failures = [result for result in outcomes if isinstance(result, BaseException)]
    successes = [result for result in outcomes if not isinstance(result, BaseException)]
    assert len(failures) == len(successes) == 1
    assert isinstance(failures[0], HTTPException)
    assert failures[0].status_code == (403 if revocation == "membership" else 404)
    if revocation == "membership":
        await db_session.execute(
            chat_participants.insert().values(chat_id=chat_id, user_id=user.id)
        )
        await db_session.commit()
        receipt = await _receipt(chat_id, user.id, key)
        assert receipt is not None and receipt.message_id == successes[0].id
        assert await _snapshot(chat_id, user.id) == (1, 1, 1, 0)
    else:
        assert await _snapshot(chat_id, user.id) == (0, 1, 0, 0)


@pytest.mark.parametrize(
    "prune_first_control",
    [False, True],
    ids=["unmodified-dispatcher-order", "test-owned-prune-first-control"],
)
async def test_concurrent_different_expired_keys_do_not_deadlock_during_cleanup(
    db_session: AsyncSession,
    user_factory,
    redis_state,
    monkeypatch: pytest.MonkeyPatch,
    prune_first_control: bool,
) -> None:
    """Compare dispatcher scheduling with an explicit test-owned negative control."""
    chat_id, user = await _seed_chat(db_session, user_factory)
    first_key, second_key = uuid.uuid4().hex, uuid.uuid4().hex
    first_original = await _send(chat_id, user, "first original", first_key)
    second_original = await _send(chat_id, user, "second original", second_key)
    await _expire_receipt(chat_id, user.id, first_key)
    await _expire_receipt(chat_id, user.id, second_key)
    assert await _snapshot(chat_id, user.id) == (2, 2, 2, 0)
    second_digest = command_service._make_send_receipt_digest(
        chat_id, user.id, second_key
    )

    first_at_claim, second_after_prune, release = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )
    tasks: list[asyncio.Task] = []
    real_calls = {
        first_key: {"claim": 0, "prune": 0},
        second_key: {"claim": 0, "prune": 0},
    }

    async def writer(key: str, *, is_first: bool):
        async with AsyncSession(database.engine, expire_on_commit=False) as session:
            await ChatRepository(session).set_message_rls_user(user.id)
            sender = _dispatcher(session)
            real_claim = sender.repository.create_send_receipt
            real_prune = sender.repository.prune_expired_send_receipts
            already_pruned: int | None = None
            control_scope: tuple[uuid.UUID, uuid.UUID] | None = None

            async def scheduled_claim(
                scope_chat: uuid.UUID,
                scope_user: uuid.UUID,
                key_digest: str,
                message_id: uuid.UUID,
            ):
                nonlocal already_pruned, control_scope
                if prune_first_control:
                    # Test-owned scheduling mutation, not copied production or
                    # replacement SQL: perform the same scoped real prune once,
                    # before the same real claim. Suppress its later duplicate.
                    control_scope = (scope_chat, scope_user)
                    real_calls[key]["prune"] += 1
                    already_pruned = await real_prune(scope_chat, scope_user)
                    if not is_first:
                        second_after_prune.set()
                        await asyncio.wait_for(release.wait(), timeout=_WAIT_SECONDS)
                if is_first:
                    # In the control this signal follows the real prune; in the
                    # unmodified case no cleanup SQL has run before this point.
                    first_at_claim.set()
                    await asyncio.wait_for(release.wait(), timeout=_WAIT_SECONDS)
                real_calls[key]["claim"] += 1
                return await real_claim(scope_chat, scope_user, key_digest, message_id)

            async def scheduled_prune(
                scope_chat: uuid.UUID,
                scope_user: uuid.UUID,
                *,
                limit: int = 100,
            ):
                if prune_first_control:
                    assert control_scope == (scope_chat, scope_user)
                    assert limit == 100
                    assert already_pruned is not None
                    return already_pruned
                real_calls[key]["prune"] += 1
                deleted = await real_prune(scope_chat, scope_user, limit=limit)
                if not is_first:
                    second_after_prune.set()
                    await asyncio.wait_for(release.wait(), timeout=_WAIT_SECONDS)
                return deleted

            monkeypatch.setattr(
                sender.repository, "create_send_receipt", scheduled_claim
            )
            monkeypatch.setattr(
                sender.repository, "prune_expired_send_receipts", scheduled_prune
            )
            content = (
                "replacement for second key"
                if is_first
                else "replacement for first key"
            )
            return await sender.send_message(
                chat_id,
                user,
                content,
                [],
                "en",
                idempotency_key=key,
            )

    async with AsyncSession(database.engine, expire_on_commit=False) as controller:
        await ChatRepository(controller).set_message_rls_user(user.id)
        locked = await controller.execute(
            select(ChatSendReceipt.id)
            .where(
                ChatSendReceipt.chat_id == chat_id,
                ChatSendReceipt.user_id == user.id,
                ChatSendReceipt.key_digest == second_digest,
            )
            .with_for_update()
        )
        assert locked.scalar_one() is not None
        try:
            # A requests key2. In the test-owned prune-first control, the
            # controller forces cleanup to take key1 and leave key2 untouched.
            tasks.append(asyncio.create_task(writer(second_key, is_first=True)))
            await asyncio.wait_for(first_at_claim.wait(), timeout=_WAIT_SECONDS)
            await controller.commit()

            # A stays paused before its exact-key claim. The test-owned
            # control makes B skip A-held key1 and take key2, forming a cycle.
            # The unmodified dispatcher claims key1 first; B can commit independently,
            # then A claims key2. Neither case replaces repository SQL.
            tasks.append(asyncio.create_task(writer(first_key, is_first=False)))
            await asyncio.wait_for(second_after_prune.wait(), timeout=_WAIT_SECONDS)
            release.set()
            outcomes = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=_WAIT_SECONDS,
            )
        finally:
            # Release the controller before awaiting cancelled writers even if
            # an assertion or barrier failed before the normal controller commit.
            await controller.rollback()
            release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=_WAIT_SECONDS,
                )

    persisted = await _snapshot(chat_id, user.id)
    failures = [result for result in outcomes if isinstance(result, BaseException)]
    successes = [result for result in outcomes if not isinstance(result, BaseException)]
    failure_kinds = [
        (
            type(error).__name__,
            getattr(getattr(error, "orig", None), "sqlstate", None),
        )
        for error in failures
    ]
    assert all(counts == {"claim": 1, "prune": 1} for counts in real_calls.values())
    async with AsyncSession(database.engine, expire_on_commit=False) as observer:
        await ChatRepository(observer).set_message_rls_user(user.id)
        original_rows = await observer.execute(
            select(Message.id, Message.content).where(
                Message.chat_id == chat_id,
                Message.id.in_([first_original.id, second_original.id]),
            )
        )
        assert dict(original_rows.all()) == {
            first_original.id: "first original",
            second_original.id: "second original",
        }

    first_receipt = await _receipt(chat_id, user.id, first_key)
    second_receipt = await _receipt(chat_id, user.id, second_key)
    if prune_first_control:
        # This establishes the regression test's sensitivity using actual
        # PostgreSQL deadlock detection. It is NOT observed old-production RED.
        assert len(failures) == len(successes) == 1, (
            f"Control outcomes={failure_kinds}; persisted={persisted}"
        )
        assert failure_kinds[0][1] == "40P01", failure_kinds
        assert persisted == (3, 3, 1, 0)
        survivor = successes[0]
        assert survivor.id not in {first_original.id, second_original.id}
        receipts = [
            receipt
            for receipt in (first_receipt, second_receipt)
            if receipt is not None
        ]
        assert len(receipts) == 1
        assert receipts[0].message_id == survivor.id
        assert receipts[0].expires_at > receipts[0].observed_at
        assert survivor.content == (
            "replacement for first key"
            if first_receipt is not None
            else "replacement for second key"
        )
        return

    assert not failures, (
        f"Different-key receipt reuse failed: {failure_kinds}; persisted={persisted}"
    )
    assert persisted == (4, 4, 2, 0)
    first_result, second_result = outcomes
    message_ids = {
        first_original.id,
        second_original.id,
        first_result.id,
        second_result.id,
    }
    assert len(message_ids) == 4
    assert first_result.content == "replacement for second key"
    assert second_result.content == "replacement for first key"
    assert first_receipt is not None and first_receipt.message_id == second_result.id
    assert second_receipt is not None and second_receipt.message_id == first_result.id
