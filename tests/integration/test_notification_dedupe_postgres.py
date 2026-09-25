"""Concurrent notification deduplication against separate PostgreSQL sessions."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

import app.core.database as database
import app.services.chat.notification_service as chat_notifications
import app.services.notifications.schedule_changes as schedule_changes
import app.services.notifications.system_release as system_release
from app.models import Group, Notification, PushSubscription

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if database.engine.dialect.name != "postgresql":
        # SQLite unit shards cannot exercise PG advisory locks.
        # QUALITY-2509 @egorribun: required PostgreSQL lane runs this file.
        pytest.skip("notification concurrency requires separate PostgreSQL sessions")


def _synchronize_reads(
    read: Callable[..., Awaitable[set[uuid.UUID]]],
) -> Callable[..., Awaitable[set[uuid.UUID]]]:
    """Let both calls observe the pre-insert state if neither holds a key lock."""
    both_read = asyncio.Event()
    calls = 0

    async def synchronized(*args: object) -> set[uuid.UUID]:
        nonlocal calls
        result = await read(*args)
        calls += 1
        if calls == 2:
            both_read.set()
        try:
            await asyncio.wait_for(both_read.wait(), timeout=0.5)
        except TimeoutError:
            # A correct transaction lock prevents the second read until commit.
            pass
        return result

    return synchronized


async def _notification_count(dedupe_prefix: str) -> int:
    async with database.async_session() as session:
        result = await session.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.dedupe_key.like(f"{dedupe_prefix}%"))
        )
        return int(result.scalar_one())


async def test_concurrent_release_creates_one_notification(user_factory) -> None:
    _require_postgres()
    user = await user_factory()
    async with database.async_session() as session:
        session.add(
            PushSubscription(
                user_id=user.id,
                endpoint="https://push.example.test/release",
                p256dh="key",
                auth="auth",
                topics=["system.release"],
            )
        )
        await session.commit()
    version = "713.0.0"
    key = system_release.release_dedupe_key(version)
    read = system_release._already_notified

    async def announce() -> int:
        async with database.async_session() as session:
            result = await system_release.announce_release(session, version=version)
            await session.commit()
            return result.created

    with (
        patch.object(system_release, "_already_notified", _synchronize_reads(read)),
        patch(
            "app.services.notifications.delivery._is_push_configured", return_value=True
        ),
        patch(
            "app.services.notifications.delivery.send_web_push",
            side_effect=AssertionError("push dispatched before commit"),
        ) as send,
    ):
        created = await asyncio.gather(announce(), announce())

    assert sorted(created) == [0, 1]
    send.assert_not_called()
    assert await _notification_count(key) == 1


async def test_concurrent_schedule_change_creates_one_notification(
    db_session, user_factory
) -> None:
    _require_postgres()
    group = Group(name=f"DEDUPE-{uuid.uuid4().hex[:8]}")
    db_session.add(group)
    await db_session.commit()
    user = await user_factory(group_id=group.id)
    db_session.add(
        PushSubscription(
            user_id=user.id,
            endpoint="https://push.example.test/schedule",
            p256dh="key",
            auth="auth",
            topics=["schedule.changed"],
        )
    )
    await db_session.commit()
    schedule_id = uuid.uuid4()
    previous = {"group_id": str(group.id), "room": "101"}
    current = {"group_id": str(group.id), "room": "202"}
    read = schedule_changes._already_notified

    async def announce() -> int:
        async with database.async_session() as session:
            result = await schedule_changes.notify_about_schedule_change(
                session,
                schedule_id=schedule_id,
                previous=previous,
                current=current,
            )
            await session.commit()
            return result

    with (
        patch.object(schedule_changes, "_already_notified", _synchronize_reads(read)),
        patch(
            "app.services.notifications.delivery._is_push_configured", return_value=True
        ),
        patch(
            "app.services.notifications.delivery.send_web_push",
            side_effect=AssertionError("push dispatched before commit"),
        ) as send,
    ):
        created = await asyncio.gather(announce(), announce())

    assert sorted(created) == [0, 1]
    send.assert_not_called()
    assert await _notification_count(f"schedule-change:{schedule_id}:") == 1


async def test_concurrent_chat_event_creates_one_notification_per_recipient(
    user_factory,
) -> None:
    """Separate outbox workers must serialize a replayed message before insert."""
    _require_postgres()
    sender = await user_factory()
    recipient = await user_factory()
    message = SimpleNamespace(
        id=uuid.uuid4(),
        chat_id=uuid.uuid4(),
        sender_id=sender.id,
        content="hello",
        attachments=[],
    )
    sender_dto = SimpleNamespace(
        id=sender.id, profile=SimpleNamespace(full_name="Sender")
    )
    recipient_dto = SimpleNamespace(id=recipient.id, profile=None)
    key = f"chat-message:{message.id}"
    read = chat_notifications._already_notified
    both_read = asyncio.Event()
    read_calls = 0

    async def synchronized_read(session, keys):
        nonlocal read_calls
        result = await read(session, keys)
        read_calls += 1
        if read_calls == 2:
            both_read.set()
        try:
            await asyncio.wait_for(both_read.wait(), timeout=0.5)
        except TimeoutError:
            # With the advisory lock, the second worker cannot read until the
            # first commits. Without it, both see an empty set and race.
            pass
        return result

    async def announce() -> None:
        async with database.async_session() as session:
            service = chat_notifications.ChatNotificationService(session)
            await service.notify_new_message(
                message, [sender_dto, recipient_dto], sender_dto
            )
            await session.commit()

    with (
        patch.object(chat_notifications, "_already_notified", synchronized_read),
        patch.object(
            chat_notifications, "build_presence_map", new=AsyncMock(return_value={})
        ),
        patch.object(chat_notifications, "serialize_message", return_value={}),
        patch.object(
            chat_notifications.ws_manager, "broadcast_to_chat", new=AsyncMock()
        ),
    ):
        await asyncio.gather(announce(), announce())

    assert read_calls == 2
    assert await _notification_count(key) == 1
