"""Focused closure tests for push notification router defensive paths."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from tests.conftest import call_injected


def _result(*, scalar_one_or_none=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    return result


def _subscription(**overrides):
    values = {
        "id": uuid.uuid4(),
        "endpoint": "https://push.example.com/device",
        "user_id": None,
        "created_at": None,
        "topics": ["news.published"],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def _bind(subscription, *, user_id, requested_topics=None, user_agent=""):
    from app.routers import notifications

    db = AsyncMock()
    now = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    with (
        patch.object(
            notifications,
            "resolve_subscription_topics_for_user",
            new=AsyncMock(return_value=("events.published",)),
        ) as resolver,
        patch.object(notifications, "logger") as logger,
    ):
        await notifications._bind_subscription_to_user(
            db,
            subscription,
            user_id=user_id,
            p256dh="p256dh",
            auth="auth",
            user_agent=user_agent,
            now=now,
            requested_topics=requested_topics,
        )
    return db, resolver, logger, now


@pytest.mark.asyncio
async def test_binding_transfers_endpoint_to_caller_preferences():
    previous, caller = uuid.uuid4(), uuid.uuid4()
    created = datetime(2026, 1, 1, tzinfo=UTC)
    endpoint = "https://push.example.com/" + "d" * 80
    subscription = _subscription(
        user_id=previous, created_at=created, endpoint=endpoint
    )

    db, resolver, logger, now = await _bind(subscription, user_id=caller)

    assert subscription.user_id == caller
    assert subscription.topics == ["events.published"]
    assert subscription.p256dh == "p256dh"
    assert subscription.auth == "auth"
    assert subscription.user_agent is None
    assert subscription.last_seen_at == now
    assert subscription.created_at == created
    db.flush.assert_awaited_once()
    resolver.assert_awaited_once_with(db, user_id=caller, requested_topics=None)
    logger.info.assert_called_once_with(
        "push.subscribe.owner_changed",
        extra={"subscription_id": subscription.id, "endpoint_prefix": endpoint[:50]},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", ["caller", "unowned"])
async def test_binding_does_not_report_a_transfer_without_a_new_owner(owner):
    caller = uuid.uuid4()
    subscription = _subscription(user_id=caller if owner == "caller" else None)

    db, resolver, logger, _now = await _bind(
        subscription,
        user_id=caller,
        requested_topics=["news.published"],
        user_agent="Firefox/140",
    )

    assert subscription.created_at is None
    assert subscription.user_agent == "Firefox/140"
    resolver.assert_awaited_once_with(
        db, user_id=caller, requested_topics=["news.published"]
    )
    logger.info.assert_not_called()


@pytest.mark.asyncio
async def test_final_integrity_recovery_binds_the_endpoint_to_the_caller():
    from app.routers import notifications
    from app.schemas.notifications import PushSubscriptionIn

    previous, caller = uuid.uuid4(), uuid.uuid4()
    existing = _subscription(user_id=previous)
    payload = PushSubscriptionIn(
        endpoint="https://push.example.com/device",
        keys={"p256dh": "p256dh", "auth": "auth"},
    )
    request = MagicMock()
    request.client = None
    request.headers.get.return_value = None
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.side_effect = [_result() for _ in range(3)] + [
        _result(scalar_one_or_none=existing)
    ]
    db.flush.side_effect = [
        IntegrityError("insert", {}, RuntimeError("duplicate")) for _ in range(3)
    ] + [None]

    with (
        patch.object(
            notifications,
            "_validate_subscription_payload",
            new=AsyncMock(return_value=("https://push.example.com/device", "k", "a")),
        ),
        patch.object(notifications, "enforce_rate_limit", new=AsyncMock()),
        patch.object(notifications.asyncio, "sleep", new=AsyncMock()),
        patch.object(
            notifications,
            "resolve_subscription_topics_for_user",
            new=AsyncMock(return_value=["events.published"]),
        ) as resolver,
        patch.object(
            notifications, "_serialize_subscription", new=MagicMock(return_value="ok")
        ),
    ):
        result = await call_injected(
            notifications.subscribe,
            payload=payload,
            request=request,
            user=SimpleNamespace(id=caller),
            provides={"AsyncDatabaseSession": db},
        )

    assert result == "ok"
    assert existing.user_id == caller
    assert existing.topics == ["events.published"]
    resolver.assert_awaited_once_with(db, user_id=caller, requested_topics=None)
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(existing)


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
            await call_injected(
                notifications.subscribe,
                payload=payload,
                request=request,
                user=user,
                provides={"AsyncDatabaseSession": db},
            )

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_subscription_validation_rejects_private_resolution_failure():
    from app.routers import notifications
    from app.schemas.notifications import PushSubscriptionIn

    payload = PushSubscriptionIn(
        endpoint="https://push.example.com/subscription",
        keys={"p256dh": "public-key", "auth": "auth-key"},
    )
    with (
        patch.object(
            notifications,
            "validate_url_not_internal_async",
            new=AsyncMock(side_effect=ValueError("SSRF blocked")),
        ),
        patch.object(
            notifications,
            "settings",
            SimpleNamespace(is_development=False),
        ),
    ):
        with pytest.raises(notifications.HTTPException) as exc:
            await notifications._validate_subscription_payload(payload, locale="en")

    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "invalid_subscription"
    assert exc.value.detail["fields"][0]["field"] == "endpoint"


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
        assert await call_injected(
            notifications.unsubscribe,
            payload=PushSubscriptionDelete(endpoint="endpoint"),
            request=request,
            user=user,
            provides={"AsyncDatabaseSession": db},
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
        result = await call_injected(
            notifications.send_test,
            request=request,
            user=user,
            payload=None,
            provides={"AsyncDatabaseSession": db},
        )

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
            await call_injected(
                notifications.unsubscribe,
                payload=PushSubscriptionDelete(endpoint="https://push.example/sub"),
                request=request,
                user=user,
                provides={"AsyncDatabaseSession": AsyncMock()},
            )

    assert exc.value.status_code == 429
    assert exc.value.detail["retry_after"] == 17
