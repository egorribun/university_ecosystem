"""Focused regressions for current backend P2 count, cleanup, and pagination gaps."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, Notification, NotificationDelivery
from app.models.chat import Message
from app.repositories.chat_repository import ChatRepository
from app.repositories.event_repository import EventRepository
from app.services.event_service import EventService
from app.services.notifications.cleanup import cleanup_stale_notifications
from app.utils.pagination import decode_datetime_cursor


@pytest.mark.asyncio
async def test_event_total_matches_the_requested_type_filter(
    db_session: AsyncSession, user_factory
) -> None:
    owner = await user_factory()
    now = datetime.now(UTC)
    selected_type = f"contract-{uuid4()}"
    selected_location = f"hall-{uuid4()}"
    matching = Event(
        title="Matching event",
        event_type="lecture",
        event_type_en=selected_type,
        location="South Hall",
        location_en=selected_location,
        starts_at=now + timedelta(hours=1),
        ends_at=now + timedelta(hours=2),
        created_by=owner.id,
        is_active=True,
    )
    wrong_type = Event(
        title="Wrong type",
        event_type=f"other-{uuid4()}",
        location_en=selected_location,
        starts_at=now + timedelta(hours=1),
        ends_at=now + timedelta(hours=2),
        created_by=owner.id,
        is_active=True,
    )
    wrong_location = Event(
        title="Wrong location",
        event_type_en=selected_type,
        location_en=f"other-{uuid4()}",
        starts_at=now + timedelta(hours=1),
        ends_at=now + timedelta(hours=2),
        created_by=owner.id,
        is_active=True,
    )
    ended = Event(
        title="Ended event",
        event_type_en=selected_type,
        location_en=selected_location,
        starts_at=now - timedelta(hours=3),
        ends_at=now - timedelta(hours=1),
        created_by=owner.id,
        is_active=True,
    )
    db_session.add_all([matching, wrong_type, wrong_location, ended])
    await db_session.flush()

    service = EventService(
        SimpleNamespace(events=EventRepository(db_session)), AsyncMock()
    )
    page = await service.get_events(
        type=selected_type,
        location=selected_location,
        is_active=True,
        locale="en",
    )

    assert [item.id for item in page.items] == [matching.id]
    assert page.total == 1


@pytest.mark.asyncio
async def test_notification_retention_binds_uuid_ids_and_preserves_unread(
    db_session: AsyncSession,
    user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await user_factory()
    now = datetime(2026, 10, 16, tzinfo=UTC)
    cutoff = now - timedelta(days=30)
    old_created_at = cutoff - timedelta(days=1)

    read_notification = Notification(
        user_id=owner.id,
        title="Read notification beyond retention",
        created_at=old_created_at,
        read=True,
    )
    unread_notification = Notification(
        user_id=owner.id,
        title="Unread notification beyond retention",
        created_at=old_created_at - timedelta(seconds=1),
        read=False,
        read_at=None,
    )
    db_session.add_all([read_notification, unread_notification])
    await db_session.flush()

    old_attempt = cutoff - timedelta(hours=1)
    db_session.add_all(
        [
            NotificationDelivery(
                notification_id=read_notification.id,
                notification_created_at=read_notification.created_at,
                attempted_at=old_attempt,
                channel="inapp",
                status="delivered",
            ),
            NotificationDelivery(
                notification_id=unread_notification.id,
                notification_created_at=unread_notification.created_at,
                attempted_at=old_attempt - timedelta(seconds=1),
                channel="inapp",
                status="delivered",
            ),
        ]
    )
    await db_session.flush()

    monkeypatch.setattr(
        "app.services.notifications.cleanup.settings",
        MagicMock(notifications_retention_batch_size=10),
    )

    counts = await cleanup_stale_notifications(
        db=db_session, retention_days=30, now=now
    )

    assert counts == (1, 2)
    retained_notifications = list(
        (await db_session.scalars(select(Notification))).all()
    )
    retained_deliveries = list(
        (await db_session.scalars(select(NotificationDelivery))).all()
    )
    assert [notification.id for notification in retained_notifications] == [
        unread_notification.id
    ]
    assert retained_notifications[0].read is False
    assert retained_notifications[0].read_at is None
    assert retained_deliveries == []


@pytest.mark.asyncio
async def test_chat_list_cursor_uses_the_same_ordering_key_as_the_page(
    db_session: AsyncSession,
    user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await user_factory()
    first_peer = await user_factory()
    second_peer = await user_factory()
    repository = ChatRepository(db_session)
    first_chat = await repository.create_chat([owner, first_peer])
    second_chat = await repository.create_chat([owner, second_peer])

    first_message_at = datetime.now(UTC) - timedelta(minutes=10)
    second_message_at = first_message_at - timedelta(hours=1)
    db_session.add_all(
        [
            Message(
                chat_id=first_chat.id,
                sender_id=first_peer.id,
                content="recent message",
                created_at=first_message_at,
            ),
            Message(
                chat_id=second_chat.id,
                sender_id=second_peer.id,
                content="older message",
                created_at=second_message_at,
            ),
        ]
    )
    await db_session.flush()

    # Sending advances the first chat's cursor timestamp; a rename advances the
    # second chat without changing its older last-message ordering timestamp.
    await repository.update_timestamp_by_id(first_chat.id, first_message_at)
    await repository.rename_chat(second_chat.id, "Renamed project pair")
    await db_session.commit()

    # The production PostgreSQL UUID binder accepts the decoder's string ID;
    # SQLite's UUID binder does not. Keep the real cursor timestamp and predicate,
    # adapting only that dialect-specific scalar to UUID for this DB fixture.
    def decode_sqlite_cursor(cursor: str | None):
        decoded = decode_datetime_cursor(cursor)
        if decoded is None:
            return None
        timestamp, raw_id = decoded
        return timestamp, UUID(raw_id)

    monkeypatch.setattr(
        "app.repositories.chat_repository.decode_datetime_cursor",
        decode_sqlite_cursor,
    )

    first_page, has_more, cursor = await repository.get_chats_for_user(
        owner.id, None, 1
    )
    assert [item[0].id for item in first_page] == [first_chat.id]
    assert has_more is True
    assert cursor is not None

    second_page, _, _ = await repository.get_chats_for_user(owner.id, cursor, 1)
    assert [item[0].id for item in second_page] == [second_chat.id]


@pytest.mark.asyncio
async def test_chat_and_message_pages_follow_complete_ordering_keys(
    db_session: AsyncSession,
    user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await user_factory()
    peers = [await user_factory() for _ in range(5)]
    repository = ChatRepository(db_session)
    chats = [await repository.create_chat([owner, peer]) for peer in peers]
    # Exact UTC-second boundaries exercise both the message tie and NULL tail.
    same_time = datetime(2026, 10, 16, 12, tzinfo=UTC)
    older_time = same_time - timedelta(minutes=1)
    low_message_id = UUID("00000000-0000-0000-0000-00000000000a")
    high_message_id = UUID("00000000-0000-0000-0000-00000000000b")
    db_session.add_all(
        [
            Message(
                id=low_message_id,
                chat_id=chats[0].id,
                sender_id=peers[0].id,
                content="lower id at same time",
                created_at=same_time,
                read_status=True,
            ),
            Message(
                id=high_message_id,
                chat_id=chats[0].id,
                sender_id=peers[0].id,
                content="higher id at same time",
                created_at=same_time,
                read_status=True,
            ),
            Message(
                id=UUID("00000000-0000-0000-0000-00000000000c"),
                chat_id=chats[1].id,
                sender_id=peers[1].id,
                content="equal chat ordering time",
                created_at=same_time,
                read_status=True,
            ),
            Message(
                id=UUID("00000000-0000-0000-0000-00000000000d"),
                chat_id=chats[2].id,
                sender_id=peers[2].id,
                content="older chat ordering time",
                created_at=older_time,
                read_status=True,
            ),
        ]
    )
    await db_session.flush()

    def decode_sqlite_cursor(cursor: str | None):
        decoded = decode_datetime_cursor(cursor)
        if decoded is None:
            return None
        timestamp, raw_id = decoded
        return timestamp, UUID(raw_id)

    monkeypatch.setattr(
        "app.repositories.chat_repository.decode_datetime_cursor",
        decode_sqlite_cursor,
    )

    null_tail_ids = sorted([chats[3].id, chats[4].id], reverse=True)
    expected_chat_ids = [
        *sorted([chats[0].id, chats[1].id], reverse=True),
        chats[2].id,
        *null_tail_ids,
    ]
    actual_chat_ids = []
    cursor = None
    for index in range(len(expected_chat_ids)):
        page, has_more, cursor = await repository.get_chats_for_user(
            owner.id, cursor, 1
        )
        assert len(page) == 1
        actual_chat_ids.append(page[0][0].id)
        assert has_more is (index < len(expected_chat_ids) - 1)
        assert (cursor is not None) is has_more

    assert actual_chat_ids == expected_chat_ids
    assert len(actual_chat_ids) == len(set(actual_chat_ids)) == len(chats)
    assert actual_chat_ids[-len(null_tail_ids) :] == null_tail_ids

    first_page, has_more, cursor = await repository.get_messages(
        chats[0].id, None, 1, user_id=owner.id
    )
    assert [message.id for message in first_page] == [high_message_id]
    assert has_more is True
    assert cursor is not None
    second_page, has_more, cursor = await repository.get_messages(
        chats[0].id, cursor, 1, user_id=owner.id
    )
    assert [message.id for message in second_page] == [low_message_id]
    assert has_more is False
    assert cursor is None

    latest = await repository.get_last_message(chats[0].id, user_id=owner.id)
    assert latest is not None
    assert latest.id == high_message_id
