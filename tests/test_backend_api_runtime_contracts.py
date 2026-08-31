"""Cross-cutting backend API runtime contract tests."""

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, Response
from sqlalchemy.exc import IntegrityError, NoSuchTableError, SQLAlchemyError
from starlette.websockets import WebSocketDisconnect

import app.api.notifications as notifications_api
import app.api.spotify as spotify_api
import app.api.users as users_api
import app.api.websocket as websocket_api
import app.core.metrics as metrics_core
import app.core.observability as observability_core

# Target imports
import app.routers.notifications as push_router
from app.models import PushSubscription, UserPushTopic
from app.models.enums import UserRole


# Helper to mock Dishka container on request
def setup_dishka_mock(request, db, audit=None):
    container = MagicMock()

    async def mock_get(dep_type, *args, **kwargs):
        if "AuditService" in str(dep_type):
            return audit or MagicMock()
        return db

    container.get = mock_get
    request.state.dishka_container = container


# =========================================================================
# 1. app/routers/notifications.py
# =========================================================================


@pytest.mark.asyncio
async def test_subscribe_existing_subscription_update():
    from app.schemas.notifications import PushSubscriptionIn

    payload = PushSubscriptionIn(
        endpoint="https://updates.push.services.mozilla.com/wpush/v2/gAAAAA",
        keys={"p256dh": "BEl62vOgw1...", "auth": "qQX4S..."},
        topics=["system"],
    )
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = MagicMock()
    request.headers.get.return_value = "Mozilla/5.0"

    db = AsyncMock()
    nested_mock = MagicMock()
    nested_mock.__aenter__ = AsyncMock()
    nested_mock.__aexit__ = AsyncMock()
    db.begin_nested = MagicMock(return_value=nested_mock)

    user = MagicMock()
    user.id = uuid.uuid4()

    # Mock existing subscription
    existing_sub = PushSubscription(
        id=uuid.uuid4(),
        endpoint=payload.endpoint,
        topics=["old-topic"],
        user_id=user.id,
    )
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = existing_sub
    db.execute.return_value = mock_res

    with (
        patch("app.routers.notifications.enforce_rate_limit", AsyncMock()),
        patch("app.routers.notifications.resolve_locale", MagicMock(return_value="en")),
        patch(
            "app.routers.notifications.resolve_topics",
            MagicMock(return_value={"system"}),
        ),
    ):
        res = await push_router.subscribe(payload, request, db, user)
        assert res is not None
        assert existing_sub.topics == ["system"]


@pytest.mark.asyncio
async def test_subscribe_rate_limit_exceeded():
    from app.core.ratelimit import RateLimitExceeded, RateLimitInfo
    from app.schemas.notifications import PushSubscriptionIn

    payload = PushSubscriptionIn(
        endpoint="https://updates.push.services.mozilla.com/wpush/v2/gAAAAA",
        keys={"p256dh": "BEl62vOgw1...", "auth": "qQX4S..."},
        topics=["system"],
    )
    request = MagicMock()
    request.client.host = "127.0.0.1"
    db = AsyncMock()
    user = MagicMock()
    user.id = uuid.uuid4()

    info = RateLimitInfo(allowed=False, remaining=0, retry_after=10)
    with (
        patch(
            "app.routers.notifications.enforce_rate_limit",
            side_effect=RateLimitExceeded(info),
        ),
        patch("app.routers.notifications.resolve_locale", MagicMock(return_value="en")),
    ):
        with pytest.raises(HTTPException) as exc:
            await push_router.subscribe(payload, request, db, user)
        assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_subscribe_db_integrity_error_recovered_on_final_attempt():
    from app.schemas.notifications import PushSubscriptionIn

    payload = PushSubscriptionIn(
        endpoint="https://updates.push.services.mozilla.com/wpush/v2/gAAAAA",
        keys={"p256dh": "BEl62vOgw1...", "auth": "qQX4S..."},
        topics=["system"],
    )
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = MagicMock()
    request.headers.get.return_value = "Mozilla/5.0"

    db = AsyncMock()
    nested_mock = MagicMock()
    nested_mock.__aenter__ = AsyncMock()
    nested_mock.__aexit__ = AsyncMock()
    db.begin_nested = MagicMock(return_value=nested_mock)

    user = MagicMock()
    user.id = uuid.uuid4()

    # We raise IntegrityError only on the first 3 flushes
    call_count = 0

    async def mock_flush():
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            raise IntegrityError("statement", {}, Exception())

    db.flush = mock_flush

    existing_sub = PushSubscription(
        id=uuid.uuid4(),
        endpoint=payload.endpoint,
        topics=["old-topic"],
        user_id=user.id,
    )
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = existing_sub
    db.execute.return_value = mock_res

    with (
        patch("app.routers.notifications.enforce_rate_limit", AsyncMock()),
        patch("app.routers.notifications.resolve_locale", MagicMock(return_value="en")),
        patch("asyncio.sleep", AsyncMock()),
    ):
        res = await push_router.subscribe(payload, request, db, user)
        assert res is not None
        assert res.id == existing_sub.id


@pytest.mark.asyncio
async def test_subscribe_db_integrity_error_not_found_on_final_attempt():
    from app.schemas.notifications import PushSubscriptionIn

    payload = PushSubscriptionIn(
        endpoint="https://updates.push.services.mozilla.com/wpush/v2/gAAAAA",
        keys={"p256dh": "BEl62vOgw1...", "auth": "qQX4S..."},
        topics=["system"],
    )
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = MagicMock()
    request.headers.get.return_value = "Mozilla/5.0"

    db = AsyncMock()
    db.add = MagicMock()
    nested_mock = MagicMock()
    nested_mock.__aenter__ = AsyncMock()
    nested_mock.__aexit__ = AsyncMock()
    db.begin_nested = MagicMock(return_value=nested_mock)

    user = MagicMock()
    user.id = uuid.uuid4()

    # We raise IntegrityError on every flush
    async def mock_flush():
        raise IntegrityError("statement", {}, Exception())

    db.flush = mock_flush

    # Return None on query
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_res

    with (
        patch("app.routers.notifications.enforce_rate_limit", AsyncMock()),
        patch("app.routers.notifications.resolve_locale", MagicMock(return_value="en")),
        patch("asyncio.sleep", AsyncMock()),
    ):
        with pytest.raises(HTTPException) as exc:
            await push_router.subscribe(payload, request, db, user)
        assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_get_push_topics_no_record():
    db = AsyncMock()
    user = MagicMock()
    user.id = uuid.uuid4()

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_res

    res = await push_router.get_push_topics(db, user)
    assert res.has_preferences is False
    assert res.topics == []


@pytest.mark.asyncio
async def test_get_push_topics_with_record():
    db = AsyncMock()
    user = MagicMock()
    user.id = uuid.uuid4()

    record = UserPushTopic(user_id=user.id, topics=["system"])
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = record
    db.execute.return_value = mock_res

    res = await push_router.get_push_topics(db, user)
    assert res.has_preferences is True
    assert "system.release" in res.topics


@pytest.mark.asyncio
async def test_delete_push_subscription_not_found():
    from app.schemas.notifications import PushSubscriptionDelete

    payload = PushSubscriptionDelete(endpoint="https://some-endpoint")
    request = MagicMock()
    request.client.host = "127.0.0.1"
    db = AsyncMock()
    user = MagicMock()
    user.id = uuid.uuid4()

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_res

    with patch("app.routers.notifications.enforce_rate_limit", AsyncMock()):
        res = await push_router.unsubscribe(payload, request, db, user)
        assert res == {"ok": True, "removed": False}


@pytest.mark.asyncio
async def test_send_test_push_forbidden():
    from app.schemas.notifications import PushTestRequest

    payload = PushTestRequest(user_id=uuid.uuid4(), topic="system")
    request = MagicMock()
    db = AsyncMock()
    user = MagicMock()
    user.role = UserRole.STUDENT

    with patch(
        "app.routers.notifications.resolve_locale", MagicMock(return_value="en")
    ):
        with pytest.raises(HTTPException) as exc:
            await push_router.send_test(request, db, user, payload)
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_send_test_push_vapid_not_configured():
    from app.schemas.notifications import PushTestRequest

    payload = PushTestRequest(user_id=uuid.uuid4(), topic="system")
    request = MagicMock()
    db = AsyncMock()
    user = MagicMock()
    user.role = UserRole.ADMIN

    with (
        patch("app.routers.notifications.resolve_locale", MagicMock(return_value="en")),
        patch("app.routers.notifications.settings") as mock_settings,
    ):
        mock_settings.VAPID_PRIVATE_KEY = ""
        mock_settings.VAPID_PUBLIC_KEY = ""
        mock_settings.environment = "production"
        with pytest.raises(HTTPException) as exc:
            await push_router.send_test(request, db, user, payload)
        assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_send_test_push_rate_limit():
    from app.core.ratelimit import RateLimitExceeded, RateLimitInfo
    from app.schemas.notifications import PushTestRequest

    payload = PushTestRequest(user_id=uuid.uuid4(), topic="system")
    request = MagicMock()
    request.client.host = "127.0.0.1"
    db = AsyncMock()
    user = MagicMock()
    user.role = UserRole.ADMIN
    user.id = uuid.uuid4()

    info = RateLimitInfo(allowed=False, remaining=0, retry_after=5)
    with (
        patch("app.routers.notifications.resolve_locale", MagicMock(return_value="en")),
        patch("app.routers.notifications.settings") as mock_settings,
        patch(
            "app.routers.notifications.enforce_rate_limit",
            side_effect=RateLimitExceeded(info),
        ),
    ):
        mock_settings.VAPID_PRIVATE_KEY = "key"  # pragma: allowlist secret
        mock_settings.VAPID_PUBLIC_KEY = "key"
        mock_settings.environment = "production"
        with pytest.raises(HTTPException) as exc:
            await push_router.send_test(request, db, user, payload)
        assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_send_test_push_user_not_found():
    from app.schemas.notifications import PushTestRequest

    payload = PushTestRequest(user_id=uuid.uuid4(), topic="system")
    request = MagicMock()
    request.client.host = "127.0.0.1"
    db = AsyncMock()
    db.get.return_value = None
    user = MagicMock()
    user.role = UserRole.ADMIN
    user.id = uuid.uuid4()

    with (
        patch("app.routers.notifications.resolve_locale", MagicMock(return_value="en")),
        patch("app.routers.notifications.settings") as mock_settings,
        patch("app.routers.notifications.enforce_rate_limit", AsyncMock()),
    ):
        mock_settings.VAPID_PRIVATE_KEY = "key"  # pragma: allowlist secret
        mock_settings.VAPID_PUBLIC_KEY = "key"
        mock_settings.environment = "test"
        with pytest.raises(HTTPException) as exc:
            await push_router.send_test(request, db, user, payload)
        assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_send_test_push_no_subscriptions():
    from app.schemas.notifications import PushTestRequest

    payload = PushTestRequest(user_id=uuid.uuid4(), topic="system")
    request = MagicMock()
    request.client.host = "127.0.0.1"
    db = AsyncMock()
    target_user = MagicMock()
    target_user.id = payload.user_id
    db.get.return_value = target_user

    # Mock db.execute to return empty list
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_res

    user = MagicMock()
    user.role = UserRole.ADMIN
    user.id = uuid.uuid4()

    with (
        patch("app.routers.notifications.resolve_locale", MagicMock(return_value="en")),
        patch("app.routers.notifications.settings") as mock_settings,
        patch("app.routers.notifications.enforce_rate_limit", AsyncMock()),
    ):
        mock_settings.VAPID_PRIVATE_KEY = "key"  # pragma: allowlist secret
        mock_settings.VAPID_PUBLIC_KEY = "key"
        mock_settings.environment = "test"
        res = await push_router.send_test(request, db, user, payload)
        assert res.total == 0
        assert res.sent == 0


@pytest.mark.asyncio
async def test_send_test_push_success():
    from app.schemas.notifications import PushTestRequest
    from app.services.webpush import WebPushResult

    payload = PushTestRequest(
        user_id=uuid.uuid4(), topic="system", tag="t", badge="1", ttl=60, urgency="high"
    )
    request = MagicMock()
    request.client.host = "127.0.0.1"
    db = AsyncMock()
    target_user = MagicMock()
    target_user.id = payload.user_id
    db.get.return_value = target_user

    sub = PushSubscription(id=uuid.uuid4(), endpoint="endpoint", topics=["system"])
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [sub]
    db.execute.return_value = mock_res

    user = MagicMock()
    user.role = UserRole.ADMIN
    user.id = uuid.uuid4()

    results = [
        WebPushResult(
            subscription_id=uuid.uuid4(),
            endpoint="endpoint",
            user_id=uuid.uuid4(),
            status="sent",
        )
    ]
    with (
        patch("app.routers.notifications.resolve_locale", MagicMock(return_value="en")),
        patch("app.routers.notifications.settings") as mock_settings,
        patch("app.routers.notifications.enforce_rate_limit", AsyncMock()),
        patch(
            "app.routers.notifications.deliver_push_to_subscriptions",
            AsyncMock(return_value=results),
        ),
    ):
        mock_settings.VAPID_PRIVATE_KEY = "key"  # pragma: allowlist secret
        mock_settings.VAPID_PUBLIC_KEY = "key"
        mock_settings.environment = "test"
        res = await push_router.send_test(request, db, user, payload)
        assert res.total == 1
        assert res.sent == 1


@pytest.mark.asyncio
async def test_admin_get_user_topics_forbidden():
    request = MagicMock()
    db = AsyncMock()
    user = MagicMock()
    user.role = UserRole.STUDENT
    with patch(
        "app.routers.notifications.resolve_locale", MagicMock(return_value="en")
    ):
        with pytest.raises(HTTPException) as exc:
            await push_router.admin_get_user_topics(uuid.uuid4(), request, db, user)
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_get_user_topics_not_found():
    request = MagicMock()
    db = AsyncMock()
    user = MagicMock()
    user.role = UserRole.ADMIN

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_res

    with patch(
        "app.routers.notifications.resolve_locale", MagicMock(return_value="en")
    ):
        with pytest.raises(HTTPException) as exc:
            await push_router.admin_get_user_topics(uuid.uuid4(), request, db, user)
        assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_admin_get_user_topics_success():
    request = MagicMock()
    db = AsyncMock()
    user = MagicMock()
    user.role = UserRole.ADMIN

    target_user = MagicMock()
    target_user.id = uuid.uuid4()
    target_user.email = "test@example.com"
    target_user.push_topic_preferences = UserPushTopic(
        user_id=target_user.id, topics=["system"]
    )

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = target_user
    db.execute.return_value = mock_res

    with patch(
        "app.routers.notifications.resolve_locale", MagicMock(return_value="en")
    ):
        res = await push_router.admin_get_user_topics(target_user.id, request, db, user)
        assert res.user_id == target_user.id
        assert res.email == target_user.email
        assert "system.release" in res.topics


@pytest.mark.asyncio
async def test_admin_update_user_topics_forbidden():
    from app.schemas.notifications import AdminUserTopicsUpdate

    payload = AdminUserTopicsUpdate(topics=["system"])
    request = MagicMock()
    db = AsyncMock()
    user = MagicMock()
    user.role = UserRole.STUDENT
    with patch(
        "app.routers.notifications.resolve_locale", MagicMock(return_value="en")
    ):
        with pytest.raises(HTTPException) as exc:
            await push_router.admin_update_user_topics(
                uuid.uuid4(), payload, request, db, user
            )
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_update_user_topics_not_found():
    from app.schemas.notifications import AdminUserTopicsUpdate

    payload = AdminUserTopicsUpdate(topics=["system"])
    request = MagicMock()
    db = AsyncMock()
    user = MagicMock()
    user.role = UserRole.ADMIN

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_res

    with patch(
        "app.routers.notifications.resolve_locale", MagicMock(return_value="en")
    ):
        with pytest.raises(HTTPException) as exc:
            await push_router.admin_update_user_topics(
                uuid.uuid4(), payload, request, db, user
            )
        assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_admin_update_user_topics_success():
    from app.schemas.notifications import AdminUserTopicsUpdate

    payload = AdminUserTopicsUpdate(topics=["system"])
    request = MagicMock()
    db = AsyncMock()
    user = MagicMock()
    user.role = UserRole.ADMIN

    target_user = MagicMock()
    target_user.id = uuid.uuid4()
    target_user.email = "test@example.com"
    target_user.push_topic_preferences = UserPushTopic(
        user_id=target_user.id, topics=["system"]
    )

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = target_user
    db.execute.return_value = mock_res

    with (
        patch("app.routers.notifications.resolve_locale", MagicMock(return_value="en")),
        patch(
            "app.routers.notifications.synchronize_user_topics",
            AsyncMock(return_value=["system"]),
        ),
    ):
        res = await push_router.admin_update_user_topics(
            target_user.id, payload, request, db, user
        )
        assert res.user_id == target_user.id
        assert "system.release" in res.topics


@pytest.mark.asyncio
async def test_disable_user_push_forbidden():
    from app.schemas.notifications import DisableUserPushRequest

    payload = DisableUserPushRequest(user_id=uuid.uuid4())
    request = MagicMock()
    db = AsyncMock()
    user = MagicMock()
    user.role = UserRole.STUDENT
    with patch(
        "app.routers.notifications.resolve_locale", MagicMock(return_value="en")
    ):
        with pytest.raises(HTTPException) as exc:
            await push_router.disable_user_push(payload, request, db, user)
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_disable_user_push_not_found():
    from app.schemas.notifications import DisableUserPushRequest

    payload = DisableUserPushRequest(user_id=uuid.uuid4())
    request = MagicMock()
    db = AsyncMock()
    db.get.return_value = None
    user = MagicMock()
    user.role = UserRole.ADMIN
    with patch(
        "app.routers.notifications.resolve_locale", MagicMock(return_value="en")
    ):
        with pytest.raises(HTTPException) as exc:
            await push_router.disable_user_push(payload, request, db, user)
        assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_disable_user_push_no_subscriptions():
    from app.schemas.notifications import DisableUserPushRequest

    payload = DisableUserPushRequest(user_id=uuid.uuid4())
    request = MagicMock()
    db = AsyncMock()
    target_user = MagicMock()
    target_user.id = payload.user_id
    db.get.return_value = target_user

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_res

    user = MagicMock()
    user.role = UserRole.ADMIN
    with patch(
        "app.routers.notifications.resolve_locale", MagicMock(return_value="en")
    ):
        res = await push_router.disable_user_push(payload, request, db, user)
        assert res == {"ok": True, "removed": 0}


@pytest.mark.asyncio
async def test_disable_user_push_success():
    from app.schemas.notifications import DisableUserPushRequest

    payload = DisableUserPushRequest(user_id=uuid.uuid4())
    request = MagicMock()
    db = AsyncMock()
    target_user = MagicMock()
    target_user.id = payload.user_id
    db.get.return_value = target_user

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [uuid.uuid4(), uuid.uuid4()]
    db.execute.return_value = mock_res

    user = MagicMock()
    user.role = UserRole.ADMIN
    with patch(
        "app.routers.notifications.resolve_locale", MagicMock(return_value="en")
    ):
        res = await push_router.disable_user_push(payload, request, db, user)
        assert res == {"ok": True, "removed": 2}


@pytest.mark.asyncio
async def test_broadcast_forbidden():
    from app.schemas.notifications import NotifyBody

    payload = NotifyBody(title="hello", body="world")
    request = MagicMock()
    db = AsyncMock()
    user = MagicMock()
    user.role = UserRole.STUDENT
    with patch(
        "app.routers.notifications.resolve_locale", MagicMock(return_value="en")
    ):
        with pytest.raises(HTTPException) as exc:
            await push_router.broadcast(payload, request, db, user)
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_broadcast_rate_limited():
    from app.core.ratelimit import RateLimitExceeded, RateLimitInfo
    from app.schemas.notifications import NotifyBody

    payload = NotifyBody(title="hello", body="world")
    request = MagicMock()
    db = AsyncMock()
    user = MagicMock()
    user.role = UserRole.ADMIN
    user.id = uuid.uuid4()

    info = RateLimitInfo(allowed=False, remaining=0, retry_after=5)
    with (
        patch("app.routers.notifications.resolve_locale", MagicMock(return_value="en")),
        patch(
            "app.routers.notifications.enforce_rate_limit",
            side_effect=RateLimitExceeded(info),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await push_router.broadcast(payload, request, db, user)
        assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_broadcast_success():
    from app.schemas.notifications import NotifyBody
    from app.services.webpush import WebPushResult

    payload = NotifyBody(title="hello", body="world", topic="system")
    request = MagicMock()
    db = AsyncMock()
    user = MagicMock()
    user.role = UserRole.ADMIN
    user.id = uuid.uuid4()

    sub = PushSubscription(id=uuid.uuid4(), endpoint="endpoint", topics=["system"])

    mock_res1 = MagicMock()
    mock_res1.scalars.return_value.all.return_value = [sub]
    mock_res2 = MagicMock()
    mock_res2.scalars.return_value.all.return_value = []

    db.execute.side_effect = [mock_res1, mock_res2]

    results = [
        WebPushResult(
            subscription_id=uuid.uuid4(),
            endpoint="endpoint",
            user_id=uuid.uuid4(),
            status="sent",
        )
    ]
    with (
        patch("app.routers.notifications.resolve_locale", MagicMock(return_value="en")),
        patch("app.routers.notifications.enforce_rate_limit", AsyncMock()),
        patch(
            "app.routers.notifications.deliver_push_to_subscriptions",
            AsyncMock(return_value=results),
        ),
    ):
        res = await push_router.broadcast(payload, request, db, user)
        assert res.total == 1
        assert res.sent == 1


# =========================================================================
# 2. app/api/notifications.py
# =========================================================================


def test_ensure_vary_header_existing_non_empty():
    response = MagicMock()
    response.headers = {"Vary": "Cookie"}
    notifications_api._ensure_vary_header(response, "Accept-Language")
    assert "Accept-Language" in response.headers["Vary"]
    assert "Cookie" in response.headers["Vary"]


@pytest.mark.asyncio
async def test_sync_get_columns_inspect_error():
    db = AsyncMock()

    async def mock_run_sync(fn, *args, **kwargs):
        sync_session = MagicMock()
        sync_session.bind = MagicMock()
        with patch("app.api.notifications.inspect") as mock_inspect:
            mock_inspect.return_value.get_columns.side_effect = NoSuchTableError(
                "no table"
            )
            return fn(sync_session)

    db.run_sync = mock_run_sync

    cols = await notifications_api._existing_notification_columns(db)
    assert cols == set()


@pytest.mark.asyncio
async def test_fetch_notification_rows_sqlalchemy_error():
    db = AsyncMock()
    db.execute.side_effect = SQLAlchemyError("db error")
    with pytest.raises(SQLAlchemyError):
        await notifications_api._fetch_notification_rows(db, uuid.uuid4(), 10, None)


@pytest.mark.asyncio
async def test_list_notifications_bad_cursor_dt():
    request = MagicMock()
    response = MagicMock()
    db = AsyncMock()
    user = MagicMock()
    user.id = uuid.uuid4()

    bad_cursor = base64.b64encode(b"invalid-timestamp,not-a-uuid").decode()
    with patch("app.api.notifications.resolve_locale", MagicMock(return_value="en")):
        with pytest.raises(HTTPException) as exc:
            await notifications_api.list_notifications(
                request=request, response=response, db=db, user=user, cursor=bad_cursor
            )
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_list_notifications_has_more():
    request = MagicMock()
    response = Response()
    db = AsyncMock()
    user = MagicMock()
    user.id = uuid.uuid4()

    created = datetime.now(UTC)
    nid = uuid.uuid4()
    row = {
        "id": nid,
        "user_id": user.id,
        "title": "t",
        "body": "b",
        "created_at": created,
        "read": False,
        "data": None,
        "topic": "system",
    }

    mock_rows = [row, row]
    with patch(
        "app.api.notifications._fetch_notification_rows",
        AsyncMock(return_value=(mock_rows, {"read", "id", "user_id"})),
    ):
        mock_exec_res = MagicMock()
        mock_exec_res.scalar_one.return_value = 1
        db.execute.return_value = mock_exec_res

        res = await notifications_api.list_notifications(
            request=request, response=response, db=db, user=user, cursor=None, limit=1
        )
        assert res.has_more is True
        assert res.next_cursor is not None


@pytest.mark.asyncio
async def test_list_notifications_available_columns_read_mismatch():
    request = MagicMock()
    response = Response()
    db = AsyncMock()
    user = MagicMock()
    user.id = uuid.uuid4()

    with patch(
        "app.api.notifications._fetch_notification_rows",
        AsyncMock(return_value=([], {"id", "user_id"})),
    ):
        mock_exec_res = MagicMock()
        mock_exec_res.scalar_one.return_value = 5
        db.execute.return_value = mock_exec_res

        res = await notifications_api.list_notifications(
            request=request, response=response, db=db, user=user, cursor=None, limit=20
        )
        assert res.unread_count == 5


# =========================================================================
# 3. app/core/metrics.py
# =========================================================================


@pytest.mark.asyncio
async def test_record_cache_metrics_non_redis():
    with patch("app.deps.cache.get_cache") as mock_get_cache:
        mock_get_cache.return_value = MagicMock()
        with (
            patch("app.core.metrics._CACHE_ENTRIES") as mock_entries,
            patch("app.core.metrics._CACHE_MEMORY_BYTES") as mock_memory,
            patch("app.core.metrics._REDIS_HEALTH") as mock_health,
        ):
            await metrics_core._record_cache_metrics()
            mock_entries.set.assert_called_with(0.0)
            mock_memory.set.assert_called_with(0.0)
            mock_health.set.assert_called_with(0.0)


@pytest.mark.asyncio
async def test_record_cache_metrics_redis():
    from app.deps.cache import RedisCache

    redis_cache = MagicMock(spec=RedisCache)
    mock_client = AsyncMock()
    mock_client.ping.return_value = "PONG"
    mock_client.info.return_value = {"used_memory": 1024}
    mock_client.dbsize.return_value = 100
    redis_cache._get_client = AsyncMock(return_value=mock_client)

    with (
        patch("app.deps.cache.get_cache", return_value=redis_cache),
        patch("app.core.metrics._CACHE_ENTRIES") as mock_entries,
        patch("app.core.metrics._CACHE_MEMORY_BYTES") as mock_memory,
        patch("app.core.metrics._REDIS_HEALTH") as mock_health,
    ):
        await metrics_core._record_cache_metrics()
        mock_entries.set.assert_called_with(100.0)
        mock_memory.set.assert_called_with(1024.0)
        mock_health.set.assert_called_with(1.0)


def test_record_pool_metrics():
    mock_pool = MagicMock()
    mock_pool.size.return_value = 10
    mock_pool.checkedout.return_value = 2
    mock_pool.overflow.return_value = 0
    mock_pool.checkedin.return_value = 8

    with (
        patch("app.core.metrics.engine") as mock_engine,
        patch("app.core.metrics._DB_POOL_SIZE") as mock_size,
        patch("app.core.metrics._DB_POOL_CHECKEDOUT") as mock_checkedout,
        patch("app.core.metrics._DB_POOL_OVERFLOW") as mock_overflow,
        patch("app.core.metrics._DB_POOL_CHECKEDIN") as mock_checkedin,
    ):
        mock_engine.sync_engine.pool = mock_pool
        metrics_core._record_pool_metrics()
        mock_size.set.assert_called_with(10.0)
        mock_checkedout.set.assert_called_with(2.0)
        mock_overflow.set.assert_called_with(0.0)
        mock_checkedin.set.assert_called_with(8.0)


def test_record_system_metrics():
    with (
        patch("app.core.metrics._CPU_LOAD") as mock_cpu,
        patch("app.core.metrics._GPU_LOAD") as mock_gpu,
        patch("app.core.metrics._load_gputil") as mock_load_gputil,
        patch("psutil.cpu_percent", return_value=45.5),
    ):
        mock_gpu_module = MagicMock()
        mock_gpu_obj = MagicMock()
        mock_gpu_obj.load = 0.2
        mock_gpu_module.getGPUs.return_value = [mock_gpu_obj]
        mock_load_gputil.return_value = mock_gpu_module

        metrics_core._record_system_metrics()
        mock_cpu.set.assert_called_with(45.5)
        mock_gpu.labels.return_value.set.assert_called_with(20.0)


def test_load_gputil():
    with patch("importlib.util.find_spec", return_value=None):
        assert metrics_core._load_gputil() is None


# =========================================================================
# 4. app/core/observability.py
# =========================================================================


def test_configure_observability():
    app = FastAPI()
    engine = MagicMock()

    with (
        patch("app.core.observability.settings") as mock_settings,
        patch("app.core.observability._configure_logging"),
        patch("app.core.observability._configure_otel") as mock_otel,
        patch("app.core.observability._configure_sentry"),
    ):
        mock_settings.enable_otel = True
        mock_otel.return_value = MagicMock()

        with patch(
            "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app"
        ) as mock_instrument:
            observability_core.configure_observability(app, engine=engine)
            mock_instrument.assert_called_once()
            assert app.state.observability_configured is True


def test_configure_observability_does_not_reinstrument_existing_app():
    app = FastAPI()
    app.state.observability_configured = False
    app.state.otel_instrumented = True
    tracer_provider = MagicMock()

    with (
        patch("app.core.observability.settings") as mock_settings,
        patch("app.core.observability._configure_logging"),
        patch("app.core.observability._configure_otel", return_value=tracer_provider),
        patch("app.core.observability._configure_sentry"),
        patch(
            "app.core.observability.FastAPIInstrumentor.instrument_app"
        ) as instrument_app,
    ):
        mock_settings.enable_otel = True
        observability_core.configure_observability(app, engine=MagicMock())

    instrument_app.assert_not_called()
    assert app.state.observability_configured is True


def test_shutdown_observability():
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.trace import TracerProvider

    class DummyTracerProvider(TracerProvider):
        def __init__(self):
            pass

        def shutdown(self):
            pass

    class DummyMeterProvider(MeterProvider):
        def __init__(self):
            pass

        def shutdown(self):
            pass

    with (
        patch("app.core.observability._otel_logging_handler"),
        patch("app.core.observability._otel_logger_provider"),
    ):
        dummy_trace = DummyTracerProvider()
        dummy_trace.shutdown = MagicMock()

        dummy_meter = DummyMeterProvider()
        dummy_meter.shutdown = MagicMock()
        # Teardown is deliberately ownership based: process-global providers may
        # belong to another in-process SDK user and must never be shut down here.
        observability_core._otel_tracer_provider = dummy_trace
        observability_core._otel_meter_provider = dummy_meter

        observability_core.shutdown_observability()
        dummy_trace.shutdown.assert_called_once()
        dummy_meter.shutdown.assert_called_once()


# =========================================================================
# 6. app/api/spotify.py
# =========================================================================


@pytest.mark.asyncio
async def test_spotify_refresh_circuit_breaker_open():
    from app.core.circuit_breaker import CircuitBreakerOpenError

    user = MagicMock()
    user.spotify = MagicMock()
    user.spotify.access_token = "old_token"
    user.spotify.token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    user.spotify.refresh_token = "refresh_token"

    db = AsyncMock()

    with patch("app.api.spotify._spotify_circuit_breaker") as mock_cb:
        mock_cb.__aenter__.side_effect = CircuitBreakerOpenError(
            "spotify", remaining_seconds=10, failure_count=3
        )
        res = await spotify_api._ensure_access_token(db, user)
        assert res is None


@pytest.mark.asyncio
async def test_spotify_refresh_status_not_200():
    user = MagicMock()
    user.spotify = MagicMock()
    user.spotify.access_token = "old_token"
    user.spotify.token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    user.spotify.refresh_token = "refresh_token"

    db = AsyncMock()

    mock_resp = MagicMock()
    mock_resp.status_code = 400

    with (
        patch(
            "app.api.spotify._spotify_http_client.post",
            AsyncMock(return_value=mock_resp),
        ),
        patch("app.api.spotify._disconnect_user") as mock_disconnect,
    ):
        with pytest.raises(HTTPException) as exc:
            await spotify_api._ensure_access_token(db, user)
        assert exc.value.status_code == 401
        mock_disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_spotify_refresh_no_access_token():
    user = MagicMock()
    user.spotify = MagicMock()
    user.spotify.access_token = "old_token"
    user.spotify.token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    user.spotify.refresh_token = "refresh_token"

    db = AsyncMock()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {}

    with (
        patch(
            "app.api.spotify._spotify_http_client.post",
            AsyncMock(return_value=mock_resp),
        ),
        patch("app.api.spotify._disconnect_user") as mock_disconnect,
    ):
        with pytest.raises(HTTPException) as exc:
            await spotify_api._ensure_access_token(db, user)
        assert exc.value.status_code == 401
        mock_disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_spotify_refresh_scope_downgraded():
    user = MagicMock()
    user.spotify = MagicMock()
    user.spotify.access_token = "old_token"
    user.spotify.token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    user.spotify.refresh_token = "refresh_token"
    user.spotify.scope = "user-read-private user-read-email"

    db = AsyncMock()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "new_token",
        "scope": "user-read-private",
        "expires_in": 3600,
    }

    with (
        patch(
            "app.api.spotify._spotify_http_client.post",
            AsyncMock(return_value=mock_resp),
        ),
        patch("app.api.spotify._disconnect_user") as mock_disconnect,
    ):
        with pytest.raises(HTTPException) as exc:
            await spotify_api._ensure_access_token(db, user)
        assert exc.value.status_code == 401
        mock_disconnect.assert_called_once()


# =========================================================================
# 7. app/api/websocket.py
# =========================================================================


@pytest.mark.asyncio
async def test_stop_presence_pubsub():
    with patch("app.api.websocket.presence_pubsub.shutdown") as mock_shutdown:
        await websocket_api.stop_presence_pubsub()
        mock_shutdown.assert_called_once()


@pytest.mark.asyncio
async def test_start_presence_pubsub():
    with patch("app.api.websocket.presence_pubsub.initialize") as mock_init:
        await websocket_api.start_presence_pubsub()
        mock_init.assert_called_once()


@pytest.mark.asyncio
async def test_get_online_users_for_user():
    user_id = uuid.uuid4()
    target_id1 = uuid.uuid4()
    target_id2 = uuid.uuid4()

    with (
        patch(
            "app.api.ws.presence._get_presence_audience",
            AsyncMock(return_value=[target_id1, target_id2]),
        ),
        patch("app.api.websocket.manager") as mock_manager,
    ):
        mock_manager.is_online.side_effect = lambda uid: uid == target_id1

        res = await websocket_api._get_online_users_for_user(user_id)
        assert res == [target_id1]


@pytest.mark.asyncio
async def test_websocket_chat_rate_limit():
    websocket = AsyncMock()
    websocket.send_json = AsyncMock()

    async def mock_receive():
        if websocket.receive_text.call_count > 1:
            raise Exception("break loop")
        return "{}"

    websocket.receive_text = AsyncMock(side_effect=mock_receive)
    websocket.receive_text.call_count = 0

    with patch("app.api.websocket.manager") as mock_manager:
        mock_manager.connect = AsyncMock(return_value=True)
        mock_manager.broadcast_presence = AsyncMock()
        mock_manager.disconnect = AsyncMock()
        mock_manager.check_rate_limit.return_value = False

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        with patch(
            "app.api.ws.authenticator.authenticator.authenticate_upgrade",
            AsyncMock(return_value=(mock_user, "jti", "subprotocol")),
        ):
            await websocket_api.websocket_chat(websocket)
            websocket.send_json.assert_called_with(
                {"type": "error", "message": "Rate limit exceeded"}
            )


@pytest.mark.asyncio
async def test_websocket_chat_payload_too_large():
    websocket = AsyncMock()
    large_payload = "a" * 33000
    websocket.receive_text = AsyncMock(return_value=large_payload)
    websocket.close = AsyncMock()

    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    with (
        patch(
            "app.api.ws.authenticator.authenticator.authenticate_upgrade",
            AsyncMock(return_value=(mock_user, "jti", "subprotocol")),
        ),
        patch("app.api.websocket.manager") as mock_manager,
    ):
        mock_manager.connect = AsyncMock(return_value=True)
        mock_manager.broadcast_presence = AsyncMock()
        mock_manager.disconnect = AsyncMock()
        mock_manager.check_rate_limit.return_value = True
        await websocket_api.websocket_chat(websocket)
        websocket.close.assert_called_with(code=1009, reason="Payload too large")


@pytest.mark.asyncio
async def test_websocket_chat_rejects_utf8_oversized_frame_before_json_dispatch():
    """A frame can fit the code-point cap while exceeding the transport byte cap."""
    websocket = AsyncMock()
    # 16k astral code points are valid text, but encode to ~64 KiB before the
    # small JSON envelope overhead.  The route must reject this before parsing
    # or dispatching it, matching ws-hub's 60 KiB ingress guard.
    large_utf8_content = "😀" * 16_000
    frame = json.dumps(
        {"type": "message", "content": large_utf8_content}, ensure_ascii=False
    )
    assert len(frame) <= 32_768
    assert len(frame.encode("utf-8")) > 60 * 1024
    websocket.receive_text = AsyncMock(
        side_effect=[frame, WebSocketDisconnect(code=1000)]
    )
    websocket.close = AsyncMock()

    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    with (
        patch(
            "app.api.ws.authenticator.authenticator.authenticate_upgrade",
            AsyncMock(return_value=(mock_user, "jti", "subprotocol")),
        ),
        patch("app.api.websocket.manager") as mock_manager,
    ):
        mock_manager.connect = AsyncMock(return_value=True)
        mock_manager.broadcast_presence = AsyncMock()
        mock_manager.disconnect = AsyncMock()
        mock_manager.check_rate_limit.return_value = True
        await websocket_api.websocket_chat(websocket)

    websocket.close.assert_called_with(code=1009, reason="Payload too large")


@pytest.mark.asyncio
async def test_websocket_chat_malformed_json():
    websocket = AsyncMock()
    websocket.receive_text = AsyncMock(return_value="{invalid json")
    websocket.send_json = AsyncMock()

    async def mock_receive():
        if websocket.receive_text.call_count > 1:
            raise Exception("break loop")
        return "{invalid json"

    websocket.receive_text.side_effect = mock_receive
    websocket.receive_text.call_count = 0

    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    with (
        patch(
            "app.api.ws.authenticator.authenticator.authenticate_upgrade",
            AsyncMock(return_value=(mock_user, "jti", "subprotocol")),
        ),
        patch("app.api.websocket.manager") as mock_manager,
    ):
        mock_manager.connect = AsyncMock(return_value=True)
        mock_manager.broadcast_presence = AsyncMock()
        mock_manager.disconnect = AsyncMock()
        mock_manager.check_rate_limit.return_value = True
        await websocket_api.websocket_chat(websocket)
        websocket.send_json.assert_called_with(
            {"type": "error", "message": "Invalid JSON"}
        )


@pytest.mark.asyncio
async def test_notify_new_message():
    from app.models.chat import Message

    message = Message(
        id=uuid.uuid4(), sender_id=uuid.uuid4(), chat_id=uuid.uuid4(), content="hello"
    )

    with (
        patch("app.api.websocket.build_presence_map", AsyncMock(return_value={})),
        patch("app.api.websocket.serialize_message", return_value={}),
        patch("app.api.websocket.manager") as mock_manager,
    ):
        mock_manager.broadcast_to_chat = AsyncMock(return_value=1)
        res = await websocket_api.notify_new_message(message)
        assert res == 1


# =========================================================================
# 8. app/api/users.py
# =========================================================================


def test_enforce_profile_cache_integrity_not_dict():
    request = MagicMock()
    request.headers = {"x-profile-cache-envelope": "[]"}
    request.state = MagicMock()
    request.state.active_session.signing_key = "secret"

    with patch("app.api.users.settings") as mock_settings:
        mock_settings.environment = "production"
        with pytest.raises(HTTPException) as exc:
            users_api._enforce_profile_cache_integrity(request)
        assert exc.value.status_code == 400


def test_enforce_profile_cache_integrity_missing_fields():
    request = MagicMock()
    raw_envelope = json.dumps({"version": 1, "data": {}, "signature": "sig"})
    request.headers = {"x-profile-cache-envelope": raw_envelope}
    request.state = MagicMock()
    request.state.active_session.signing_key = "secret"

    with patch("app.api.users.settings") as mock_settings:
        mock_settings.environment = "production"
        with pytest.raises(HTTPException) as exc:
            users_api._enforce_profile_cache_integrity(request)
        assert exc.value.status_code == 400


def test_enforce_profile_cache_integrity_invalid_signature():
    request = MagicMock()
    raw_envelope = json.dumps(
        {"version": 1, "expiresAt": 123456789000, "data": {}, "signature": "invalidsig"}
    )
    request.headers = {"x-profile-cache-envelope": raw_envelope}
    request.state = MagicMock()
    request.state.active_session.signing_key = "secret"

    with patch("app.api.users.settings") as mock_settings:
        mock_settings.environment = "production"
        with pytest.raises(HTTPException) as exc:
            users_api._enforce_profile_cache_integrity(request)
        assert exc.value.status_code == 400
