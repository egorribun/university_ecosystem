from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from sqlalchemy import select

from app.core.nats_broker import NatsTaskBroker, _NatsTaskPayload, broker
from app.models import Event, News, NewsComment, Notification, User
from app.services.notifications import delivery as notification_delivery
from app.tasks import notifications as notification_tasks

TASK_CASES = [
    (
        notification_tasks.enqueue_event_notification_task,
        "_notify_about_event",
        (Event,),
        1,
    ),
    (
        notification_tasks.enqueue_news_notification_task,
        "_notify_about_news",
        (News,),
        1,
    ),
    (
        notification_tasks.enqueue_comment_notification_task,
        "_notify_about_comment",
        (News, NewsComment, User),
        3,
    ),
]


@pytest.mark.parametrize(
    ("task", "notify_name", "model_types", "argument_count"), TASK_CASES
)
async def test_uuid_notification_ids_round_trip_through_nats_task_payload(
    monkeypatch,
    task,
    notify_name: str,
    model_types: tuple[type, ...],
    argument_count: int,
) -> None:
    """UUID primary keys survive task JSON encoding and handler dispatch."""
    task_ids = [uuid.uuid4() for _ in range(argument_count)]
    broker = NatsTaskBroker()
    jetstream = AsyncMock()
    broker._js = jetstream
    task_name = f"{task.__module__}.{task.__name__}"

    await broker.enqueue(task_name, *task_ids, locale="en")

    published_subject, published_body = jetstream.publish.await_args.args[:2]
    payload = _NatsTaskPayload.model_validate(json.loads(published_body))
    assert published_subject == f"tasks.{task_name}"
    assert payload.name == task_name
    assert payload.args == [str(task_id) for task_id in task_ids]
    assert payload.kwargs == {"locale": "en"}

    loaded_rows = [MagicMock() for _ in model_types]
    db = AsyncMock()
    db.get.side_effect = loaded_rows
    db.commit = AsyncMock()

    @asynccontextmanager
    async def session_scope():
        yield db

    monkeypatch.setattr(notification_tasks, "async_session", lambda: session_scope())
    notify = AsyncMock()
    monkeypatch.setattr(notification_tasks, notify_name, notify)

    # This is the same JSON-decoded argument shape passed by run_worker().
    await task(*payload.args, **payload.kwargs)

    assert db.get.await_args_list == [
        call(model_type, task_id)
        for model_type, task_id in zip(model_types, task_ids, strict=True)
    ]
    notify.assert_awaited_once_with(db, *loaded_rows, locale="en")
    db.commit.assert_awaited_once()


@pytest.mark.parametrize(
    ("task", "notify_name", "model_types", "argument_count"), TASK_CASES
)
async def test_notification_task_preserves_legacy_integer_ids(
    monkeypatch,
    task,
    notify_name: str,
    model_types: tuple[type, ...],
    argument_count: int,
) -> None:
    legacy_ids = list(range(1, argument_count + 1))
    loaded_rows = [MagicMock() for _ in model_types]
    db = AsyncMock()
    db.get.side_effect = loaded_rows
    db.commit = AsyncMock()

    @asynccontextmanager
    async def session_scope():
        yield db

    monkeypatch.setattr(notification_tasks, "async_session", lambda: session_scope())
    notify = AsyncMock()
    monkeypatch.setattr(notification_tasks, notify_name, notify)

    await task(*legacy_ids, locale="en")

    assert db.get.await_args_list == [
        call(model_type, uuid.UUID(int=legacy_id))
        for model_type, legacy_id in zip(model_types, legacy_ids, strict=True)
    ]
    notify.assert_awaited_once_with(db, *loaded_rows, locale="en")
    db.commit.assert_awaited_once()


@pytest.mark.parametrize(
    ("task", "argument_count"),
    [(case[0], case[3]) for case in TASK_CASES],
)
async def test_notification_task_rejects_malformed_uuid_before_opening_session(
    monkeypatch, task, argument_count: int
) -> None:
    def unexpected_session_open():
        raise AssertionError("invalid task ID must fail before opening a session")

    monkeypatch.setattr(notification_tasks, "async_session", unexpected_session_open)

    with pytest.raises(ValueError):
        await task(*(["not-a-uuid"] * argument_count), locale="en")


async def test_nats_task_enqueue_still_rejects_unsupported_payload_objects() -> None:
    broker = NatsTaskBroker()
    jetstream = AsyncMock()
    broker._js = jetstream

    with pytest.raises(TypeError):
        await broker.enqueue("test.unsupported", object())

    jetstream.publish.assert_not_awaited()


async def test_event_notification_round_trip_persists_in_database(
    db_session, user_factory, monkeypatch
) -> None:
    author = await user_factory()
    now = datetime.now(UTC)
    event = Event(
        title="Queue round-trip",
        starts_at=now + timedelta(hours=1),
        ends_at=now + timedelta(hours=2),
        created_by=author.id,
    )
    db_session.add(event)
    await db_session.commit()

    jetstream = AsyncMock()
    monkeypatch.setattr(broker, "_js", jetstream)
    # This integration path must cross the real producer boundary; the
    # suite's autouse fixture mocks the singleton enqueue method by default.
    monkeypatch.setattr(
        broker, "enqueue", NatsTaskBroker.enqueue.__get__(broker, NatsTaskBroker)
    )
    monkeypatch.setattr(notification_delivery, "_is_push_configured", lambda: False)

    await notification_tasks.enqueue_event_notification_task.kick(event.id, locale="en")

    published_subject, published_body = jetstream.publish.await_args.args[:2]
    payload = _NatsTaskPayload.model_validate(json.loads(published_body))
    assert published_subject == f"tasks.{payload.name}"
    assert payload.name == ("app.tasks.notifications.enqueue_event_notification_task")
    assert payload.args == [str(event.id)]

    await notification_tasks.enqueue_event_notification_task(
        *payload.args, **payload.kwargs
    )

    rows = (
        (
            await db_session.execute(
                select(Notification).where(
                    Notification.user_id == author.id,
                    Notification.type == "events.new",
                    Notification.url == f"/events/{event.id}",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
