from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import database
from app.core.events import AttachmentCleanupRequested, ChatDeleted
from app.models import Attachment, Chat, Message, User
from app.models.domain_events import StoredEvent
from app.repositories.chat_repository import ChatRepository
from app.repositories.unit_of_work import uow_from_session
from app.services.chat.attachment_service import ChatAttachmentService
from app.services.chat.command_service import (
    ChatMaintenanceService,
    ChatMessageDispatcher,
)
from app.services.event_handlers import handle_attachment_cleanup_requested
from app.services.storage import StaticFSStorage

_RUN = os.getenv("RUN_INTEGRATION_TESTS") == "1"
_TOTAL_MESSAGES = 32_768

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _RUN,
        reason="Set RUN_INTEGRATION_TESTS=1 to run owned PostgreSQL regressions",
    ),
]


def _require_postgres() -> None:
    if database.engine.dialect.name != "postgresql":
        pytest.fail("AUD-258 lock and page semantics require PostgreSQL")


async def _seed_chat(
    db_session: AsyncSession,
    users: list[User],
    *,
    message_count: int,
    attachment_count: int = 0,
    attachment_offset: int = 0,
) -> Chat:
    chat = Chat()
    chat.participants.extend(users)
    db_session.add(chat)
    await db_session.flush()

    sender = users[0]
    repository = ChatRepository(db_session)
    await repository.set_message_rls_user(sender.id)
    await db_session.execute(
        text(
            """
            INSERT INTO messages (
                id, chat_id, sender_id, content, created_at, read_status
            )
            SELECT gen_random_uuid(), :chat_id, :sender_id, 'AUD-258 fixture',
                   CAST(:base_time AS TIMESTAMPTZ) - (n * INTERVAL '1 microsecond'), false
            FROM generate_series(1, :message_count) AS series(n)
            """
        ),
        {
            "chat_id": chat.id,
            "sender_id": sender.id,
            "base_time": datetime.now(UTC),
            "message_count": message_count,
        },
    )
    if attachment_count:
        await db_session.execute(
            text(
                """
                WITH selected AS (
                    SELECT id,
                           row_number() OVER (ORDER BY created_at DESC, id DESC) AS n
                    FROM messages
                    WHERE chat_id = :chat_id
                )
                INSERT INTO attachments (
                    id, message_id, url, file_type, filename, size
                )
                SELECT gen_random_uuid(), id,
                       'https://objects.example.test/aud258/' || n,
                       'file', 'fixture.txt', 1
                FROM selected
                WHERE n > :attachment_offset
                  AND n <= :attachment_offset + :attachment_count
                """
            ),
            {
                "chat_id": chat.id,
                "attachment_count": attachment_count,
                "attachment_offset": attachment_offset,
            },
        )
    await db_session.commit()
    return chat


def _patch_post_commit_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.chat.command_service.invalidate_chat_participants_cache",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.chat.command_service.invalidate_presence_audience_cache",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.ws_hub_client.invalidate_ws_hub_cache", AsyncMock()
    )


@pytest.mark.parametrize("operation", ["clear_history", "delete_chat"])
async def test_maintenance_processes_history_larger_than_bind_limit_in_pages(
    operation: str,
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_postgres()
    admin = await user_factory(role="admin")
    peer = await user_factory()
    chat = await _seed_chat(
        db_session,
        [admin, peer],
        message_count=_TOTAL_MESSAGES,
        attachment_count=130,
    )

    service = ChatMaintenanceService(
        uow_from_session(db_session), ChatAttachmentService()
    )
    page_sizes: list[int] = []
    delete_batch_sizes: list[int] = []
    original_get_messages = service.repository.get_messages
    original_delete_messages = service.repository.delete_messages

    async def observe_pages(*args, **kwargs):
        messages, has_more, cursor = await original_get_messages(*args, **kwargs)
        page_sizes.append(len(messages))
        assert kwargs["for_update"] is True
        return messages, has_more, cursor

    async def observe_deletes(message_ids, **kwargs):
        delete_batch_sizes.append(len(message_ids))
        return await original_delete_messages(message_ids, **kwargs)

    monkeypatch.setattr(service.repository, "get_messages", observe_pages)
    monkeypatch.setattr(service.repository, "delete_messages", observe_deletes)
    _patch_post_commit_effects(monkeypatch)

    result = await getattr(service, operation)(chat.id, admin, "en")

    assert result.deleted_messages == _TOTAL_MESSAGES
    assert result.deleted_attachments == 130
    assert page_sizes
    assert sum(page_sizes) == _TOTAL_MESSAGES
    assert max(page_sizes) <= ChatMaintenanceService._MESSAGE_PAGE_SIZE
    if operation == "clear_history":
        assert delete_batch_sizes
        assert sum(delete_batch_sizes) == _TOTAL_MESSAGES
        assert max(delete_batch_sizes) <= ChatMaintenanceService._MESSAGE_PAGE_SIZE

    await ChatRepository(db_session).set_message_rls_user(admin.id)
    remaining_messages = await db_session.scalar(
        select(func.count()).select_from(Message).where(Message.chat_id == chat.id)
    )
    remaining_attachments = await db_session.scalar(
        select(func.count())
        .select_from(Attachment)
        .join(Message, Attachment.message_id == Message.id)
        .where(Message.chat_id == chat.id)
    )
    assert remaining_messages == 0
    assert remaining_attachments == 0
    remaining_chat_count = await db_session.scalar(
        select(func.count()).select_from(Chat).where(Chat.id == chat.id)
    )
    assert remaining_chat_count == (1 if operation == "clear_history" else 0)

    cleanup_rows = list(
        (
            await db_session.scalars(
                select(StoredEvent).where(
                    StoredEvent.event_type == AttachmentCleanupRequested.EVENT_TYPE,
                    StoredEvent.aggregate_type == "Chat",
                    StoredEvent.aggregate_id == str(chat.id),
                )
            )
        ).all()
    )
    cleanup_urls = [
        url for event in cleanup_rows for url in event.payload["attachment_urls"]
    ]
    assert len(cleanup_urls) == 130
    assert max(len(event.payload["attachment_urls"]) for event in cleanup_rows) <= 128
    if operation == "delete_chat":
        deleted_events = list(
            (
                await db_session.scalars(
                    select(StoredEvent).where(
                        StoredEvent.event_type == ChatDeleted.EVENT_TYPE,
                        StoredEvent.aggregate_id == str(chat.id),
                    )
                )
            ).all()
        )
        assert {row.payload["participant_id"] for row in deleted_events} == {
            str(admin.id),
            str(peer.id),
        }


async def _assert_blocked_by(
    session_factory: async_sessionmaker[AsyncSession],
    application_name: str,
    expected_blocker_pid: int,
) -> bool:
    deadline = time.monotonic() + 5
    async with session_factory() as observer:
        while time.monotonic() < deadline:
            blockers = await observer.scalar(
                text(
                    """
                    SELECT pg_blocking_pids(pid)
                    FROM pg_stat_activity
                    WHERE application_name = :application_name
                    """
                ),
                {"application_name": application_name},
            )
            if blockers and expected_blocker_pid in blockers:
                return True
            await asyncio.sleep(0.01)  # bounded by the five-second lock deadline
    return False


@pytest.mark.parametrize("operation", ["clear_history", "delete_chat"])
async def test_attachment_fk_insert_waits_for_maintenance_page_lock(
    operation: str,
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _require_postgres()
    admin = await user_factory(role="admin")
    chat = await _seed_chat(db_session, [admin], message_count=1)
    await ChatRepository(db_session).set_message_rls_user(admin.id)
    message = Message(
        chat_id=chat.id,
        sender_id=admin.id,
        content="locked target",
    )
    db_session.add(message)
    await db_session.flush()

    storage = StaticFSStorage(tmp_path, base_url="https://objects.example.test")
    existing_url = await storage.save_file(
        f"chat/{uuid.uuid4().hex}/existing.txt", b"existing"
    )
    racing_url = await storage.save_file(
        f"chat/{uuid.uuid4().hex}/racing.txt", b"racing"
    )
    db_session.add(
        Attachment(
            message_id=message.id,
            url=existing_url,
            file_type="file",
            filename="existing.txt",
            size=8,
        )
    )
    await db_session.commit()

    service = ChatMaintenanceService(
        uow_from_session(db_session), ChatAttachmentService()
    )
    _patch_post_commit_effects(monkeypatch)
    page_loaded = asyncio.Event()
    release_maintenance = asyncio.Event()
    maintenance_pid: int | None = None
    original_get_messages = service.repository.get_messages

    async def pause_after_locked_page(*args, **kwargs):
        nonlocal maintenance_pid
        result = await original_get_messages(*args, **kwargs)
        maintenance_pid = await db_session.scalar(text("SELECT pg_backend_pid()"))
        page_loaded.set()
        await release_maintenance.wait()
        return result

    monkeypatch.setattr(service.repository, "get_messages", pause_after_locked_page)
    maintenance_task = asyncio.create_task(
        getattr(service, operation)(chat.id, admin, "en")
    )
    writer_pid_future: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    application_name = f"aud258-{uuid.uuid4().hex[:24]}"
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def insert_late_attachment() -> None:
        async with session_factory() as writer:
            await writer.execute(
                text("SELECT set_config('application_name', :name, false)"),
                {"name": application_name},
            )
            writer_pid_future.set_result(
                await writer.scalar(text("SELECT pg_backend_pid()"))
            )
            await writer.execute(
                text(
                    """
                    INSERT INTO attachments (
                        id, message_id, url, file_type, filename, size
                    ) VALUES (gen_random_uuid(), :message_id, :url, 'file',
                              'racing.txt', 6)
                    """
                ),
                {"message_id": message.id, "url": racing_url},
            )
            await writer.commit()

    writer_task: asyncio.Task[None] | None = None
    was_blocked = False
    try:
        await asyncio.wait_for(page_loaded.wait(), timeout=10)
        writer_task = asyncio.create_task(insert_late_attachment())
        await asyncio.wait_for(writer_pid_future, timeout=5)
        assert maintenance_pid is not None
        was_blocked = await _assert_blocked_by(
            session_factory, application_name, maintenance_pid
        )
    finally:
        release_maintenance.set()
        await asyncio.wait_for(maintenance_task, timeout=20)

    assert was_blocked, "the attachment FK insert must wait on the locked message"
    assert writer_task is not None
    with pytest.raises(IntegrityError):
        await writer_task

    event_row = await db_session.scalar(
        select(StoredEvent).where(
            StoredEvent.event_type == AttachmentCleanupRequested.EVENT_TYPE,
            StoredEvent.aggregate_id == str(chat.id),
        )
    )
    assert event_row is not None
    assert event_row.payload["attachment_urls"] == [existing_url]
    assert not (
        await db_session.scalars(select(Attachment).where(Attachment.url == racing_url))
    ).all()

    monkeypatch.setattr("app.utils.files._get_storage_backend", lambda: storage)
    await handle_attachment_cleanup_requested(
        AttachmentCleanupRequested(chat_id=chat.id, attachment_urls=[existing_url])
    )
    assert not await storage.exists(existing_url)

    dispatcher = ChatMessageDispatcher(
        uow_from_session(db_session), ChatAttachmentService(), AsyncMock()
    )
    await dispatcher._cleanup_unreferenced_uploaded_files([racing_url])
    assert not await storage.exists(racing_url)


@pytest.mark.parametrize("operation", ["clear_history", "delete_chat"])
async def test_participant_removal_waits_for_locked_snapshot_across_pages(
    operation: str,
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_postgres()
    admin = await user_factory(role="admin")
    participants = sorted(
        [await user_factory(), await user_factory()], key=lambda item: item.id.int
    )
    chat = await _seed_chat(
        db_session,
        participants,
        message_count=600,
        attachment_count=1,
        attachment_offset=ChatMaintenanceService._MESSAGE_PAGE_SIZE,
    )
    removed_participant = participants[0]
    remaining_participant = participants[1]
    later_page_attachment_url = (
        "https://objects.example.test/aud258/"
        f"{ChatMaintenanceService._MESSAGE_PAGE_SIZE + 1}"
    )

    service = ChatMaintenanceService(
        uow_from_session(db_session), ChatAttachmentService()
    )
    _patch_post_commit_effects(monkeypatch)
    first_page_loaded = asyncio.Event()
    release_maintenance = asyncio.Event()
    maintenance_pid: int | None = None
    page_number = 0
    original_get_messages = service.repository.get_messages

    async def pause_after_first_locked_page(*args, **kwargs):
        nonlocal maintenance_pid, page_number
        result = await original_get_messages(*args, **kwargs)
        page_number += 1
        if page_number == 1:
            maintenance_pid = await db_session.scalar(text("SELECT pg_backend_pid()"))
            first_page_loaded.set()
            await release_maintenance.wait()
        return result

    monkeypatch.setattr(
        service.repository, "get_messages", pause_after_first_locked_page
    )
    maintenance_task = asyncio.create_task(
        getattr(service, operation)(chat.id, admin, "en")
    )
    remover_pid_future: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    remover_rowcount_future: asyncio.Future[int] = (
        asyncio.get_running_loop().create_future()
    )
    application_name = f"aud258-{uuid.uuid4().hex[:24]}"
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def remove_participant() -> None:
        async with session_factory() as remover:
            await remover.execute(
                text("SELECT set_config('application_name', :name, false)"),
                {"name": application_name},
            )
            remover_pid_future.set_result(
                await remover.scalar(text("SELECT pg_backend_pid()"))
            )
            result = await remover.execute(
                text(
                    """
                    DELETE FROM chat_participants
                    WHERE chat_id = :chat_id AND user_id = :user_id
                    """
                ),
                {"chat_id": chat.id, "user_id": removed_participant.id},
            )
            await remover.commit()
            remover_rowcount_future.set_result(result.rowcount or 0)

    remover_task: asyncio.Task[None] | None = None
    was_blocked = False
    try:
        await asyncio.wait_for(first_page_loaded.wait(), timeout=10)
        remover_task = asyncio.create_task(remove_participant())
        await asyncio.wait_for(remover_pid_future, timeout=5)
        assert maintenance_pid is not None
        was_blocked = await _assert_blocked_by(
            session_factory, application_name, maintenance_pid
        )
    finally:
        release_maintenance.set()
        await asyncio.wait_for(maintenance_task, timeout=30)
        if remover_task is not None:
            await asyncio.wait_for(remover_task, timeout=10)

    assert was_blocked, "membership removal must wait for the locked roster snapshot"
    removal_rowcount = await asyncio.wait_for(remover_rowcount_future, timeout=1)
    assert removal_rowcount == (1 if operation == "clear_history" else 0)
    result = maintenance_task.result()
    assert result.deleted_messages == 600
    assert result.deleted_attachments == 1
    assert page_number == 2

    cleanup_rows = list(
        (
            await db_session.scalars(
                select(StoredEvent).where(
                    StoredEvent.event_type == AttachmentCleanupRequested.EVENT_TYPE,
                    StoredEvent.aggregate_id == str(chat.id),
                )
            )
        ).all()
    )
    cleanup_urls = [
        url for event in cleanup_rows for url in event.payload["attachment_urls"]
    ]
    assert cleanup_urls == [later_page_attachment_url]

    if operation == "delete_chat":
        deleted_events = list(
            (
                await db_session.scalars(
                    select(StoredEvent).where(
                        StoredEvent.event_type == ChatDeleted.EVENT_TYPE,
                        StoredEvent.aggregate_id == str(chat.id),
                    )
                )
            ).all()
        )
        assert {row.payload["participant_id"] for row in deleted_events} == {
            str(participant.id) for participant in participants
        }
    else:
        await ChatRepository(db_session).set_message_rls_user(remaining_participant.id)
        remaining_messages = await db_session.scalar(
            select(func.count()).select_from(Message).where(Message.chat_id == chat.id)
        )
        remaining_attachments = await db_session.scalar(
            select(func.count())
            .select_from(Attachment)
            .join(Message, Attachment.message_id == Message.id)
            .where(Message.chat_id == chat.id)
        )
        assert remaining_messages == 0
        assert remaining_attachments == 0


@pytest.mark.parametrize("operation", ["clear_history", "delete_chat"])
async def test_empty_participant_chat_fails_closed_without_cascading_blobs(
    operation: str,
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    tmp_path: Path,
) -> None:
    _require_postgres()
    admin = await user_factory(role="admin")
    former_participant = await user_factory()
    chat = await _seed_chat(
        db_session,
        [former_participant],
        message_count=1,
        attachment_count=1,
    )
    # Keep identifiers independent of deliberate ORM expiration and rollback.
    chat_id = chat.id
    former_participant_id = former_participant.id
    storage = StaticFSStorage(tmp_path, base_url="https://objects.example.test")
    attachment_url = await storage.save_file(
        f"chat/{uuid.uuid4().hex}/orphan.txt", b"orphan blob"
    )
    await db_session.execute(
        update(Attachment)
        .where(Attachment.url == "https://objects.example.test/aud258/1")
        .values(url=attachment_url)
    )
    await db_session.execute(
        text(
            "DELETE FROM chat_participants "
            "WHERE chat_id = :chat_id AND user_id = :user_id"
        ),
        {"chat_id": chat_id, "user_id": former_participant_id},
    )
    await db_session.commit()
    db_session.expire_all()

    # The policy correctly hides old messages from a former member. Maintenance
    # must therefore refuse an orphaned chat instead of treating it as empty.
    await ChatRepository(db_session).set_message_rls_user(former_participant_id)
    invisible_message_count = await db_session.scalar(
        select(func.count()).select_from(Message).where(Message.chat_id == chat_id)
    )
    assert invisible_message_count == 0
    await db_session.rollback()
    # Rollback expires the actor too; load its columns before synchronous checks.
    await db_session.refresh(admin)

    service = ChatMaintenanceService(
        uow_from_session(db_session), ChatAttachmentService()
    )
    with pytest.raises(HTTPException) as denied:
        await getattr(service, operation)(chat_id, admin, "en")
    assert denied.value.status_code == 403
    assert await storage.exists(attachment_url)
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Chat).where(Chat.id == chat_id)
        )
        == 1
    )
    assert not (
        await db_session.scalars(
            select(StoredEvent).where(
                StoredEvent.aggregate_id == str(chat_id),
                StoredEvent.event_type.in_(
                    [AttachmentCleanupRequested.EVENT_TYPE, ChatDeleted.EVENT_TYPE]
                ),
            )
        )
    ).all()

    # Restore membership only for verification; the rejected maintenance request
    # must leave both the invisible database rows and their blob reference intact.
    await db_session.execute(
        text(
            "INSERT INTO chat_participants (chat_id, user_id) "
            "VALUES (:chat_id, :user_id)"
        ),
        {"chat_id": chat_id, "user_id": former_participant_id},
    )
    await db_session.commit()
    await ChatRepository(db_session).set_message_rls_user(former_participant_id)
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
            .where(Attachment.url == attachment_url)
        )
        == 1
    )


async def test_send_timestamp_update_does_not_deadlock_with_maintenance_chat_lock(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """Probe the send FK-lock → timestamp UPDATE interleaving against clear.

    Transactions use a 10-second local lock timeout, beyond the 5-second
    observer window, so the test can see a real wait before either lock expires.
    """
    _require_postgres()
    admin = await user_factory(role="admin")
    chat = await _seed_chat(db_session, [admin], message_count=0)
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    sender_application_name = f"aud258-sender-{uuid.uuid4().hex[:16]}"
    maintenance_application_name = f"aud258-maint-{uuid.uuid4().hex[:16]}"
    sender_pid_future: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    maintenance_pid_future: asyncio.Future[int] = (
        asyncio.get_running_loop().create_future()
    )
    sender_inserted = asyncio.Event()
    allow_sender_timestamp_update = asyncio.Event()

    async def send_message_transaction() -> Exception | None:
        try:
            async with session_factory() as sender:
                await sender.execute(
                    text("SELECT set_config('application_name', :name, false)"),
                    {"name": sender_application_name},
                )
                await sender.execute(
                    text("SELECT set_config('lock_timeout', '10s', true)")
                )
                repository = ChatRepository(sender)
                await repository.set_message_rls_user(admin.id)
                message = Message(
                    chat_id=chat.id,
                    sender_id=admin.id,
                    content="AUD-258 lock-order probe",
                )
                await repository.create_message(message)
                sender_pid_future.set_result(
                    await sender.scalar(text("SELECT pg_backend_pid()"))
                )
                sender_inserted.set()
                await allow_sender_timestamp_update.wait()
                await repository.update_timestamp_by_id(chat.id, datetime.now(UTC))
                await sender.commit()
        except Exception as exc:
            return exc
        return None

    async def clear_chat_history() -> object:
        async with session_factory() as maintenance_session:
            await maintenance_session.execute(
                text("SELECT set_config('application_name', :name, false)"),
                {"name": maintenance_application_name},
            )
            await maintenance_session.execute(
                text("SELECT set_config('lock_timeout', '10s', true)")
            )
            maintenance_pid_future.set_result(
                await maintenance_session.scalar(text("SELECT pg_backend_pid()"))
            )
            service = ChatMaintenanceService(
                uow_from_session(maintenance_session), ChatAttachmentService()
            )
            return await service.clear_history(chat.id, admin, "en")

    sender_task = asyncio.create_task(send_message_transaction())
    maintenance_task: asyncio.Task[object] | None = None
    was_blocked = False
    try:
        await asyncio.wait_for(sender_inserted.wait(), timeout=5)
        maintenance_task = asyncio.create_task(clear_chat_history())
        sender_pid = await asyncio.wait_for(sender_pid_future, timeout=5)
        await asyncio.wait_for(maintenance_pid_future, timeout=5)
        was_blocked = await _assert_blocked_by(
            session_factory, maintenance_application_name, sender_pid
        )
    finally:
        allow_sender_timestamp_update.set()
        if maintenance_task is not None:
            await asyncio.gather(sender_task, maintenance_task, return_exceptions=True)
        else:
            await asyncio.gather(sender_task, return_exceptions=True)

    sender_error = sender_task.result()
    assert was_blocked, "maintenance must wait for the pending sender Chat FK lock"
    assert sender_error is None, f"sender transaction failed: {sender_error!r}"
    assert maintenance_task is not None
    assert not isinstance(maintenance_task.result(), BaseException)
    maintenance_result = maintenance_task.result()
    assert maintenance_result.deleted_messages == 1
