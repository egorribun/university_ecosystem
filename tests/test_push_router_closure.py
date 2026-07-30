"""Focused closure tests for push notification router defensive paths."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError


class _NestedTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


def _result(*, scalars=None, scalar_one_or_none=None):
    result = MagicMock()
    result.scalars.return_value = scalars if scalars is not None else []
    result.scalar_one_or_none.return_value = scalar_one_or_none
    return result


@pytest.mark.asyncio
async def test_refresh_topics_recovers_from_integrity_race_for_update_and_delete():
    from app.routers import notifications

    user_id = uuid.uuid4()
    existing = MagicMock(topics=[])
    db = AsyncMock()
    db.add = MagicMock()
    db.begin_nested = MagicMock(return_value=_NestedTransaction())
    db.execute.side_effect = [
        _result(scalars=[["news"]]),
        _result(scalar_one_or_none=existing),
        _result(scalar_one_or_none=existing),
    ]
    db.flush.side_effect = [
        IntegrityError("insert", {}, RuntimeError("duplicate")),
        None,
    ]

    await notifications._refresh_user_topic_preferences(db, user_id=user_id)

    assert existing.topics == ["news"]
    db.flush.assert_awaited()

    existing.topics = ["old"]
    db.execute.side_effect = [
        _result(scalars=[None]),
        _result(scalar_one_or_none=existing),
        _result(scalar_one_or_none=existing),
    ]
    db.flush.side_effect = [
        IntegrityError("delete", {}, RuntimeError("duplicate")),
        None,
    ]

    await notifications._refresh_user_topic_preferences(db, user_id=user_id)

    db.delete.assert_awaited_with(existing)

    db.execute.side_effect = [
        _result(scalars=[["news"]]),
        _result(scalar_one_or_none=None),
        _result(scalar_one_or_none=None),
    ]
    db.flush.side_effect = [
        IntegrityError("insert", {}, RuntimeError("duplicate")),
    ]
    await notifications._refresh_user_topic_preferences(db, user_id=user_id)


@pytest.mark.asyncio
async def test_subscribe_defensive_failure_and_missing_client_host():
    from app.routers import notifications

    payload = MagicMock(user_agent=None, topics=[])
    request = MagicMock()
    request.client = None
    request.headers.get.return_value = None
    db = AsyncMock()
    user = MagicMock(id=uuid.uuid4())

    with (
        patch.object(
            notifications,
            "_validate_subscription_payload",
            new=AsyncMock(return_value=("endpoint", "p256dh", "auth")),
        ),
        patch.object(notifications, "enforce_rate_limit", new=AsyncMock()),
        patch.object(notifications, "range", lambda *_args: (), create=True),
    ):
        with pytest.raises(notifications.HTTPException) as exc:
            await notifications.subscribe(payload, request, db, user)

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_unsubscribe_and_send_test_cover_missing_client_and_optional_payload():
    from app.models.enums import UserRole
    from app.routers import notifications
    from app.schemas.notifications import PushSubscriptionDelete

    request = MagicMock()
    request.client = None
    user = MagicMock(id=uuid.uuid4(), role=UserRole.ADMIN)
    db = AsyncMock()
    empty_result = _result(scalar_one_or_none=None)
    db.execute.return_value = empty_result
    with (
        patch.object(notifications, "resolve_locale", return_value="en"),
        patch.object(notifications, "enforce_rate_limit", new=AsyncMock()),
    ):
        assert await notifications.unsubscribe(
            PushSubscriptionDelete(endpoint="endpoint"), request, db, user
        ) == {"ok": True, "removed": False}

    target = MagicMock(id=user.id)
    db.get.return_value = target
    subscriptions_result = MagicMock()
    subscriptions_result.scalars.return_value.all.return_value = [
        SimpleNamespace(endpoint="endpoint", id=uuid.uuid4())
    ]
    db.execute = AsyncMock(return_value=subscriptions_result)
    settings = MagicMock(
        VAPID_PRIVATE_KEY="private",  # pragma: allowlist secret
        VAPID_PUBLIC_KEY="public",
        environment="test",
    )
    with (
        patch.object(notifications, "resolve_locale", return_value="en"),
        patch.object(notifications, "enforce_rate_limit", new=AsyncMock()),
        patch.object(notifications, "settings", settings),
        patch.object(
            notifications,
            "deliver_push_to_subscriptions",
            new=AsyncMock(return_value=[]),
        ),
    ):
        result = await notifications.send_test(request, db, user, None)

    assert result.total == 0
    assert result.sent == 0


@pytest.mark.asyncio
async def test_unsubscribe_rate_limit_returns_retry_after():
    from app.core.ratelimit import RateLimitExceeded, RateLimitInfo
    from app.routers import notifications
    from app.schemas.notifications import PushSubscriptionDelete

    request = MagicMock()
    request.client = SimpleNamespace(host="127.0.0.1")
    user = SimpleNamespace(id=uuid.uuid4())

    with (
        patch.object(notifications, "resolve_locale", return_value="en"),
        patch.object(
            notifications,
            "enforce_rate_limit",
            new=AsyncMock(side_effect=RateLimitExceeded(RateLimitInfo(False, 0, 17))),
        ),
    ):
        with pytest.raises(notifications.HTTPException) as exc:
            await notifications.unsubscribe(
                PushSubscriptionDelete(endpoint="https://push.example/sub"),
                request,
                AsyncMock(),
                user,
            )

    assert exc.value.status_code == 429
    assert exc.value.detail["retry_after"] == 17
