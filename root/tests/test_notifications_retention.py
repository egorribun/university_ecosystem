import datetime as dt

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.models import Notification, NotificationDelivery
from app.services.notifications import cleanup_stale_notifications


@pytest.mark.anyio
async def test_cleanup_stale_notifications_respects_read_state(
    db_session, user_factory, monkeypatch
):
    monkeypatch.setattr(settings, "notifications_retention_batch_size", 1)

    now = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    user = await user_factory()

    old_read = Notification(
        user_id=user.id,
        title="Old read",
        body="body",
        type="info",
        url="/old-read",
        created_at=now - dt.timedelta(days=120),
        read=True,
        read_at=now - dt.timedelta(days=119),
    )
    another_old_read = Notification(
        user_id=user.id,
        title="Old read 2",
        body="body",
        type="info",
        url="/old-read-2",
        created_at=now - dt.timedelta(days=120),
        read=True,
        read_at=now - dt.timedelta(days=119),
    )
    old_unread = Notification(
        user_id=user.id,
        title="Old unread",
        body="body",
        type="info",
        url="/old-unread",
        created_at=now - dt.timedelta(days=120),
        read=False,
        read_at=None,
    )
    recent_read = Notification(
        user_id=user.id,
        title="Recent read",
        body="body",
        type="info",
        url="/recent-read",
        created_at=now - dt.timedelta(days=10),
        read=True,
        read_at=now - dt.timedelta(days=9),
    )

    deliveries = [
        NotificationDelivery(
            notification=old_read,
            channel="webpush",
            status="sent",
            attempted_at=now - dt.timedelta(days=110),
            delivered_at=now - dt.timedelta(days=110),
        ),
        NotificationDelivery(
            notification=another_old_read,
            channel="webpush",
            status="sent",
            attempted_at=now - dt.timedelta(days=110),
            delivered_at=now - dt.timedelta(days=110),
        ),
        NotificationDelivery(
            notification=old_unread,
            channel="webpush",
            status="sent",
            attempted_at=now - dt.timedelta(days=110),
            delivered_at=now - dt.timedelta(days=110),
        ),
        NotificationDelivery(
            notification=recent_read,
            channel="webpush",
            status="sent",
            attempted_at=now - dt.timedelta(days=5),
            delivered_at=now - dt.timedelta(days=5),
        ),
    ]

    db_session.add_all(
        [old_read, another_old_read, old_unread, recent_read, *deliveries]
    )
    await db_session.flush()
    recent_read_id = recent_read.id
    await db_session.commit()

    deleted_notifications, deleted_deliveries = await cleanup_stale_notifications(
        db=db_session, retention_days=90, now=now
    )

    assert deleted_notifications == 2
    assert deleted_deliveries == 3

    remaining_notifications = (
        (await db_session.execute(select(Notification).order_by(Notification.id)))
        .scalars()
        .all()
    )
    remaining_titles = {notification.title for notification in remaining_notifications}
    assert remaining_titles == {"Old unread", "Recent read"}

    remaining_deliveries = (
        (
            await db_session.execute(
                select(NotificationDelivery).order_by(NotificationDelivery.id)
            )
        )
        .scalars()
        .all()
    )
    assert [delivery.notification_id for delivery in remaining_deliveries] == [
        recent_read_id
    ]


@pytest.mark.anyio
async def test_cleanup_stale_notifications_disabled(db_session, user_factory):
    now = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    user = await user_factory()

    old_read = Notification(
        user_id=user.id,
        title="Keep me",
        body="body",
        type="info",
        url="/keep",
        created_at=now - dt.timedelta(days=200),
        read=True,
        read_at=now - dt.timedelta(days=199),
    )
    db_session.add(old_read)
    await db_session.commit()

    deleted_notifications, deleted_deliveries = await cleanup_stale_notifications(
        db=db_session, retention_days=0, now=now
    )

    assert deleted_notifications == 0
    assert deleted_deliveries == 0

    remaining = (await db_session.execute(select(Notification))).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].title == "Keep me"
