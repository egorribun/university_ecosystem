import asyncio
import datetime as dt
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import Schedule, User
from app.services.notifications.cleanup import cleanup_stale_notifications
from app.services.notifications.quiet_hours import (
    is_user_in_quiet_hours,
    prepare_push_payload_for_user,
)
from app.services.notifications.schedule_reminders import (
    build_schedule_reminder_message,
    generate_schedule_reminders,
)
from app.services.notifications.scheduler import (
    _scheduler_loop,
    start_notifications_scheduler,
)
from app.services.notifications.stats import aggregate_notification_delivery_stats


@pytest.mark.asyncio
async def test_aggregate_notification_delivery_stats():
    db = AsyncMock()

    mock_row = MagicMock()
    mock_row._mapping = {
        "channel": "push",
        "status": "delivered",
        "count": 5,
        "delivered": 4,
        "first_attempt_at": dt.datetime(2023, 1, 1, tzinfo=UTC),
        "last_attempt_at": dt.datetime(2023, 1, 2, tzinfo=UTC),
    }
    mock_result = MagicMock()
    mock_result.__iter__.return_value = [mock_row]
    db.execute.return_value = mock_result

    stats = await aggregate_notification_delivery_stats(
        db, since=dt.datetime(2023, 1, 1, tzinfo=UTC), channel="push"
    )

    assert len(stats) == 1
    assert stats[0] == {
        "channel": "push",
        "status": "delivered",
        "count": 5,
        "delivered": 4,
        "first_attempt_at": dt.datetime(2023, 1, 1, tzinfo=UTC),
        "last_attempt_at": dt.datetime(2023, 1, 2, tzinfo=UTC),
    }


@pytest.mark.parametrize(
    "dnd_enabled, dnd_start, dnd_end, now_time, expected",
    [
        (False, None, None, dt.time(10, 0), False),
        (True, dt.time(22, 0), dt.time(8, 0), dt.time(23, 0), True),
        (True, dt.time(22, 0), dt.time(8, 0), dt.time(2, 0), True),
        (True, dt.time(22, 0), dt.time(8, 0), dt.time(10, 0), False),
        (True, dt.time(10, 0), dt.time(12, 0), dt.time(11, 0), True),
        (True, dt.time(10, 0), dt.time(12, 0), dt.time(13, 0), False),
        (True, dt.time(10, 0), dt.time(10, 0), dt.time(10, 0), True),
    ],
)
def test_is_user_in_quiet_hours(dnd_enabled, dnd_start, dnd_end, now_time, expected):
    user = User()
    user.preferences = MagicMock(
        dnd_enabled=dnd_enabled, dnd_start=dnd_start, dnd_end=dnd_end
    )

    assert is_user_in_quiet_hours(user, now_time=now_time) is expected


def test_is_user_in_quiet_hours_no_user():
    assert is_user_in_quiet_hours(None) is False


def test_prepare_push_payload_for_user():
    user = User()
    user.preferences = MagicMock(
        dnd_enabled=True, dnd_start=dt.time(22, 0), dnd_end=dt.time(8, 0)
    )
    payload = {"data": {"foo": "bar"}}

    res = prepare_push_payload_for_user(payload, user, now_time=dt.time(23, 0))

    assert res["silent"] is True
    assert res["vibrate"] == []
    assert res["renotify"] is False
    assert res["requireInteraction"] is False
    assert res["data"]["dnd_suppressed"] is True
    assert res["data"]["foo"] == "bar"

    # Outside DND
    res_out = prepare_push_payload_for_user(payload, user, now_time=dt.time(10, 0))
    assert res_out.get("silent") is None


@pytest.mark.asyncio
async def test_cleanup_stale_notifications_refined(monkeypatch):
    db = AsyncMock()
    mock_settings = MagicMock(
        notifications_retention_days=30, notifications_retention_batch_size=10
    )
    monkeypatch.setattr("app.services.notifications.cleanup.settings", mock_settings)

    # cleanup_stale_notifications has two separate while-True loops:
    #   loop 1 (deliveries): scalars → [1], then scalars → [] → break
    #   loop 2 (notifications): scalars → [1], then scalars → [] → break
    # db.scalars is awaited, so it must be an AsyncMock whose return value
    # exposes .all().  We sequence four results via side_effect on the AsyncMock.
    scalars_results = [
        MagicMock(**{"all.return_value": [1]}),  # delivery loop iteration 1
        MagicMock(**{"all.return_value": []}),  # delivery loop → break
        MagicMock(**{"all.return_value": [1]}),  # notification loop iteration 1
        MagicMock(**{"all.return_value": []}),  # notification loop → break
    ]
    db.scalars = AsyncMock(side_effect=scalars_results)

    mock_exec = MagicMock()
    mock_exec.rowcount = 1
    db.execute.return_value = mock_exec

    n_del, d_del = await cleanup_stale_notifications(
        db=db, now=dt.datetime(2023, 2, 1, tzinfo=UTC)
    )
    assert n_del == 1
    assert d_del == 1


@pytest.mark.asyncio
async def test_cleanup_stale_notifications_zero_retention():
    n_del, d_del = await cleanup_stale_notifications(retention_days=0)
    assert n_del == 0
    assert d_del == 0


@pytest.mark.asyncio
async def test_cleanup_stale_notifications_no_db(monkeypatch):
    mock_session_ctx = MagicMock()
    mock_db = AsyncMock()
    mock_session_ctx.__aenter__.return_value = mock_db
    monkeypatch.setattr(
        "app.services.notifications.cleanup._async_session", lambda: mock_session_ctx
    )

    mock_settings = MagicMock(
        notifications_retention_days=30, notifications_retention_batch_size=10
    )
    monkeypatch.setattr("app.services.notifications.cleanup.settings", mock_settings)

    def scalars_side_effect(*args, **kwargs):
        mock = MagicMock()
        mock.all.side_effect = [[], []]
        return mock

    mock_db.scalars.side_effect = scalars_side_effect

    n_del, d_del = await cleanup_stale_notifications()
    assert n_del == 0
    assert d_del == 0


@pytest.mark.asyncio
async def test_start_notifications_scheduler(monkeypatch):
    # start_notifications_scheduler does a local `from app.workers.notifications
    # import start_notifications_scheduler as _start`, so patching the module-level
    # name '_start' on the scheduler module has no effect — it is never read.
    # We must patch the function on the workers module directly and also cancel
    # the background task that start_notifications_scheduler creates in the
    # event loop to prevent leaking it into subsequent tests.
    import sys

    mock_worker_notifications = MagicMock()
    mock_start = AsyncMock(return_value=None)
    mock_worker_notifications.start_notifications_scheduler = mock_start
    monkeypatch.setitem(
        sys.modules, "app.workers.notifications", mock_worker_notifications
    )

    await start_notifications_scheduler()
    mock_start.assert_called_once()


@pytest.mark.asyncio
async def test_scheduler_loop(monkeypatch):
    # _scheduler_loop does `from app.workers import notifications as worker_module`.
    # Python resolves this by:
    #   1. importing app.workers (gets the package from sys.modules)
    #   2. getting `notifications` attribute off that package object
    # app.workers.__init__.py does NOT pre-import notifications, so the attribute
    # doesn't exist until it's explicitly set.  We inject it via monkeypatch so it
    # is automatically restored after the test.
    import sys

    import app.workers as _workers_pkg

    mock_scheduler = AsyncMock()
    mock_scheduler.run_forever.side_effect = asyncio.CancelledError()

    mock_worker_module = MagicMock()
    # run_forever must be an AsyncMock so `await scheduler.run_forever()` works.
    mock_worker_module.NotificationsScheduler.return_value = mock_scheduler

    # Register in sys.modules (for submodule resolution) and as a package attr.
    monkeypatch.setitem(sys.modules, "app.workers.notifications", mock_worker_module)
    monkeypatch.setattr(
        _workers_pkg, "notifications", mock_worker_module, raising=False
    )

    await _scheduler_loop()


def test_build_schedule_reminder_message():
    lesson = Schedule()
    lesson.id = "lesson-1"
    lesson.start_time = dt.datetime(2023, 1, 1, 10, 0, tzinfo=UTC)
    lesson.lesson_type = "Lecture"
    lesson.subject = "Math"
    lesson.room = "101"

    (
        title,
        body,
        tag,
        data_payload,
        _title_translations,
        _body_translations,
        dedupe_value,
    ) = build_schedule_reminder_message(lesson)

    assert title
    assert body
    assert tag
    assert data_payload
    assert dedupe_value


@pytest.mark.asyncio
async def test_generate_schedule_reminders(monkeypatch):
    db = AsyncMock()
    # Mock schedules
    mock_schedule = Schedule()
    mock_schedule.id = "s1"
    mock_schedule.group_id = "g1"
    mock_schedule.start_time = dt.datetime.now(UTC) + dt.timedelta(minutes=2)
    mock_schedule.lesson_type = "Lecture"

    mock_scalars = MagicMock()
    mock_scalars.scalars().all.return_value = [mock_schedule]

    # Mock users
    mock_users = MagicMock()
    mock_users.__iter__.return_value = [("u1", "g1")]

    # Mock existing
    mock_existing = MagicMock()
    mock_existing.__iter__.return_value = []

    db.execute.side_effect = [mock_scalars, mock_users, mock_existing]

    mock_create = AsyncMock()
    mock_create.return_value = 1
    monkeypatch.setattr(
        "app.services.notifications.schedule_reminders.create_notifications_for_users",
        mock_create,
    )

    res = await generate_schedule_reminders(db)
    assert res == 1


@pytest.mark.asyncio
async def test_generate_schedule_reminders_no_schedules():
    db = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.scalars().all.return_value = []
    db.execute.return_value = mock_scalars

    res = await generate_schedule_reminders(db)
    assert res == 0
