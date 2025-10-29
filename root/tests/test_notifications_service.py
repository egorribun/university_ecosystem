import asyncio
import datetime as dt
import logging
from contextlib import contextmanager

import pytest
from sqlalchemy import delete, event, select

from app.auth.security import get_password_hash
from app.core.config import settings
from app.models.models import (
    Group,
    Notification,
    NotificationDelivery,
    PushSubscription,
    Schedule,
    User,
)
from app.services import notification_queue
from app.services import notifications as notifications_module
from app.services import webpush as webpush_module
from app.services.notifications import (
    aggregate_notification_delivery_stats,
    create_notifications_for_users,
    is_user_in_quiet_hours,
    prepare_push_payload_for_user,
)
from app.services.webpush import WebPushResult


def _reset_vapid_cache() -> None:
    for cached in ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "WEBPUSH_SUBJECT"):
        settings.__dict__.pop(cached, None)


@contextmanager
def _count_queries(session):
    queries = 0
    engine = session.bind
    if engine is None:
        yield lambda: queries
        return

    sync_engine = engine.sync_engine

    def _before_cursor_execute(
        _conn, _cursor, _statement, _parameters, _context, _executemany
    ) -> None:
        nonlocal queries
        queries += 1

    event.listen(sync_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        yield lambda: queries
    finally:
        event.remove(sync_engine, "before_cursor_execute", _before_cursor_execute)


@pytest.fixture
def configured_push_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_vapid_cache()
    monkeypatch.setattr(settings, "vapid_public_key", "test-public-key")
    monkeypatch.setattr(settings, "vapid_private_key", "test-private-key")
    monkeypatch.setattr(settings, "vapid_subject", "mailto:test@example.com")
    yield
    _reset_vapid_cache()


@pytest.fixture(autouse=True)
async def reset_notification_queue_state() -> None:
    await notification_queue.shutdown_notification_queue()
    await notification_queue.reset_testing_state()
    yield
    await notification_queue.shutdown_notification_queue()


async def _login(async_client, email: str, password: str) -> dict[str, str]:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_is_user_in_quiet_hours_crosses_midnight():
    user = User(dnd_enabled=True, dnd_start=dt.time(22, 0), dnd_end=dt.time(7, 0))
    assert is_user_in_quiet_hours(user, now_time=dt.time(23, 15)) is True
    assert is_user_in_quiet_hours(user, now_time=dt.time(6, 45)) is True
    assert is_user_in_quiet_hours(user, now_time=dt.time(12, 0)) is False


def test_is_user_in_quiet_hours_uses_user_timezone(monkeypatch: pytest.MonkeyPatch):
    user = User(
        dnd_enabled=True,
        dnd_start=dt.time(21, 0),
        dnd_end=dt.time(6, 0),
        timezone="America/New_York",
    )

    base = dt.datetime(2024, 1, 1, 2, 30, tzinfo=dt.timezone.utc)

    class _FixedDatetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return base.replace(tzinfo=None)
            return base.astimezone(tz)

    monkeypatch.setattr(notifications_module.dt, "datetime", _FixedDatetime)
    assert is_user_in_quiet_hours(user) is True

    monkeypatch.setattr(webpush_module, "datetime", _FixedDatetime)
    assert webpush_module._is_user_in_quiet_hours(user) is True


def test_is_user_in_quiet_hours_defaults_to_utc(monkeypatch: pytest.MonkeyPatch):
    user = User(dnd_enabled=True, dnd_start=dt.time(1, 0), dnd_end=dt.time(5, 0))

    base = dt.datetime(2024, 6, 1, 3, 0, tzinfo=dt.timezone.utc)

    class _UtcDatetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return base.replace(tzinfo=None)
            return base.astimezone(tz)

    monkeypatch.setattr(notifications_module.dt, "datetime", _UtcDatetime)
    assert is_user_in_quiet_hours(user) is True

    user.timezone = "Invalid/Zone"
    assert is_user_in_quiet_hours(user) is True

    monkeypatch.setattr(webpush_module, "datetime", _UtcDatetime)
    assert webpush_module._is_user_in_quiet_hours(user) is True


def test_prepare_push_payload_applies_silent_mode():
    payload = {"title": "Test", "data": {"foo": "bar"}}
    user = User(dnd_enabled=True, dnd_start=dt.time(21, 0), dnd_end=dt.time(6, 0))

    result = prepare_push_payload_for_user(payload, user, now_time=dt.time(22, 30))

    assert result is not payload
    assert result["silent"] is True
    assert result["vibrate"] == []
    assert result["renotify"] is False
    assert result["requireInteraction"] is False
    assert result["data"]["foo"] == "bar"
    assert result["data"]["dnd_suppressed"] is True
    assert "silent" not in payload


def test_prepare_push_payload_keeps_original_when_outside_interval():
    payload = {"title": "Test outside", "data": {"foo": "bar"}}
    user = User(dnd_enabled=True, dnd_start=dt.time(22, 0), dnd_end=dt.time(7, 0))

    result = prepare_push_payload_for_user(payload, user, now_time=dt.time(15, 0))

    assert "silent" not in result
    assert result["data"]["foo"] == "bar"
    assert "dnd_suppressed" not in result["data"]


@pytest.mark.anyio
async def test_create_notifications_records_webpush_deliveries(
    db_session,
    user_factory,
    configured_push_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    user = await user_factory()
    subscription = PushSubscription(
        user_id=user.id,
        endpoint="https://push.example.test/sub-1",
        p256dh="key-1",
        auth="auth-1",
        topics=["system"],
    )
    db_session.add(subscription)
    await db_session.commit()

    def _fake_send(sub: PushSubscription, payload: dict[str, object]) -> WebPushResult:
        return WebPushResult(
            subscription_id=sub.id,
            endpoint=sub.endpoint,
            user_id=sub.user_id,
            status="sent",
            status_code=201,
        )

    monkeypatch.setattr(notifications_module, "send_web_push", _fake_send)

    created = await create_notifications_for_users(
        db_session,
        title="Hello",
        body="World",
        url="/hello",
        user_ids=[user.id],
        topic="system",
    )

    assert created == 1

    notifications = (
        (
            await db_session.execute(
                select(Notification).where(Notification.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(notifications) == 1

    deliveries = (
        (await db_session.execute(select(NotificationDelivery))).scalars().all()
    )
    assert len(deliveries) == 1
    delivery = deliveries[0]
    assert delivery.notification_id == notifications[0].id
    assert delivery.channel == "webpush"
    assert delivery.status == "sent"
    assert delivery.status_code == 201
    assert delivery.delivered_at is not None
    assert delivery.attempted_at is not None

    stats = await aggregate_notification_delivery_stats(db_session)
    key = {(row["channel"], row["status"]): row for row in stats}
    assert key[("webpush", "sent")]["count"] == 1
    assert key[("webpush", "sent")]["delivered"] == 1


@pytest.mark.anyio
async def test_create_notifications_records_skip_without_credentials(
    db_session, user_factory, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "vapid_public_key", "")
    monkeypatch.setattr(settings, "vapid_private_key", "")
    _reset_vapid_cache()

    user = await user_factory()

    created = await create_notifications_for_users(
        db_session,
        title="No Push",
        body="Missing credentials",
        user_ids=[user.id],
        topic="system",
    )

    assert created == 1

    deliveries = (
        (await db_session.execute(select(NotificationDelivery))).scalars().all()
    )
    assert len(deliveries) == 1
    delivery = deliveries[0]
    assert delivery.status == "skipped_no_credentials"
    assert delivery.delivered_at is None
    _reset_vapid_cache()


@pytest.mark.anyio
async def test_generate_schedule_reminders_query_count_constant(
    db_session, user_factory, monkeypatch: pytest.MonkeyPatch
):
    group = Group(name="G1")
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)

    await user_factory(group_id=group.id)

    async def _fake_create(*_args, **_kwargs) -> int:
        return 0

    monkeypatch.setattr(
        notifications_module,
        "create_notifications_for_users",
        _fake_create,
    )

    async def _prepare_lessons(count: int) -> None:
        await db_session.execute(delete(Schedule))
        await db_session.commit()
        now = dt.datetime.now(dt.timezone.utc)
        lessons = [
            Schedule(
                group_id=group.id,
                subject=f"Subject {idx}",
                teacher="Teacher",
                room="101",
                weekday="monday",
                start_time=now + dt.timedelta(minutes=idx + 1),
                end_time=now + dt.timedelta(minutes=idx + 2),
            )
            for idx in range(count)
        ]
        db_session.add_all(lessons)
        await db_session.commit()

    async def _run_with_count(count: int) -> int:
        await _prepare_lessons(count)
        with _count_queries(db_session) as get_count:
            await notifications_module.generate_schedule_reminders(
                db_session, window_minutes=15
            )
        return get_count()

    single_count = await _run_with_count(1)
    many_count = await _run_with_count(5)

    assert single_count == many_count


@pytest.mark.anyio
async def test_generate_schedule_reminders_handles_duplicate_titles(
    db_session, user_factory
):
    group = Group(name="G2")
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)

    user = await user_factory(group_id=group.id)

    now = dt.datetime.now(dt.timezone.utc)
    lessons = [
        Schedule(
            group_id=group.id,
            subject="Mathematics",
            teacher="Teacher",
            room="201",
            weekday="monday",
            start_time=now + dt.timedelta(minutes=idx * 5 + 5),
            end_time=now + dt.timedelta(minutes=idx * 5 + 55),
        )
        for idx in range(2)
    ]
    db_session.add_all(lessons)
    await db_session.commit()

    created = await notifications_module.generate_schedule_reminders(
        db_session, window_minutes=30
    )

    assert created == 2

    notifications = (
        (
            await db_session.execute(
                select(Notification).where(Notification.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(notifications) == 2
    dedupe_keys = {note.dedupe_key for note in notifications}
    assert len(dedupe_keys) == 2
    assert all(key and key.startswith("schedule-reminder") for key in dedupe_keys)

    repeat_created = await notifications_module.generate_schedule_reminders(
        db_session, window_minutes=30
    )

    assert repeat_created == 0


@pytest.mark.anyio
async def test_generate_schedule_reminders_skips_inactive_users(
    db_session, user_factory
):
    group = Group(name="G3")
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)

    active_user = await user_factory(group_id=group.id, is_active=True)
    inactive_user = await user_factory(group_id=group.id, is_active=False)

    now = dt.datetime.now(dt.timezone.utc)
    lesson = Schedule(
        group_id=group.id,
        subject="History",
        teacher="Teacher",
        room="301",
        weekday="tuesday",
        start_time=now + dt.timedelta(minutes=10),
        end_time=now + dt.timedelta(minutes=60),
    )
    db_session.add(lesson)
    await db_session.commit()

    created = await notifications_module.generate_schedule_reminders(
        db_session, window_minutes=30
    )

    assert created == 1

    notifications = (
        (
            await db_session.execute(
                select(Notification).where(
                    Notification.user_id.in_([active_user.id, inactive_user.id])
                )
            )
        )
        .scalars()
        .all()
    )

    assert notifications
    assert {note.user_id for note in notifications} == {active_user.id}


@pytest.mark.anyio
async def test_scheduler_loop_logs_failures(monkeypatch: pytest.MonkeyPatch, caplog):
    class _DummySession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def _failing_generate(*_args, **_kwargs):
        raise RuntimeError("boom")

    async def _cancel_sleep(_seconds: float):
        raise asyncio.CancelledError()

    monkeypatch.setattr(notifications_module, "async_session", lambda: _DummySession())
    monkeypatch.setattr(
        notifications_module,
        "generate_schedule_reminders",
        _failing_generate,
    )
    monkeypatch.setattr(notifications_module.asyncio, "sleep", _cancel_sleep)

    caplog.set_level(logging.ERROR, logger=notifications_module.logger.name)

    await notifications_module._scheduler_loop(poll_seconds=1, window_minutes=1)

    assert any(
        "Failed to generate schedule reminders" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.anyio
async def test_event_creation_enqueues_notifications(
    async_client,
    db_session,
    user_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    admin = await user_factory(role="admin")
    password = "Adm1nPass!"
    admin.hashed_password = get_password_hash(password)
    await db_session.commit()

    headers = await _login(async_client, admin.email, password)

    delivery_started = asyncio.Event()
    calls = 0

    async def _fake_create(*args, **kwargs):
        nonlocal calls
        calls += 1
        delivery_started.set()
        return 0

    monkeypatch.setattr(
        notifications_module,
        "create_notifications_for_users",
        _fake_create,
    )

    starts_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
    ends_at = starts_at + dt.timedelta(hours=2)

    payload = {
        "title": "Async Event",
        "description": "Test event",
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
    }

    response = await async_client.post("/events", json=payload, headers=headers)
    assert response.status_code == 200
    assert not delivery_started.is_set()

    await notification_queue.wait_for_all_jobs(timeout=1.0)
    await asyncio.wait_for(delivery_started.wait(), timeout=1.0)
    assert calls == 1


@pytest.mark.anyio
async def test_news_creation_enqueues_notifications(
    async_client,
    db_session,
    user_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    admin = await user_factory(role="admin")
    password = "Adm1nPass!"
    admin.hashed_password = get_password_hash(password)
    await db_session.commit()

    headers = await _login(async_client, admin.email, password)

    delivery_started = asyncio.Event()
    calls = 0

    async def _fake_create(*args, **kwargs):
        nonlocal calls
        calls += 1
        delivery_started.set()
        return 0

    monkeypatch.setattr(
        notifications_module,
        "create_notifications_for_users",
        _fake_create,
    )

    response = await async_client.post(
        "/news",
        json={"title": "Async News", "content": "Hello"},
        headers=headers,
    )
    assert response.status_code == 200
    assert not delivery_started.is_set()

    await notification_queue.wait_for_all_jobs(timeout=1.0)
    await asyncio.wait_for(delivery_started.wait(), timeout=1.0)
    assert calls == 1
