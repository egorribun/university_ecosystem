"""Dedupe-lock, outbox deferral and CDC configuration contracts."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.workers.cdc_outbox as cdc
from app.services.chat import notification_service
from app.services.notifications import dedupe, schedule_changes, system_release
from app.services.notifications.system_release import release_dedupe_key
from tests.test_schedule_change_notifications import _group, _state

# ---------------------------------------------------------------------------
# lock_notification_dedupe
# ---------------------------------------------------------------------------


def _db(dialect: str) -> MagicMock:
    db = MagicMock()
    db.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name=dialect))
    db.execute = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_postgres_lock_uses_the_shared_notification_namespace() -> None:
    db = _db("postgresql")

    await dedupe.lock_notification_dedupe(db, "chat-message:1")

    statement, params = db.execute.await_args.args
    assert str(statement) == (
        "SELECT pg_advisory_xact_lock("
        "hashtext('notification-dedupe'), hashtext(:dedupe_key))"
    )
    assert params == {"dedupe_key": "chat-message:1"}


@pytest.mark.asyncio
async def test_other_dialects_skip_the_advisory_lock() -> None:
    db = _db("sqlite")

    await dedupe.lock_notification_dedupe(db, "chat-message:1")

    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_release_announcements_lock_their_release_key(db_session) -> None:
    lock = AsyncMock()
    with patch.object(system_release, "lock_notification_dedupe", lock):
        await system_release.announce_release(db_session, version="7.1.0")

    lock.assert_awaited_once_with(db_session, release_dedupe_key("7.1.0"))


@pytest.mark.asyncio
async def test_schedule_changes_lock_their_change_key(db_session, user_factory) -> None:
    group = await _group(db_session, "LOCK-KEY")
    await user_factory(group_id=group.id)
    schedule_id = uuid.uuid4()
    lock = AsyncMock()

    with (
        patch.object(schedule_changes, "lock_notification_dedupe", lock),
        patch(
            "app.services.notifications.delivery._is_push_configured",
            return_value=False,
        ),
    ):
        await schedule_changes.notify_about_schedule_change(
            db_session,
            schedule_id=schedule_id,
            previous=_state(group.id),
            current=_state(group.id, room="303"),
        )

    session, key = lock.await_args.args
    assert session is db_session
    assert key.startswith(f"schedule-change:{schedule_id}:")


class _StopAfterLock(Exception):
    pass


@pytest.mark.asyncio
async def test_chat_messages_lock_their_generic_message_key() -> None:
    session = MagicMock()
    service = notification_service.ChatNotificationService.__new__(
        notification_service.ChatNotificationService
    )
    service.session = session
    message = SimpleNamespace(
        id=uuid.uuid4(), chat_id=uuid.uuid4(), sender_id=uuid.uuid4()
    )
    sender = SimpleNamespace(id=message.sender_id)
    recipient = SimpleNamespace(id=uuid.uuid4())
    lock = AsyncMock()

    with (
        patch.object(
            notification_service, "build_presence_map", AsyncMock(return_value={})
        ),
        patch.object(notification_service, "serialize_message", return_value={}),
        patch.object(notification_service, "ws_manager") as ws,
        patch.object(notification_service, "lock_notification_dedupe", lock),
        patch.object(
            notification_service,
            "_already_notified",
            AsyncMock(side_effect=_StopAfterLock),
        ),
        pytest.raises(_StopAfterLock),
    ):
        ws.broadcast_to_chat = AsyncMock()
        await service.notify_new_message(message, [sender, recipient], sender)

    lock.assert_awaited_once_with(session, f"chat-message:{message.id}")


# ---------------------------------------------------------------------------
# CDC configuration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"slot_name": "Bad-Slot"},
            "slot_name must be a lowercase PostgreSQL identifier",
        ),
        (
            {"publication_name": "Bad Pub"},
            "publication_name must be a lowercase PostgreSQL identifier",
        ),
    ],
)
def test_cdc_rejects_non_identifier_names_exactly(kwargs, message: str) -> None:
    with pytest.raises(ValueError) as error:
        cdc.CdcOutboxWorker(nats_broker=AsyncMock(), **kwargs)

    assert str(error.value) == message


@pytest.mark.asyncio
async def test_cdc_logs_the_publication_it_provisions() -> None:
    worker = cdc.CdcOutboxWorker(nats_broker=AsyncMock(), publication_name="ue_pub")
    conn = MagicMock()
    conn.fetchval = AsyncMock(side_effect=[None, 1])
    conn.execute = AsyncMock()

    with patch.object(cdc, "logger") as logger:
        await worker.provision_replication_resources(conn)

    logger.info.assert_any_call("Provisioned replication publication '%s'", "ue_pub")
