"""Fallback-value contracts for outbox-driven Web Push delivery."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest

from app.services.notifications import delivery


def _rows(values: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


@pytest.mark.asyncio
async def test_redelivery_uses_safe_url_and_unknown_metric_type_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing optional notification fields still produce a valid push payload."""

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
    assert payload["url"] == "/"
    record_delivered.assert_called_once_with(notification_type="unknown")
