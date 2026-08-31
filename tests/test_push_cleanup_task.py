"""RED contracts for canonical admin Web Push result processing.

These tests intentionally describe the Task 13 contract before the shared
orchestration exists: admin test/broadcast must process the exact delivery
results, and duplicate result entries must not cause duplicate cleanup writes.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.enums import UserRole
from app.services import webpush as webpush_module
from app.services.webpush import WebPushResult


def _request() -> MagicMock:
    request = MagicMock()
    request.client.host = "127.0.0.1"
    return request


def _admin() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = UserRole.ADMIN
    return user


@pytest.mark.asyncio
async def test_send_test_processes_results_after_delivery() -> None:
    """The admin test endpoint must run canonical post-delivery processing."""

    from app.routers import notifications
    from app.schemas.notifications import PushTestRequest

    target = SimpleNamespace(id=uuid.uuid4())
    subscription = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=target.id,
        endpoint="https://push.example.test/sub",
        topics=["system"],
        user=None,
    )
    result = WebPushResult(
        subscription_id=subscription.id,
        endpoint=subscription.endpoint,
        user_id=target.id,
        status="sent",
    )
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [subscription]
    db = AsyncMock()
    db.get.return_value = target
    db.execute.return_value = execute_result

    process = AsyncMock()
    with (
        patch.object(notifications, "enforce_rate_limit", new=AsyncMock()),
        patch.object(
            notifications.settings,
            "VAPID_PRIVATE_KEY",
            "configured",
            create=True,
        ),
        patch.object(
            notifications.settings,
            "VAPID_PUBLIC_KEY",
            "configured",
            create=True,
        ),
        patch.object(notifications.settings, "environment", "test", create=True),
        patch.object(
            notifications,
            "deliver_push_to_subscriptions",
            new=AsyncMock(return_value=[result]),
        ),
        patch.object(webpush_module, "process_push_results", new=process),
    ):
        response = await notifications.send_test(
            _request(), db, _admin(), PushTestRequest(user_id=target.id, topic="system")
        )

    assert response.sent == 1
    process.assert_awaited_once_with([result])


@pytest.mark.asyncio
async def test_broadcast_processes_results_for_each_batch() -> None:
    """Broadcast batches use the same post-delivery result processor."""

    from app.routers import notifications
    from app.schemas.notifications import NotifyBody

    subscription = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        endpoint="https://push.example.test/sub",
        topics=["system"],
        user=None,
    )
    result = WebPushResult(
        subscription_id=subscription.id,
        endpoint=subscription.endpoint,
        user_id=subscription.user_id,
        status="gone",
        status_code=410,
    )
    first = MagicMock()
    first.scalars.return_value.all.return_value = [subscription]
    second = MagicMock()
    second.scalars.return_value.all.return_value = []
    db = AsyncMock()
    db.execute.side_effect = [first, second]
    process = AsyncMock()
    with (
        patch.object(notifications, "enforce_rate_limit", new=AsyncMock()),
        patch.object(
            notifications,
            "deliver_push_to_subscriptions",
            new=AsyncMock(return_value=[result]),
        ),
        patch.object(webpush_module, "process_push_results", new=process),
    ):
        response = await notifications.broadcast(
            NotifyBody(title="Test", body="Body", topic="system"),
            _request(),
            db,
            _admin(),
        )

    assert response.removed == 1
    process.assert_awaited_once_with([result])


@pytest.mark.asyncio
async def test_broadcast_stops_on_malformed_pagination_cursor() -> None:
    """Malformed subscription IDs cannot create an unbounded broadcast loop."""

    from app.routers import notifications
    from app.schemas.notifications import NotifyBody

    subscription = SimpleNamespace(
        id=object(),
        user_id=uuid.uuid4(),
        endpoint="https://push.example.test/sub",
        topics=["system"],
        user=None,
    )
    result = WebPushResult(
        subscription_id=uuid.uuid4(),
        endpoint=subscription.endpoint,
        user_id=subscription.user_id,
        status="sent",
    )
    first = MagicMock()
    first.scalars.return_value.all.return_value = [subscription]
    db = AsyncMock()
    db.execute.return_value = first
    deliver = AsyncMock(return_value=[result])
    with (
        patch.object(notifications, "enforce_rate_limit", new=AsyncMock()),
        patch.object(notifications, "deliver_push_to_subscriptions", new=deliver),
        patch.object(webpush_module, "process_push_results", new=AsyncMock()),
    ):
        response = await notifications.broadcast(
            NotifyBody(title="Test", body="Body", topic="system"),
            _request(),
            db,
            _admin(),
        )

    assert response.sent == 1
    deliver.assert_awaited_once()
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_push_results_deduplicates_status_updates() -> None:
    """Repeated provider results are collapsed before cleanup writes."""

    from app.services.webpush import process_push_results

    subscription_id = uuid.uuid4()
    result = WebPushResult(
        subscription_id=subscription_id,
        endpoint="https://push.example.test/sub",
        user_id=uuid.uuid4(),
        status="sent",
    )
    session = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = session
    with (
        patch.object(webpush_module, "async_session", factory),
        patch.object(
            webpush_module,
            "_ensure_async_sessionmaker",
            new=AsyncMock(),
        ),
    ):
        await process_push_results([result, result])

    assert session.execute.await_count == 1


def test_coalesce_push_results_normalizes_unhashable_status() -> None:
    """Malformed provider statuses must fail closed instead of raising TypeError."""

    subscription_id = uuid.uuid4()
    malformed = WebPushResult(
        subscription_id=subscription_id,
        endpoint="https://push.example.test/sub",
        user_id=None,
        status=[],  # type: ignore[arg-type]
    )

    results = webpush_module.coalesce_push_results([malformed])

    assert len(results) == 1
    assert results[0].subscription_id == subscription_id
    assert results[0].status == "error"


def test_coalesce_push_results_ignores_non_result_values() -> None:
    """Provider adapters cannot make arbitrary values enter the result ledger."""

    subscription_id = uuid.uuid4()
    result = WebPushResult(
        subscription_id=subscription_id,
        endpoint="https://push.example.test/sub",
        user_id=None,
        status="sent",
    )

    assert webpush_module.coalesce_push_results([object(), result]) == [result]


def test_coalesce_push_results_normalizes_string_subscription_id() -> None:
    """Deserialized UUID strings are normalized before deduplication."""

    subscription_id = uuid.uuid4()
    malformed = WebPushResult(
        subscription_id=str(subscription_id),  # type: ignore[arg-type]
        endpoint="https://push.example.test/sub",
        user_id=None,
        status="sent",
    )

    results = webpush_module.coalesce_push_results([malformed])

    assert results[0].subscription_id == subscription_id
    assert isinstance(results[0].subscription_id, uuid.UUID)


def test_coalesce_push_results_discards_invalid_subscription_id() -> None:
    """An invalid adapter UUID is ignored rather than entering cleanup writes."""

    malformed = WebPushResult(
        subscription_id="not-a-uuid",  # type: ignore[arg-type]
        endpoint="https://push.example.test/sub",
        user_id=None,
        status="sent",
    )

    assert webpush_module.coalesce_push_results([malformed]) == []


def test_coalesce_push_results_keeps_highest_priority_duplicate() -> None:
    """Terminal ``gone``/successful results replace a transient duplicate."""

    subscription_id = uuid.uuid4()
    transient = WebPushResult(
        subscription_id=subscription_id,
        endpoint="https://push.example.test/sub",
        user_id=None,
        status="error",
    )
    sent = WebPushResult(
        subscription_id=subscription_id,
        endpoint="https://push.example.test/sub",
        user_id=None,
        status="sent",
    )

    results = webpush_module.coalesce_push_results([transient, sent])

    assert results == [sent]
