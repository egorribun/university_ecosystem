"""Fallback-value contracts for outbox-driven Web Push delivery."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest

from app.models import NotificationDelivery
from app.services.notifications import delivery


def _rows(values: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


@pytest.mark.asyncio
async def test_deliver_and_process_uses_shared_default_deliverer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The shared boundary must resolve and invoke the default fan-out lazily."""

    expected = delivery.WebPushResult(
        subscription_id=uuid4(),
        endpoint="https://push.example.test/subscription",
        user_id=uuid4(),
        status="sent",
        status_code=201,
    )
    deliverer = AsyncMock(return_value=[expected])
    process = AsyncMock()
    monkeypatch.setattr(
        "app.services.push_service.deliver_push_to_subscriptions", deliverer
    )
    monkeypatch.setattr(delivery.webpush_module, "process_push_results", process)

    payload = {"title": "Test"}
    outcome = await delivery.deliver_and_process_push_results(
        [], payload, topic=None, concurrency=7
    )

    assert outcome == [expected]
    deliverer.assert_awaited_once_with([], payload, topic=None, concurrency=7)
    process.assert_awaited_once_with([expected])


@pytest.mark.asyncio
async def test_redelivery_uses_safe_url_and_unknown_metric_type_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing optional notification fields still produce a valid push payload."""

    user_id = uuid4()
    subscription = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        endpoint="https://push.example.test/subscription",
        topics=None,
    )
    notification = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        title="A notification",
        body=None,
        url=None,
        type=None,
        created_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
    )
    provider_result = delivery.WebPushResult(
        subscription_id=subscription.id,
        endpoint=subscription.endpoint,
        user_id=user_id,
        status="sent",
        status_code=201,
    )
    send = AsyncMock(return_value=provider_result)
    record_delivered = Mock()
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    monkeypatch.setattr(delivery, "subscription_supports_topic", lambda *_args: True)
    monkeypatch.setattr(delivery.webpush_module, "_send_push_async", send)
    monkeypatch.setattr(delivery.webpush_module, "process_push_results", AsyncMock())
    build_row = MagicMock(side_effect=delivery._build_delivery_row)
    monkeypatch.setattr(delivery, "_build_delivery_row", build_row)
    monkeypatch.setattr(
        delivery.metrics, "record_notification_delivered", record_delivered
    )

    db = MagicMock(
        execute=AsyncMock(
            side_effect=[
                _rows([notification]),
                _rows([subscription]),
                _rows([]),
                MagicMock(),
            ]
        ),
        flush=AsyncMock(),
    )

    outcome = await delivery.redeliver_notifications(
        db, notification_ids=[notification.id]
    )

    assert outcome.sent == 1
    payload = send.await_args.args[1]
    assert payload["title"] == notification.title
    assert payload["url"] == "/"
    record_delivered.assert_called_once_with(notification_type="unknown")
    assert build_row.call_args is not None
    assert build_row.call_args.kwargs["delivered"] is True
    assert build_row.call_args.kwargs["detail"] is None
    assert build_row.call_args.kwargs["attempted_at"].tzinfo is UTC
    query = db.execute.await_args_list[0].args[0]
    assert len(query._order_by_clauses) == 1
    assert query._order_by_clauses[0].compare(delivery.Notification.__table__.c.id)


@pytest.mark.asyncio
async def test_redelivery_updates_the_latest_attempt_for_each_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retries must mutate the newest journal row, never an older attempt."""

    user_id = uuid4()
    notification_id = uuid4()
    subscription_id = uuid4()
    subscription = SimpleNamespace(
        id=subscription_id,
        user_id=user_id,
        user=None,
        endpoint="https://push.example.test/subscription",
        topics=None,
    )
    notification = SimpleNamespace(
        id=notification_id,
        user_id=user_id,
        title="A notification",
        body="Body",
        url="/news/1",
        type="news",
        created_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
    )
    older = SimpleNamespace(
        notification_id=notification_id,
        subscription_id=subscription_id,
        status="error",
        attempted_at=datetime(2026, 8, 28, 11, 58, tzinfo=UTC),
        delivered_at=None,
        status_code=503,
        detail="first failure",
    )
    newer = SimpleNamespace(
        notification_id=notification_id,
        subscription_id=subscription_id,
        status="error",
        attempted_at=datetime(2026, 8, 28, 11, 59, tzinfo=UTC),
        delivered_at=None,
        status_code=503,
        detail="latest failure",
    )
    sent = delivery.WebPushResult(
        subscription_id=subscription_id,
        endpoint=subscription.endpoint,
        user_id=user_id,
        status="sent",
        status_code=201,
    )

    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    monkeypatch.setattr(delivery, "subscription_supports_topic", lambda *_args: True)
    monkeypatch.setattr(
        delivery.webpush_module, "_send_push_async", AsyncMock(return_value=sent)
    )
    monkeypatch.setattr(delivery, "_process_canonical_push_results", AsyncMock())
    monkeypatch.setattr(delivery.metrics, "record_notification_delivered", Mock())

    calls = 0

    async def execute(statement: object) -> MagicMock:
        nonlocal calls
        calls += 1
        if calls == 1:
            return _rows([notification])
        if calls == 2:
            return _rows([subscription])
        if calls == 3:
            # A real database honours the ORDER BY clause.  Returning rows in
            # the corresponding order makes this test exercise the observable
            # idempotency contract rather than just inspecting SQL text.
            ordered = bool(getattr(statement, "_order_by_clauses", ()))
            return _rows([newer, older] if ordered else [older, newer])
        raise AssertionError("unexpected database query")

    db = MagicMock(execute=AsyncMock(side_effect=execute), flush=AsyncMock())

    outcome = await delivery.redeliver_notifications(
        db, notification_ids=[notification_id]
    )

    assert outcome.sent == 1
    assert newer.status == "sent"
    assert newer.status_code == 201
    assert older.status == "error"
    assert older.status_code == 503


def test_unique_notification_ids_logs_the_stable_warning_text() -> None:
    """Invalid outbox IDs are observable through one canonical warning."""

    with patch.object(delivery.logger, "warning") as warning:
        assert delivery._unique_notification_ids(["not-a-uuid"]) == []

    warning.assert_called_once_with("Ignoring invalid notification id in outbox event")


def test_redelivery_error_exposes_the_exact_retryable_failure_count() -> None:
    outcome = delivery.NotificationRedeliveryOutcome(retryable_failures=2)

    error = delivery.NotificationRedeliveryError(outcome)

    assert error.outcome is outcome
    assert str(error) == "Web Push redelivery has 2 retryable failure(s)"


@pytest.mark.asyncio
async def test_redelivery_records_exception_metric_with_unknown_type_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider exceptions retain their type label and exception reason."""

    user_id = uuid4()
    subscription = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        user=None,
        endpoint="https://push.example.test/subscription",
        topics=None,
    )
    notification = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        title="A notification",
        body="Body",
        url="/news/1",
        type=None,
        created_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
    )
    failed = Mock()
    build_row = MagicMock(side_effect=delivery._build_delivery_row)
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    monkeypatch.setattr(delivery, "subscription_supports_topic", lambda *_args: True)
    monkeypatch.setattr(
        delivery.webpush_module,
        "_send_push_async",
        AsyncMock(side_effect=RuntimeError("provider down")),
    )
    monkeypatch.setattr(delivery.webpush_module, "process_push_results", AsyncMock())
    monkeypatch.setattr(delivery.metrics, "record_notification_failed", failed)
    monkeypatch.setattr(delivery, "_build_delivery_row", build_row)

    db = MagicMock(
        execute=AsyncMock(
            side_effect=[
                _rows([notification]),
                _rows([subscription]),
                _rows([]),
                MagicMock(),
            ]
        ),
        flush=AsyncMock(),
    )

    outcome = await delivery.redeliver_notifications(
        db, notification_ids=[notification.id]
    )

    assert outcome.retryable_failures == 1
    failed.assert_called_once_with(notification_type="unknown", reason="exception")
    assert build_row.call_count == 1
    row_call = build_row.call_args
    assert row_call.args[:2] == (notification.id, notification.created_at)
    assert row_call.kwargs["subscription_id"] == subscription.id
    assert row_call.kwargs["attempted_at"].tzinfo is UTC
    assert row_call.kwargs["detail"] == "exception:provider down"


@pytest.mark.asyncio
async def test_redelivery_error_result_uses_canonical_unknown_metric_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider error statuses must preserve the public unknown fallback label."""

    user_id = uuid4()
    subscription = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        user=None,
        endpoint="https://push.example.test/subscription",
        topics=None,
    )
    notification = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        title="A notification",
        body="Body",
        url="/news/1",
        type=None,
        created_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
    )
    provider_result = delivery.WebPushResult(
        subscription_id=subscription.id,
        endpoint=subscription.endpoint,
        user_id=user_id,
        status="error",
        status_code=503,
        error="provider rejected",
    )
    failed = Mock()
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    monkeypatch.setattr(delivery, "subscription_supports_topic", lambda *_args: True)
    monkeypatch.setattr(
        delivery.webpush_module,
        "_send_push_async",
        AsyncMock(return_value=provider_result),
    )
    monkeypatch.setattr(delivery.webpush_module, "process_push_results", AsyncMock())
    monkeypatch.setattr(delivery.metrics, "record_notification_failed", failed)
    db = MagicMock(
        execute=AsyncMock(
            side_effect=[
                _rows([notification]),
                _rows([subscription]),
                _rows([]),
                MagicMock(),
            ]
        ),
        flush=AsyncMock(),
    )

    outcome = await delivery.redeliver_notifications(
        db, notification_ids=[notification.id]
    )

    assert outcome.retryable_failures == 1
    failed.assert_called_once_with(notification_type="unknown", reason="error")


@pytest.mark.asyncio
async def test_redelivery_payload_preserves_canonical_topic_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    subscription = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        user=None,
        endpoint="https://push.example.test/subscription",
        topics=None,
    )
    notification = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        title="A notification",
        body="Body",
        url="/news/1",
        type="news",
        created_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
    )
    provider_result = delivery.WebPushResult(
        subscription_id=subscription.id,
        endpoint=subscription.endpoint,
        user_id=user_id,
        status="sent",
        status_code=201,
    )
    send = AsyncMock(return_value=provider_result)
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    monkeypatch.setattr(delivery, "subscription_supports_topic", lambda *_args: True)
    monkeypatch.setattr(
        delivery, "infer_notification_topic", lambda _type: "news.published"
    )
    monkeypatch.setattr(delivery, "normalize_topic", lambda topic: topic)
    monkeypatch.setattr(delivery.webpush_module, "_send_push_async", send)
    monkeypatch.setattr(delivery.webpush_module, "process_push_results", AsyncMock())
    db = MagicMock(
        execute=AsyncMock(
            side_effect=[
                _rows([notification]),
                _rows([subscription]),
                _rows([]),
                MagicMock(),
            ]
        ),
        flush=AsyncMock(),
    )

    outcome = await delivery.redeliver_notifications(
        db, notification_ids=[notification.id]
    )

    assert outcome.sent == 1
    payload = send.await_args.args[1]
    assert payload["topic"] == "news.published"
    assert payload["data"] == {
        "notificationId": str(notification.id),
        "topic": "news.published",
        "type": "news",
        "url": "/news/1",
    }


@pytest.mark.asyncio
async def test_redelivery_gone_result_uses_lowercase_metric_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    subscription = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        user=None,
        endpoint="https://push.example.test/subscription",
        topics=None,
    )
    notification = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        title="A notification",
        body="Body",
        url="/news/1",
        type="news",
        created_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
    )
    provider_result = delivery.WebPushResult(
        subscription_id=subscription.id,
        endpoint=subscription.endpoint,
        user_id=user_id,
        status="gone",
        status_code=410,
        error="expired endpoint",
    )
    failed = Mock()
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    monkeypatch.setattr(delivery, "subscription_supports_topic", lambda *_args: True)
    monkeypatch.setattr(
        delivery.webpush_module,
        "_send_push_async",
        AsyncMock(return_value=provider_result),
    )
    monkeypatch.setattr(delivery.webpush_module, "process_push_results", AsyncMock())
    monkeypatch.setattr(delivery.metrics, "record_notification_failed", failed)
    db = MagicMock(
        execute=AsyncMock(
            side_effect=[
                _rows([notification]),
                _rows([subscription]),
                _rows([]),
                MagicMock(),
            ]
        ),
        flush=AsyncMock(),
    )

    outcome = await delivery.redeliver_notifications(
        db, notification_ids=[notification.id]
    )

    assert outcome.terminal_failures == 1
    failed.assert_called_once_with(notification_type="news", reason="gone")


@pytest.mark.asyncio
async def test_redelivery_continues_after_an_already_delivered_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sent pair must not stop delivery to later subscriptions of the user."""

    user_id = uuid4()
    first = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        user=None,
        endpoint="https://push.example.test/first",
        topics=None,
    )
    second = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        user=None,
        endpoint="https://push.example.test/second",
        topics=None,
    )
    notification = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        title="A notification",
        body="Body",
        url="/news/1",
        type="news",
        created_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
    )
    prior = SimpleNamespace(
        notification_id=notification.id,
        subscription_id=first.id,
        status="sent",
    )
    provider_result = delivery.WebPushResult(
        subscription_id=second.id,
        endpoint=second.endpoint,
        user_id=user_id,
        status="sent",
        status_code=201,
    )
    send = AsyncMock(return_value=provider_result)
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    monkeypatch.setattr(delivery, "subscription_supports_topic", lambda *_args: True)
    monkeypatch.setattr(delivery.webpush_module, "_send_push_async", send)
    monkeypatch.setattr(delivery.webpush_module, "process_push_results", AsyncMock())
    db = MagicMock(
        execute=AsyncMock(
            side_effect=[
                _rows([notification]),
                _rows([first, second]),
                _rows([prior]),
                MagicMock(),
            ]
        ),
        flush=AsyncMock(),
    )

    outcome = await delivery.redeliver_notifications(
        db, notification_ids=[notification.id]
    )

    assert outcome.sent == 1
    assert outcome.already_delivered == 1
    send.assert_awaited_once_with(second, send.await_args.args[1])


@pytest.mark.asyncio
async def test_redelivery_continues_after_an_unsupported_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    unsupported = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        user=None,
        endpoint="https://push.example.test/unsupported",
        topics=[],
    )
    supported = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        user=None,
        endpoint="https://push.example.test/supported",
        topics=["news.published"],
    )
    notification = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        title="A notification",
        body="Body",
        url="/news/1",
        type="news",
        created_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
    )
    provider_result = delivery.WebPushResult(
        subscription_id=supported.id,
        endpoint=supported.endpoint,
        user_id=user_id,
        status="sent",
        status_code=201,
    )
    send = AsyncMock(return_value=provider_result)
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    supports_topic = MagicMock(
        side_effect=lambda subscription, topic: subscription is supported
        and topic == "news.published"
    )
    monkeypatch.setattr(delivery, "subscription_supports_topic", supports_topic)
    monkeypatch.setattr(delivery.webpush_module, "_send_push_async", send)
    monkeypatch.setattr(delivery.webpush_module, "process_push_results", AsyncMock())
    db = MagicMock(
        execute=AsyncMock(
            side_effect=[
                _rows([notification]),
                _rows([unsupported, supported]),
                _rows([]),
                MagicMock(),
            ]
        ),
        flush=AsyncMock(),
    )

    outcome = await delivery.redeliver_notifications(
        db, notification_ids=[notification.id]
    )

    assert outcome.terminal_failures == 1
    assert outcome.sent == 1
    send.assert_awaited_once()
    assert send.await_args.args[0] is supported
    assert supports_topic.call_args_list == [
        ((unsupported, "news.published"),),
        ((supported, "news.published"),),
    ]


@pytest.mark.asyncio
async def test_redelivery_accumulates_retryable_failures_across_all_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    subscription = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        user=None,
        endpoint="https://push.example.test/subscription",
        topics=None,
    )
    notifications = [
        SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            title=f"Notification {index}",
            body="Body",
            url="/news/1",
            type="news",
            created_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
        )
        for index in range(2)
    ]
    results = [
        delivery.WebPushResult(
            subscription_id=subscription.id,
            endpoint=subscription.endpoint,
            user_id=user_id,
            status="error",
            status_code=503,
            error="provider rejected",
        )
        for _ in notifications
    ]
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    monkeypatch.setattr(delivery, "subscription_supports_topic", lambda *_args: True)
    monkeypatch.setattr(
        delivery.webpush_module, "_send_push_async", AsyncMock(side_effect=results)
    )
    monkeypatch.setattr(delivery.webpush_module, "process_push_results", AsyncMock())
    monkeypatch.setattr(delivery.metrics, "record_notification_failed", Mock())
    db = MagicMock(
        execute=AsyncMock(
            side_effect=[
                _rows(notifications),
                _rows([subscription]),
                _rows([]),
                MagicMock(),
            ]
        ),
        flush=AsyncMock(),
    )

    outcome = await delivery.redeliver_notifications(
        db, notification_ids=[item.id for item in notifications]
    )

    assert outcome.retryable_failures == 2


@pytest.mark.asyncio
async def test_redelivery_accumulates_already_delivered_pairs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    subscription = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        user=None,
        endpoint="https://push.example.test/subscription",
        topics=None,
    )
    notifications = [
        SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            title=f"Notification {index}",
            body="Body",
            url="/news/1",
            type="news",
            created_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
        )
        for index in range(2)
    ]
    prior = [
        SimpleNamespace(
            notification_id=item.id,
            subscription_id=subscription.id,
            status="sent",
        )
        for item in notifications
    ]
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    db = MagicMock(
        execute=AsyncMock(
            side_effect=[
                _rows(notifications),
                _rows([subscription]),
                _rows(prior),
            ]
        ),
        flush=AsyncMock(),
    )

    outcome = await delivery.redeliver_notifications(
        db, notification_ids=[item.id for item in notifications]
    )

    assert outcome.already_delivered == 2
    prior_delivery_query = db.execute.await_args_list[2].args[0]
    compiled_prior_query = prior_delivery_query.compile()
    assert "notification_deliveries.channel =" in str(compiled_prior_query)
    assert "webpush" in compiled_prior_query.params.values()
    order_by = tuple(prior_delivery_query._order_by_clauses)
    assert len(order_by) == 1
    assert order_by[0].compare(NotificationDelivery.__table__.c.attempted_at.desc())


@pytest.mark.asyncio
async def test_redelivery_requires_one_provider_result_per_send_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken gather result must fail closed instead of silently dropping sends."""

    user_id = uuid4()
    subscription = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        user=None,
        endpoint="https://push.example.test/subscription",
        topics=None,
    )
    notification = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        title="A notification",
        body="Body",
        url="/news/1",
        type="news",
        created_at=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
    )
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    monkeypatch.setattr(delivery, "subscription_supports_topic", lambda *_args: True)
    monkeypatch.setattr(
        delivery.webpush_module,
        "_send_push_async",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(delivery.asyncio, "gather", AsyncMock(return_value=[]))
    db = MagicMock(
        execute=AsyncMock(
            side_effect=[
                _rows([notification]),
                _rows([subscription]),
                _rows([]),
            ]
        ),
        flush=AsyncMock(),
    )

    with pytest.raises(ValueError, match="zip"):
        await delivery.redeliver_notifications(db, notification_ids=[notification.id])
