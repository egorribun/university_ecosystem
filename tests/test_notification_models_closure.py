"""Closure test for NotificationQueueJob system-managed initialization."""

from uuid import uuid4

from app.models.notifications import NotificationQueueJob


def test_notification_queue_job_accepts_system_managed_assignment_flag():
    job = NotificationQueueJob(
        kind="event",
        record_id=uuid4(),
        _allow_system_managed_assignment=True,
    )

    assert "NotificationQueueJob" in repr(job)
    assert job.kind == "event"
