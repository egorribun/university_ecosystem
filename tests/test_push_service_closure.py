"""Closure test for the single-subscription thread-pool adapter."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

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
