import datetime
import uuid

import pytest

from app.models.notifications import Notification, NotificationDelivery
from app.services.notifications.stats import aggregate_notification_delivery_stats
from app.utils.uuid_v7 import generate_uuid7


@pytest.fixture
def clean_deliveries(db_session):
    # This fixture ensures we run against a clean database
    # In SQLite tests, transactions are rolled back, but we can seed safely.
    pass


@pytest.mark.asyncio
async def test_aggregate_stats_empty(db_session):
    stats = await aggregate_notification_delivery_stats(db_session)
    assert stats == []


@pytest.mark.asyncio
async def test_aggregate_stats_success(db_session, user_factory):
    now = datetime.datetime.now(datetime.UTC)
    notif_id = uuid.uuid4()
    user = await user_factory()
    notification = Notification(
        id=notif_id,
        user_id=user.id,
        title="Stats notification",
        body="Delivery stats",
        type="system",
        created_at=now,
    )

    # Seed 3 delivery records
    # Group 1: channel="push", status="delivered" (2 rows)
    d1 = NotificationDelivery(
        id=generate_uuid7(),
        notification_id=notif_id,
        notification_created_at=now,
        channel="push",
        status="delivered",
        attempted_at=now - datetime.timedelta(minutes=10),
        delivered_at=now - datetime.timedelta(minutes=10),
    )
    d2 = NotificationDelivery(
        id=generate_uuid7(),
        notification_id=notif_id,
        notification_created_at=now,
        channel="push",
        status="delivered",
        attempted_at=now - datetime.timedelta(minutes=5),
        delivered_at=now - datetime.timedelta(minutes=5),
    )
    # Group 2: channel="inapp", status="failed" (1 row)
    d3 = NotificationDelivery(
        id=generate_uuid7(),
        notification_id=notif_id,
        notification_created_at=now,
        channel="inapp",
        status="failed",
        attempted_at=now - datetime.timedelta(minutes=1),
        delivered_at=None,
    )

    db_session.add_all([notification, d1, d2, d3])
    await db_session.commit()

    # Aggregate all
    stats = await aggregate_notification_delivery_stats(db_session)
    assert len(stats) == 2

    # Map groups for easy checking
    groups = {f"{s['channel']}_{s['status']}": s for s in stats}

    assert "push_delivered" in groups
    push_group = groups["push_delivered"]
    assert push_group["count"] == 2
    assert push_group["delivered"] == 2
    assert push_group["first_attempt_at"] is not None
    assert push_group["last_attempt_at"] is not None

    assert "inapp_failed" in groups
    inapp_group = groups["inapp_failed"]
    assert inapp_group["count"] == 1
    assert inapp_group["delivered"] == 0
    assert inapp_group["first_attempt_at"] is not None
    assert inapp_group["last_attempt_at"] is not None


@pytest.mark.asyncio
async def test_aggregate_stats_filtering(db_session, user_factory):
    now = datetime.datetime.now(datetime.UTC)
    notif_id = uuid.uuid4()
    user = await user_factory()
    notification = Notification(
        id=notif_id,
        user_id=user.id,
        title="Filtered stats notification",
        body="Delivery stats",
        type="system",
        created_at=now,
    )

    # 1. Row outside since filter
    d1 = NotificationDelivery(
        id=generate_uuid7(),
        notification_id=notif_id,
        notification_created_at=now,
        channel="push",
        status="delivered",
        attempted_at=now - datetime.timedelta(hours=5),
        delivered_at=now - datetime.timedelta(hours=5),
    )
    # 2. Row inside since filter, matching channel
    d2 = NotificationDelivery(
        id=generate_uuid7(),
        notification_id=notif_id,
        notification_created_at=now,
        channel="push",
        status="delivered",
        attempted_at=now - datetime.timedelta(minutes=10),
        delivered_at=now - datetime.timedelta(minutes=10),
    )
    # 3. Row inside since filter, different channel
    d3 = NotificationDelivery(
        id=generate_uuid7(),
        notification_id=notif_id,
        notification_created_at=now,
        channel="inapp",
        status="delivered",
        attempted_at=now - datetime.timedelta(minutes=5),
        delivered_at=now - datetime.timedelta(minutes=5),
    )

    db_session.add_all([notification, d1, d2, d3])
    await db_session.commit()

    # Filter with since (last 1 hour)
    since_time = now - datetime.timedelta(hours=1)
    stats_since = await aggregate_notification_delivery_stats(
        db_session, since=since_time
    )
    # Should only aggregate d2 and d3 (2 different channels)
    assert len(stats_since) == 2
    for s in stats_since:
        assert s["count"] == 1

    # Filter with since AND channel="push"
    stats_filtered = await aggregate_notification_delivery_stats(
        db_session, since=since_time, channel="push"
    )
    # Should only aggregate d2
    assert len(stats_filtered) == 1
    assert stats_filtered[0]["channel"] == "push"
    assert stats_filtered[0]["count"] == 1
