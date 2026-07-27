"""Closure test for the single-subscription thread-pool adapter."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services import push_service
from app.services.webpush import WebPushResult


async def test_deliver_to_subscription_delegates_to_thread_pool():
    subscription = MagicMock()
    subscription.id = uuid4()
    subscription.user_id = uuid4()
    payload = {"title": "test"}
    expected = WebPushResult(
        subscription_id=subscription.id,
        endpoint="https://push.example.com",
        user_id=subscription.user_id,
        status="ok",
        error=None,
    )
    run_in_threadpool = AsyncMock(return_value=expected)

    with patch.object(push_service, "run_in_threadpool", new=run_in_threadpool):
        result = await push_service._deliver_to_subscription(subscription, payload)

    assert result is expected
    run_in_threadpool.assert_awaited_once_with(
        push_service.send_web_push,
        subscription,
        payload,
    )


@pytest.mark.asyncio
async def test_deliver_push_returns_empty_when_topic_filters_everything():
    subscription = MagicMock()

    with patch.object(push_service, "subscription_supports_topic", return_value=False):
        result = await push_service.deliver_push_to_subscriptions(
            [subscription], {"title": "test"}, topic="news"
        )

    assert result == []


@pytest.mark.asyncio
async def test_deliver_push_prepares_and_returns_successful_results():
    subscription = MagicMock()
    expected = WebPushResult(
        subscription_id=uuid4(),
        endpoint="https://push.example.com",
        user_id=uuid4(),
        status="sent",
    )
    with (
        patch.object(push_service, "subscription_supports_topic", return_value=True),
        patch(
            "app.services.notifications.prepare_push_payload_for_user",
            return_value={"prepared": True},
        ) as prepare,
        patch.object(
            push_service,
            "_deliver_to_subscription",
            new=AsyncMock(return_value=expected),
        ) as deliver,
    ):
        result = await push_service.deliver_push_to_subscriptions(
            [subscription], {"title": "test"}, topic=None
        )

    assert result == [expected]
    prepare.assert_called_once()
    deliver.assert_awaited_once_with(subscription, {"prepared": True})


@pytest.mark.asyncio
async def test_deliver_push_converts_exceptions_to_error_results():
    subscription = MagicMock()
    with (
        patch.object(push_service, "subscription_supports_topic", return_value=True),
        patch(
            "app.services.notifications.prepare_push_payload_for_user",
            return_value={"title": "test"},
        ),
        patch.object(
            push_service,
            "_deliver_to_subscription",
            new=AsyncMock(side_effect=RuntimeError("push failed")),
        ),
    ):
        result = await push_service.deliver_push_to_subscriptions(
            [subscription], {"title": "test"}, topic=None
        )

    assert len(result) == 1
    assert result[0].status == "error"
    assert result[0].error == "push failed"
