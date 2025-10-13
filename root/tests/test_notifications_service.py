import datetime as dt

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.models import (
    Notification,
    NotificationDelivery,
    PushSubscription,
    User,
)
from app.services import notifications as notifications_module
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


@pytest.fixture
def configured_push_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_vapid_cache()
    monkeypatch.setattr(settings, "vapid_public_key", "test-public-key")
    monkeypatch.setattr(settings, "vapid_private_key", "test-private-key")
    monkeypatch.setattr(settings, "vapid_subject", "mailto:test@example.com")
    yield
    _reset_vapid_cache()


def test_is_user_in_quiet_hours_crosses_midnight():
    user = User(dnd_enabled=True, dnd_start=dt.time(22, 0), dnd_end=dt.time(7, 0))
    assert is_user_in_quiet_hours(user, now_time=dt.time(23, 15)) is True
    assert is_user_in_quiet_hours(user, now_time=dt.time(6, 45)) is True
    assert is_user_in_quiet_hours(user, now_time=dt.time(12, 0)) is False


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
