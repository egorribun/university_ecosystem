"""Closure tests for notification model constructors and representations."""

from datetime import UTC, datetime
from uuid import uuid4

from app.models.notifications import (
    Notification,
    NotificationDelivery,
    NotificationQueueJob,
    PushSubscription,
)


def test_notification_queue_job_accepts_system_managed_assignment_flag():
    job = NotificationQueueJob(
        kind="event",
        record_id=uuid4(),
        _allow_system_managed_assignment=True,
    )

    assert "NotificationQueueJob" in repr(job)
    assert job.kind == "event"


def test_notification_queue_job_keeps_python_and_server_defaults_in_sync():
    """Queue retries must be deterministic before the INSERT reaches PostgreSQL."""

    table = NotificationQueueJob.__table__
    attempts = table.c.attempts
    dead_lettered = table.c.dead_lettered

    assert attempts.default is not None
    assert attempts.default.arg == 0
    assert str(attempts.server_default.arg) == "0"
    assert dead_lettered.default is not None
    assert dead_lettered.default.arg is False
    assert str(dead_lettered.server_default.arg) == "false"


def test_notification_models_accept_system_managed_assignment_flag():
    created_at = datetime.now(UTC)
    notification = Notification(
        user_id=uuid4(),
        title="Title",
        created_at=created_at,
        _allow_system_managed_assignment=True,
    )
    delivery = NotificationDelivery(
        notification_id=uuid4(),
        notification_created_at=created_at,
        attempted_at=created_at,
        _allow_system_managed_assignment=True,
    )
    subscription = PushSubscription(
        user_id=uuid4(),
        endpoint="https://push.example.test/subscription",
        p256dh="p256dh",
        auth="auth",
        _allow_system_managed_assignment=True,
    )

    assert notification.title == "Title"
    assert "NotificationDelivery" in repr(delivery)
    assert "push.example" in repr(subscription)
