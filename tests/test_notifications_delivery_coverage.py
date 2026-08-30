"""Behavior and failure-path tests for notification delivery services.

Targets the previously-uncovered branches of ``create_notifications_for_users``:
user_filter exclusion, push-disabled early return, skipped_no_subscription,
payload badge/tag/actions normalization, skipped_topic, sent/error/exception
delivery rows and the grade-cache invalidation hook.

Harness mirrors tests/test_notifications_service.py (``configured_push_settings``
vapid fixture + ``send_web_push`` monkeypatch via the module-level override the
production code explicitly supports at delivery.py L264-277).
"""

from __future__ import annotations

import typing
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import insert, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Notification, NotificationDelivery, PushSubscription
from app.services import stats_cache
from app.services import webpush as webpush_module
from app.services.notifications import delivery as notifications_delivery
from app.services.notifications.core import _build_delivery_row
from app.services.notifications.delivery import create_notifications_for_users
from app.services.webpush import WebPushResult


def _reset_vapid_cache() -> None:
    for cached in ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "WEBPUSH_SUBJECT"):
        settings.__dict__.pop(cached, None)


@pytest.fixture
def push_configured(monkeypatch: pytest.MonkeyPatch) -> typing.Generator[None]:
    _reset_vapid_cache()
    monkeypatch.setattr(settings, "vapid_public_key", "test-public-key")
    monkeypatch.setattr(settings, "vapid_private_key", "test-private-key")
    monkeypatch.setattr(settings, "vapid_subject", "mailto:test@example.com")
    yield
    _reset_vapid_cache()


@pytest.fixture
def push_disabled(monkeypatch: pytest.MonkeyPatch) -> typing.Generator[None]:
    _reset_vapid_cache()
    monkeypatch.setattr(settings, "vapid_public_key", "")
    monkeypatch.setattr(settings, "vapid_private_key", "")
    yield
    _reset_vapid_cache()


async def _add_subscription(db: AsyncSession, user_id: uuid.UUID) -> PushSubscription:
    sub = PushSubscription(
        user_id=user_id,
        endpoint=f"https://push.example.com/{uuid.uuid4().hex}",
        p256dh="p256dh-key",  # pragma: allowlist secret
        auth="auth-key",  # pragma: allowlist secret
        created_at=datetime.now(UTC),
        topics=[],
    )
    db.add(sub)
    await db.flush()
    return sub


async def _add_notification(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    title: str = "Published",
) -> Notification:
    notification = Notification(
        user_id=user_id,
        title=title,
        title_en=f"{title} EN",
        body="Body",
        body_en="Body EN",
        type="news",
        url="/news/42",
        created_at=datetime.now(UTC),
        read=False,
    )
    db.add(notification)
    await db.flush()
    return notification


async def _delivery_rows_for_user(
    db: AsyncSession, user_id: uuid.UUID
) -> list[NotificationDelivery]:
    notif_ids = (
        (
            await db.execute(
                select(Notification.id).where(Notification.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    if not notif_ids:
        return []
    rows = await db.execute(
        select(NotificationDelivery).where(
            NotificationDelivery.notification_id.in_(notif_ids)
        )
    )
    return list(rows.scalars().all())


def test_delivery_rows_have_a_uniform_postgresql_insert_shape() -> None:
    """Mixed delivery outcomes must compile as one PostgreSQL multi-row insert.

    SQLAlchemy's PostgreSQL compiler rejects heterogeneous ``values`` mappings
    when one row omits a nullable column that another row supplies.  Broadcast
    fan-out legitimately mixes successful (status code only) and failed
    (detail only) deliveries, so the row builder must include both optional
    columns consistently.
    """

    notification_id = uuid.uuid4()
    created_at = datetime.now(UTC)
    rows = [
        _build_delivery_row(
            notification_id,
            created_at,
            status="sent",
            status_code=201,
        ),
        _build_delivery_row(
            notification_id,
            created_at,
            status="error",
            detail="provider unavailable",
        ),
    ]

    compiled = (
        insert(NotificationDelivery).values(rows).compile(dialect=postgresql.dialect())
    )
    assert "status_code" in compiled.string
    assert "detail" in compiled.string


@pytest.fixture
def no_process_results(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(_results):
        return None

    monkeypatch.setattr(webpush_module, "process_push_results", _noop)


# ---------------------------------------------------------------------------
# Early returns
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_user_ids_returns_zero(db_session):
    created = await create_notifications_for_users(db_session, title="T", user_ids=[])
    assert created == 0


@pytest.mark.asyncio
async def test_user_filter_retaining_user_continues_to_notification_insert(monkeypatch):
    user_id = uuid.uuid4()
    filtered_rows = MagicMock()
    filtered_rows.scalars.return_value.all.return_value = [user_id]
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[filtered_rows, MagicMock()])
    db.flush = AsyncMock()
    db.add = MagicMock()
    monkeypatch.setattr(notifications_delivery, "_is_push_configured", lambda: False)

    def _retain_user(stmt):
        return stmt

    assert (
        await create_notifications_for_users(
            db,
            title="Filtered",
            user_ids=[user_id],
            user_filter=_retain_user,
        )
        == 1
    )
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_user_filter_excluding_all_returns_zero(db_session, user_factory):
    user = await user_factory()

    def _exclude_all(stmt):
        return stmt.where(False)

    created = await create_notifications_for_users(
        db_session,
        title="Filtered",
        user_ids=[user.id],
        user_filter=_exclude_all,
    )
    assert created == 0
    notifs = await _delivery_rows_for_user(db_session, user.id)
    assert notifs == []


@pytest.mark.asyncio
async def test_push_disabled_creates_notifications_without_deliveries(
    db_session, user_factory, push_disabled
):
    user = await user_factory()
    created = await create_notifications_for_users(
        db_session, title="In-app only", user_ids=[user.id]
    )
    assert created == 1
    notif = (
        await db_session.execute(
            select(Notification).where(Notification.user_id == user.id)
        )
    ).scalar_one()
    assert notif.title == "In-app only"
    assert await _delivery_rows_for_user(db_session, user.id) == []


# ---------------------------------------------------------------------------
# Push-enabled paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_subscription_records_skipped_row(
    db_session, user_factory, push_configured
):
    user = await user_factory()
    created = await create_notifications_for_users(
        db_session, title="No subs", user_ids=[user.id]
    )
    assert created == 1
    rows = await _delivery_rows_for_user(db_session, user.id)
    assert [r.status for r in rows] == ["skipped_no_subscription"]


@pytest.mark.asyncio
async def test_sent_path_normalizes_payload(
    db_session, user_factory, push_configured, no_process_results, monkeypatch
):
    user = await user_factory()
    sub = await _add_subscription(db_session, user.id)
    payloads: list[dict] = []

    def _fake_send(s: PushSubscription, payload: dict[str, object]) -> WebPushResult:
        payloads.append(dict(payload))
        return WebPushResult(
            subscription_id=s.id,
            endpoint=s.endpoint,
            user_id=s.user_id,
            status="sent",
            status_code=201,
        )

    monkeypatch.setattr(notifications_delivery, "send_web_push", _fake_send)

    created = await create_notifications_for_users(
        db_session,
        title="Rich",
        body="Body",
        url="/rich",
        badge="/badge.png",
        tag="rich-tag",
        payload_data={"extra": "value"},
        actions=[
            {"action": "open", "title": "Open", "icon": "/i.png", "junk": "drop"},
            {"action": "no-title"},  # filtered: missing title
        ],
        user_ids=[user.id],
        topic="system.release",
    )
    assert created == 1

    rows = await _delivery_rows_for_user(db_session, user.id)
    assert len(rows) == 1
    assert rows[0].status == "sent"
    assert rows[0].delivered_at is not None
    assert rows[0].subscription_id == sub.id

    assert len(payloads) == 1
    sent_payload = payloads[0]
    assert sent_payload["badge"] == "/badge.png"
    assert sent_payload["tag"] == str(sent_payload["data"]["notificationId"])
    assert sent_payload["data"] == {
        "extra": "value",
        "notificationId": str(sent_payload["data"]["notificationId"]),
        "topic": "system.release",
        "type": None,
        "url": "/rich",
    }
    assert sent_payload["actions"] == [
        {"action": "open", "title": "Open", "icon": "/i.png"}
    ]
    assert sent_payload["topic"] == "system.release"


@pytest.mark.asyncio
async def test_error_result_records_error_row(
    db_session, user_factory, push_configured, no_process_results, monkeypatch
):
    user = await user_factory()
    await _add_subscription(db_session, user.id)

    def _fake_send(s: PushSubscription, payload: dict[str, object]) -> WebPushResult:
        return WebPushResult(
            subscription_id=s.id,
            endpoint=s.endpoint,
            user_id=s.user_id,
            status="error",
            status_code=500,
            error="boom",
        )

    monkeypatch.setattr(notifications_delivery, "send_web_push", _fake_send)

    await create_notifications_for_users(db_session, title="Err", user_ids=[user.id])
    rows = await _delivery_rows_for_user(db_session, user.id)
    assert [r.status for r in rows] == ["error"]
    assert rows[0].delivered_at is None
    assert rows[0].detail == "boom"


@pytest.mark.asyncio
async def test_send_exception_records_exception_row(
    db_session, user_factory, push_configured, no_process_results, monkeypatch
):
    user = await user_factory()
    await _add_subscription(db_session, user.id)

    def _raise_send(s: PushSubscription, payload: dict[str, object]) -> WebPushResult:
        raise RuntimeError("push exploded")

    monkeypatch.setattr(notifications_delivery, "send_web_push", _raise_send)

    await create_notifications_for_users(db_session, title="Boom", user_ids=[user.id])
    rows = await _delivery_rows_for_user(db_session, user.id)
    assert [r.status for r in rows] == ["error"]
    assert rows[0].detail is not None
    assert rows[0].detail.startswith("exception:")


@pytest.mark.asyncio
async def test_unsupported_topic_records_skipped_topic_row(
    db_session, user_factory, push_configured, no_process_results, monkeypatch
):
    user = await user_factory()
    await _add_subscription(db_session, user.id)
    monkeypatch.setattr(
        notifications_delivery,
        "subscription_supports_topic",
        lambda _sub, _topic: False,
    )

    sent_calls: list = []

    def _fake_send(s, payload):
        sent_calls.append(payload)
        return WebPushResult(
            subscription_id=s.id,
            endpoint=s.endpoint,
            user_id=s.user_id,
            status="sent",
        )

    monkeypatch.setattr(notifications_delivery, "send_web_push", _fake_send)

    await create_notifications_for_users(
        db_session, title="Topic", user_ids=[user.id], topic="news"
    )
    rows = await _delivery_rows_for_user(db_session, user.id)
    assert [r.status for r in rows] == ["skipped_topic"]
    assert sent_calls == []


@pytest.mark.asyncio
async def test_grade_type_invalidates_stats_cache(
    db_session, user_factory, push_disabled, monkeypatch
):
    user = await user_factory()
    invalidate = AsyncMock()
    monkeypatch.setattr(stats_cache, "invalidate_user_stats_cache", invalidate)

    await create_notifications_for_users(
        db_session, title="Grade!", type="grade", user_ids=[user.id]
    )
    invalidate.assert_awaited_once()
    kwargs = invalidate.await_args.kwargs
    assert kwargs["user_ids"] == [user.id]
    assert kwargs["kinds"] == ("grades",)


@pytest.mark.asyncio
async def test_translations_populate_localized_columns(
    db_session, user_factory, push_disabled
):
    user = await user_factory()
    await create_notifications_for_users(
        db_session,
        title="Fallback title",
        body="Fallback body",
        title_translations={"ru": "Заголовок", "en": "Title-EN", "xx": "skip"},
        body_translations={"ru": "Тело", "en": "Body-EN"},
        user_ids=[user.id],
    )
    notif = (
        await db_session.execute(
            select(Notification).where(Notification.user_id == user.id)
        )
    ).scalar_one()
    assert notif.title == "Заголовок"
    assert notif.title_en == "Title-EN"
    assert notif.body == "Тело"
    assert notif.body_en == "Body-EN"


@pytest.mark.asyncio
async def test_outbox_event_created_on_delivery(
    db_session, user_factory, push_configured, no_process_results, monkeypatch
):
    from sqlalchemy import delete

    from app.models.domain_events import StoredEvent

    user = await user_factory()
    await _add_subscription(db_session, user.id)

    def _fake_send(s, payload):
        return WebPushResult(
            subscription_id=s.id,
            endpoint=s.endpoint,
            user_id=s.user_id,
            status="sent",
            status_code=201,
        )

    monkeypatch.setattr(notifications_delivery, "send_web_push", _fake_send)

    # Clean out any old stored events
    await db_session.execute(delete(StoredEvent))

    created = await create_notifications_for_users(
        db_session,
        title="Outbox Test",
        user_ids=[user.id],
    )
    assert created == 1

    # Check outbox events in DB
    events = (await db_session.execute(select(StoredEvent))).scalars().all()
    assert len(events) == 1
    assert events[0].event_type == "notification.delivery_requested"
    assert "notification_ids" in events[0].payload


@pytest.mark.asyncio
async def test_webpush_timeout_records_error(
    db_session, user_factory, push_configured, no_process_results, monkeypatch
):
    user = await user_factory()
    await _add_subscription(db_session, user.id)

    def _timeout_send(s, payload):
        raise TimeoutError("simulate timeout")

    monkeypatch.setattr(notifications_delivery, "send_web_push", _timeout_send)

    await create_notifications_for_users(
        db_session,
        title="Timeout Test",
        user_ids=[user.id],
    )

    rows = await _delivery_rows_for_user(db_session, user.id)
    assert len(rows) == 1
    assert rows[0].status == "error"
    assert "push delivery timed out" in rows[0].detail


@pytest.mark.asyncio
async def test_delivery_ignores_subscriptions_without_matching_notification(
    monkeypatch,
):
    user_id = uuid.uuid4()
    orphan_subscription = SimpleNamespace(user_id=None, id=uuid.uuid4())
    unrelated_subscription = SimpleNamespace(user_id=uuid.uuid4(), id=uuid.uuid4())
    subscriptions = MagicMock()
    subscriptions.scalars.return_value = [orphan_subscription, unrelated_subscription]
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[MagicMock(), subscriptions])
    db.flush = AsyncMock()
    db.add = MagicMock()
    monkeypatch.setattr(notifications_delivery, "_is_push_configured", lambda: True)

    assert (
        await create_notifications_for_users(db, title="No match", user_ids=[user_id])
        == 1
    )
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_default_webpush_path_handles_empty_normalized_actions(monkeypatch):
    user_id = uuid.uuid4()
    subscription = SimpleNamespace(
        user_id=user_id,
        id=uuid.uuid4(),
        endpoint="https://push.example.test/subscription",
        user=None,
    )
    subscriptions = MagicMock()
    subscriptions.scalars.return_value = [subscription]
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[MagicMock(), subscriptions, MagicMock()])
    db.flush = AsyncMock()
    db.add = MagicMock()
    result = WebPushResult(
        subscription_id=subscription.id,
        endpoint=subscription.endpoint,
        user_id=user_id,
        status="sent",
    )
    send_async = AsyncMock(return_value=result)
    process_results = AsyncMock()
    monkeypatch.setattr(notifications_delivery, "_is_push_configured", lambda: True)
    monkeypatch.setattr(
        notifications_delivery,
        "subscription_supports_topic",
        lambda _sub, _topic: True,
    )
    monkeypatch.setattr(
        notifications_delivery,
        "prepare_push_payload_for_user",
        lambda payload, _user: payload,
    )
    monkeypatch.setattr(webpush_module, "_send_push_async", send_async)
    monkeypatch.setattr(webpush_module, "process_push_results", process_results)

    created = await create_notifications_for_users(
        db,
        title="Default path",
        actions=[{"action": "missing-title"}],
        user_ids=[user_id],
    )

    assert created == 1
    send_async.assert_awaited_once()
    process_results.assert_awaited_once()


@pytest.mark.asyncio
async def test_outbox_redelivery_is_idempotent_by_notification_and_subscription(
    db_session,
    user_factory,
    push_configured,
    no_process_results,
    monkeypatch,
):
    user = await user_factory()
    subscription = await _add_subscription(db_session, user.id)
    notification = await _add_notification(db_session, user.id)
    payloads: list[dict[str, object]] = []

    async def _send(sub: PushSubscription, payload: dict[str, object]) -> WebPushResult:
        payloads.append(payload)
        return WebPushResult(
            subscription_id=sub.id,
            endpoint=sub.endpoint,
            user_id=sub.user_id,
            status="sent",
            status_code=201,
        )

    monkeypatch.setattr(webpush_module, "_send_push_async", _send)

    first = await notifications_delivery.redeliver_notifications(
        db_session,
        notification_ids=[notification.id, notification.id],
        channel="push",
    )
    second = await notifications_delivery.redeliver_notifications(
        db_session,
        notification_ids=[notification.id],
        channel="push",
    )

    assert first.sent == 1
    assert first.retryable_failures == 0
    assert second.sent == 0
    assert second.already_delivered == 1
    assert len(payloads) == 1
    assert payloads[0]["tag"] == str(notification.id)
    assert payloads[0]["data"] == {
        "notificationId": str(notification.id),
        "topic": "news.published",
        "type": "news",
        "url": "/news/42",
    }
    rows = await _delivery_rows_for_user(db_session, user.id)
    assert [(row.status, row.subscription_id) for row in rows] == [
        ("sent", subscription.id)
    ]
    assert rows[0].status_code == 201


@pytest.mark.asyncio
async def test_outbox_redelivery_retries_only_failed_recipients(
    db_session,
    user_factory,
    push_configured,
    no_process_results,
    monkeypatch,
):
    first_user = await user_factory()
    second_user = await user_factory()
    first_sub = await _add_subscription(db_session, first_user.id)
    second_sub = await _add_subscription(db_session, second_user.id)
    first_notification = await _add_notification(db_session, first_user.id)
    second_notification = await _add_notification(db_session, second_user.id)
    calls: list[uuid.UUID] = []

    async def _partially_failing_send(
        sub: PushSubscription, _payload: dict[str, object]
    ) -> WebPushResult:
        calls.append(sub.id)
        status = "sent" if sub.id == first_sub.id else "error"
        return WebPushResult(
            subscription_id=sub.id,
            endpoint=sub.endpoint,
            user_id=sub.user_id,
            status=status,
            status_code=201 if status == "sent" else 503,
            error=None if status == "sent" else "provider unavailable",
        )

    monkeypatch.setattr(webpush_module, "_send_push_async", _partially_failing_send)
    first = await notifications_delivery.redeliver_notifications(
        db_session,
        notification_ids=[first_notification.id, second_notification.id],
    )
    await db_session.flush()

    async def _successful_retry(
        sub: PushSubscription, _payload: dict[str, object]
    ) -> WebPushResult:
        calls.append(sub.id)
        return WebPushResult(
            subscription_id=sub.id,
            endpoint=sub.endpoint,
            user_id=sub.user_id,
            status="sent",
            status_code=201,
        )

    monkeypatch.setattr(webpush_module, "_send_push_async", _successful_retry)
    second = await notifications_delivery.redeliver_notifications(
        db_session,
        notification_ids=[first_notification.id, second_notification.id],
    )

    assert first.sent == 1
    assert first.retryable_failures == 1
    assert second.sent == 1
    assert second.already_delivered == 1
    assert calls.count(first_sub.id) == 1
    assert calls.count(second_sub.id) == 2
    second_rows = await _delivery_rows_for_user(db_session, second_user.id)
    assert len(second_rows) == 1
    assert second_rows[0].delivered_at is not None
    assert second_rows[0].status_code == 201


@pytest.mark.asyncio
async def test_outbox_redelivery_treats_stale_subscription_as_terminal(
    db_session,
    user_factory,
    push_configured,
    monkeypatch,
):
    user = await user_factory()
    await _add_subscription(db_session, user.id)
    notification = await _add_notification(db_session, user.id)
    processed = AsyncMock()

    async def _gone(
        sub: PushSubscription, _payload: dict[str, object]
    ) -> WebPushResult:
        return WebPushResult(
            subscription_id=sub.id,
            endpoint=sub.endpoint,
            user_id=sub.user_id,
            status="gone",
            status_code=410,
            error="expired endpoint",
        )

    monkeypatch.setattr(webpush_module, "_send_push_async", _gone)
    monkeypatch.setattr(webpush_module, "process_push_results", processed)

    outcome = await notifications_delivery.redeliver_notifications(
        db_session,
        notification_ids=[notification.id],
    )

    assert outcome.sent == 0
    assert outcome.retryable_failures == 0
    assert outcome.terminal_failures == 1
    processed.assert_awaited_once()
    assert processed.await_args.args[0][0].status == "gone"
