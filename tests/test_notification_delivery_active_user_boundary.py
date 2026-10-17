"""Delivery contracts for inactive accounts with retained push subscriptions."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping, Sequence
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Notification,
    NotificationDelivery,
    PushSubscription,
    UserPushTopic,
)
from app.services import webpush as webpush_module
from app.services.notifications import delivery
from app.services.webpush import WebPushResult


@pytest.mark.asyncio
async def test_initial_fanout_skips_inactive_subscription_owner(
    db_session: AsyncSession,
    user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_user = await user_factory(is_active=True)
    inactive_user = await user_factory(is_active=False)
    active_subscription = PushSubscription(
        user_id=active_user.id,
        endpoint=f"https://push.example.test/{uuid.uuid4().hex}",
        p256dh="synthetic-p256dh",
        auth="synthetic-auth",
        topics=[],
    )
    inactive_subscription = PushSubscription(
        user_id=inactive_user.id,
        endpoint=f"https://push.example.test/{uuid.uuid4().hex}",
        p256dh="synthetic-p256dh",
        auth="synthetic-auth",
        topics=[],
    )
    db_session.add_all([active_subscription, inactive_subscription])
    await db_session.flush()

    delivered_user_ids: list[uuid.UUID] = []

    def _send(
        subscription: PushSubscription, _payload: Mapping[str, Any]
    ) -> WebPushResult:
        user_id = uuid.UUID(str(subscription.user_id))
        delivered_user_ids.append(user_id)
        return WebPushResult(
            subscription_id=subscription.id,
            endpoint=subscription.endpoint,
            user_id=user_id,
            status="sent",
            status_code=201,
        )

    async def _process_results(_results: Sequence[WebPushResult]) -> None:
        return None

    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    monkeypatch.setattr(delivery, "send_web_push", _send)
    monkeypatch.setattr(webpush_module, "process_push_results", _process_results)

    created = await delivery.create_notifications_for_users(
        db_session,
        title="Synthetic notification",
        user_ids=[active_user.id, inactive_user.id],
        type="news",
    )

    assert created == 2
    assert delivered_user_ids == [active_user.id]


@pytest.mark.asyncio
async def test_initial_fanout_respects_explicit_topic_opt_out(
    db_session: AsyncSession,
    user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await user_factory(is_active=True)
    subscription = PushSubscription(
        user_id=user.id,
        endpoint=f"https://push.example.test/{uuid.uuid4().hex}",
        p256dh="synthetic-p256dh",
        auth="synthetic-auth",
        topics=[],
    )
    db_session.add_all([subscription, UserPushTopic(user_id=user.id, topics=[])])
    await db_session.flush()

    attempted_subscriptions: list[uuid.UUID] = []

    def _send(
        subscription: PushSubscription, _payload: Mapping[str, Any]
    ) -> WebPushResult:
        attempted_subscriptions.append(uuid.UUID(str(subscription.id)))
        return WebPushResult(
            subscription_id=subscription.id,
            endpoint=subscription.endpoint,
            user_id=user.id,
            status="sent",
            status_code=201,
        )

    async def _process_results(_results: Sequence[WebPushResult]) -> None:
        return None

    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    monkeypatch.setattr(delivery, "send_web_push", _send)
    monkeypatch.setattr(webpush_module, "process_push_results", _process_results)

    created = await delivery.create_notifications_for_users(
        db_session,
        title="Opted-out notification",
        user_ids=[user.id],
        type="news",
        topic="news.published",
    )

    notifications = (
        (
            await db_session.execute(
                select(Notification).where(Notification.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    rows = (
        (
            await db_session.execute(
                select(NotificationDelivery).where(
                    NotificationDelivery.subscription_id == subscription.id
                )
            )
        )
        .scalars()
        .all()
    )

    assert created == 0
    assert notifications == []
    assert rows == []
    assert attempted_subscriptions == []


@pytest.mark.asyncio
async def test_outbox_redelivery_rechecks_cached_user_topic_opt_out(
    db_session: AsyncSession,
    user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await user_factory(is_active=True)
    # Force the identity-mapped User relationship to hold the old default before
    # the preference row is inserted, as can happen in a long-lived transaction.
    assert user.push_topic_preferences is None
    subscription = PushSubscription(
        user_id=user.id,
        endpoint=f"https://push.example.test/{uuid.uuid4().hex}",
        p256dh="synthetic-p256dh",
        auth="synthetic-auth",
        topics=[],
    )
    notification = Notification(
        user_id=user.id,
        title="Queued notification",
        type="news",
        url="/news/1",
        read=False,
    )
    db_session.add_all(
        [subscription, notification, UserPushTopic(user_id=user.id, topics=[])]
    )
    await db_session.flush()

    send = AsyncMock()
    process_results = AsyncMock()
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    monkeypatch.setattr(webpush_module, "_send_push_async", send)
    monkeypatch.setattr(webpush_module, "process_push_results", process_results)

    outcome = await delivery.redeliver_notifications(
        db_session,
        notification_ids=[notification.id],
    )

    rows = (
        (
            await db_session.execute(
                select(NotificationDelivery).where(
                    NotificationDelivery.notification_id == notification.id
                )
            )
        )
        .scalars()
        .all()
    )
    persisted = (
        await db_session.execute(
            select(Notification.read).where(Notification.id == notification.id)
        )
    ).scalar_one()

    assert outcome.terminal_failures == 1
    assert outcome.sent == 0
    send.assert_not_awaited()
    process_results.assert_not_awaited()
    assert rows == []
    assert persisted is False


@pytest.mark.asyncio
async def test_outbox_cancellation_propagates_without_delivery_journal(
    db_session: AsyncSession,
    user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await user_factory(is_active=True)
    subscription = PushSubscription(
        user_id=user.id,
        endpoint=f"https://push.example.test/{uuid.uuid4().hex}",
        p256dh="synthetic-p256dh",
        auth="synthetic-auth",
        topics=[],
    )
    notification = Notification(
        user_id=user.id,
        title="Queued notification",
        type="news",
        url="/news/1",
        read=False,
    )
    db_session.add_all([subscription, notification])
    await db_session.flush()

    send_started = asyncio.Event()

    async def _blocked_send(
        _subscription: PushSubscription, _payload: Mapping[str, Any]
    ) -> WebPushResult:
        send_started.set()
        await asyncio.Event().wait()
        raise AssertionError("cancellation should stop the provider await")

    process_results = AsyncMock()
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    monkeypatch.setattr(webpush_module, "_send_push_async", _blocked_send)
    monkeypatch.setattr(webpush_module, "process_push_results", process_results)

    task = asyncio.create_task(
        delivery.redeliver_notifications(
            db_session,
            notification_ids=[notification.id],
        )
    )
    await asyncio.wait_for(send_started.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    rows = (
        (
            await db_session.execute(
                select(NotificationDelivery).where(
                    NotificationDelivery.notification_id == notification.id
                )
            )
        )
        .scalars()
        .all()
    )
    persisted = (
        await db_session.execute(
            select(Notification.read).where(Notification.id == notification.id)
        )
    ).scalar_one()

    assert rows == []
    assert persisted is False
    process_results.assert_not_awaited()
