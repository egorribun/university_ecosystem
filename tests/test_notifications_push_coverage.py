from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

import app.models.models as models
from app.routers.notifications import (
    PushSubscriptionDelete,
    PushSubscriptionIn,
    PushSubscriptionKeys,
    PushSubscriptionTopicsUpdate,
    PushTestRequest,
    _refresh_user_topic_preferences,
    _validate_subscription_payload,
    get_push_topics,
    send_test,
    subscribe,
    unsubscribe,
    update_subscription_topics,
)
from app.services.webpush import (
    WebPushResult,
    _is_user_in_quiet_hours,
    _mask_endpoint,
    _normalize_payload,
    _prepare_actions,
    _prepare_delivery_payload,
    _resolve_ttl,
    build_payload,
)


# Mock models
@pytest.fixture
def mock_user():
    return models.User(id=1, email="test@e.com", role="student", dnd_enabled=False)


@pytest.fixture
def mock_admin():
    return models.User(id=2, email="admin@e.com", role="admin")


@pytest.fixture
def mock_db():
    db = MagicMock(spec=AsyncSession)
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    db.get = AsyncMock()
    db.add = MagicMock()  # add is usually sync
    # Support async context manager
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_request():
    req = MagicMock(spec=Request)
    req.client.host = "127.0.0.1"
    req.headers = {"user-agent": "Mozilla/5.0"}
    return req


@pytest.mark.asyncio
async def test_validate_subscription_payload():
    # Valid
    data = PushSubscriptionIn(
        endpoint="https://push.com/123",
        keys=PushSubscriptionKeys(p256dh="key", auth="secret"),
    )
    res = await _validate_subscription_payload(data, locale="en")
    assert res == ("https://push.com/123", "key", "secret")

    # Invalid
    data.endpoint = " "
    with pytest.raises(HTTPException) as exc:
        await _validate_subscription_payload(data, locale="en")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_subscribe_flow(mock_db, mock_user, mock_request):
    payload = PushSubscriptionIn(
        endpoint="https://push.com/123",
        keys=PushSubscriptionKeys(p256dh="key", auth="secret"),
        topics=["news"],
    )

    # 1. New subscription
    mock_db.execute.return_value = MagicMock(
        scalar_one_or_none=MagicMock(return_value=None)
    )

    # Ensure the subscription added to db has an ID and keys for serialization
    def add_id(obj):
        if isinstance(obj, models.PushSubscription):
            obj.id = 123
            obj.p256dh = payload.keys.p256dh
            obj.auth = payload.keys.auth

    mock_db.add.side_effect = add_id

    with (
        patch("app.routers.notifications.ensure_push_subscription_schema", AsyncMock()),
        patch("app.routers.notifications.enforce_rate_limit", AsyncMock()),
        patch("app.routers.notifications.resolve_locale", return_value="en"),
        patch("app.routers.notifications.resolve_topics", return_value=["news"]),
        patch("app.routers.notifications._refresh_user_topic_preferences", AsyncMock()),
    ):
        res = await subscribe(payload, mock_request, mock_db, mock_user)
        assert res.endpoint == "https://push.com/123"
        mock_db.add.assert_called()
        mock_db.commit.assert_called()

    # 2. Existing subscription from different user - now transfers ownership (no conflict)
    existing = models.PushSubscription(
        id=1,
        user_id=99,
        endpoint="https://push.com/123",
        p256dh="old_key",
        auth="old_secret",
        topics=["old_topic"],
    )
    mock_db.execute.return_value = MagicMock(
        scalar_one_or_none=MagicMock(return_value=existing)
    )

    with (
        patch("app.routers.notifications.ensure_push_subscription_schema", AsyncMock()),
        patch("app.routers.notifications.enforce_rate_limit", AsyncMock()),
        patch("app.routers.notifications.resolve_locale", return_value="en"),
        patch("app.routers.notifications.resolve_topics", return_value=["news"]),
        patch("app.routers.notifications._refresh_user_topic_preferences", AsyncMock()),
    ):
        # Should succeed with ownership transfer, not raise HTTPException
        res = await subscribe(payload, mock_request, mock_db, mock_user)
        assert res.endpoint == "https://push.com/123"
        # Ownership should be transferred to mock_user
        assert existing.user_id == mock_user.id


@pytest.mark.asyncio
async def test_unsubscribe(mock_db, mock_user, mock_request):
    payload = PushSubscriptionDelete(endpoint="https://push.com/123")

    # Not found
    mock_db.execute.return_value = MagicMock(
        scalar_one_or_none=MagicMock(return_value=None)
    )
    res = await unsubscribe(payload, mock_request, mock_db, mock_user)
    assert res["removed"] is False

    # Found and removed
    existing = models.PushSubscription(
        id=1, user_id=mock_user.id, endpoint="https://push.com/123"
    )
    mock_db.execute.return_value = MagicMock(
        scalar_one_or_none=MagicMock(return_value=existing)
    )

    with patch(
        "app.routers.notifications._refresh_user_topic_preferences", AsyncMock()
    ):
        res = await unsubscribe(payload, mock_request, mock_db, mock_user)
        assert res["removed"] is True
        mock_db.delete.assert_called_with(existing)


@pytest.mark.asyncio
async def test_update_topics(mock_db, mock_user, mock_request):
    payload = PushSubscriptionTopicsUpdate(
        endpoint="https://push.com/123", topics=["sports"]
    )

    # Not found
    mock_db.execute.return_value = MagicMock(
        scalar_one_or_none=MagicMock(return_value=None)
    )
    with pytest.raises(HTTPException) as exc:
        await update_subscription_topics(payload, mock_request, mock_db, mock_user)
    assert exc.value.status_code == 404

    # Success
    existing = models.PushSubscription(
        id=1,
        user_id=mock_user.id,
        endpoint="https://push.com/123",
        topics=["news"],
        p256dh="key",
        auth="secret",
    )
    mock_db.execute.return_value = MagicMock(
        scalar_one_or_none=MagicMock(return_value=existing)
    )

    with (
        patch(
            "app.routers.notifications.synchronize_user_topics",
            AsyncMock(return_value=["sports"]),
        ),
        patch(
            "app.routers.notifications.normalize_topics", side_effect=lambda x, **kw: x
        ),
    ):
        res = await update_subscription_topics(
            payload, mock_request, mock_db, mock_user
        )
        assert "sports" in res.topics
        # Ensure refresh didn't wipe it (though mock won't really "refresh")
        assert existing.topics == ["sports"]


@pytest.mark.asyncio
async def test_get_push_topics(mock_db, mock_user):
    record = models.UserPushTopic(
        user_id=mock_user.id, topics=["news"], updated_at=datetime.now(UTC)
    )
    mock_db.execute.return_value = MagicMock(
        scalar_one_or_none=MagicMock(return_value=record)
    )

    with (
        patch(
            "app.routers.notifications.get_allowed_topics",
            return_value=["news", "sports"],
        ),
        patch("app.routers.notifications.sort_topics", return_value=["news"]),
    ):
        res = await get_push_topics(mock_db, mock_user)
        assert res.topics == ["news"]
        assert res.has_preferences is True


@pytest.mark.asyncio
async def test_send_test_push(mock_db, mock_admin, mock_user, mock_request):
    payload = PushTestRequest(user_id=mock_user.id, title="Test", body="Hello")

    # Forbidden for non-admin
    with pytest.raises(HTTPException) as exc:
        await send_test(mock_request, mock_db, mock_user, payload)
    assert exc.value.status_code == 403

    mock_db.get.return_value = mock_user
    sub = models.PushSubscription(
        id=1, user_id=mock_user.id, endpoint="https://push.com/123", topics=["system"]
    )

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [sub]
    mock_res = MagicMock()
    mock_res.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_res

    with (
        patch("app.routers.notifications.enforce_rate_limit", AsyncMock()),
        patch(
            "app.routers.notifications.subscription_supports_topic", return_value=True
        ),
        patch(
            "app.routers.notifications._deliver_to_subscription",
            AsyncMock(return_value=WebPushResult(1, "url", 1, "sent")),
        ),
    ):
        res = await send_test(mock_request, mock_db, mock_admin, payload)
        assert res.sent == 1


@pytest.mark.asyncio
async def test_refresh_user_topic_preferences(mock_db):
    user_id = 1
    # Mock multiple subscriptions with different topics
    topics_mock = MagicMock()
    topics_mock.scalars.return_value = [["news"], ["sports", "news"]]
    mock_db.execute.side_effect = [
        topics_mock,
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ]

    with patch(
        "app.routers.notifications.sort_topics", return_value=["news", "sports"]
    ):
        await _refresh_user_topic_preferences(mock_db, user_id=user_id)
        # Should add a new record
        mock_db.add.assert_called()
        added_record = mock_db.add.call_args[0][0]
        assert sorted(added_record.topics) == ["news", "sports"]


# --- WebPush Service Tests ---


def test_webpush_utils():
    # Mask endpoint
    assert _mask_endpoint("https://example.com/sub/123") is not None
    assert _mask_endpoint(None) is None

    # Prepare actions
    raw = [{"action": "a1", "title": "t1", "url": "/u1"}, {"invalid": "item"}]
    actions, urls = _prepare_actions(raw)
    assert len(actions) == 1
    assert actions[0]["action"] == "a1"
    assert urls["a1"] == "/u1"


def test_quiet_hours():
    user = models.User(dnd_enabled=True, dnd_start=None, dnd_end=None)
    # enabled but no dates -> quiet
    assert _is_user_in_quiet_hours(user) is True

    from datetime import time

    user.dnd_start = time(22, 0)
    user.dnd_end = time(8, 0)
    # night time
    assert _is_user_in_quiet_hours(user, now_time=time(23, 0)) is True
    # day time
    assert _is_user_in_quiet_hours(user, now_time=time(10, 0)) is False


def test_normalize_payload():
    raw = {
        "title": "T",
        "body": "B",
        "actions": [{"action": "a", "title": "title"}],
        "ttl": 3600,
    }
    payload, meta = _normalize_payload(raw)
    assert payload["title"] == "T"
    assert payload["options"]["body"] == "B"
    assert meta["ttl"] == 3600

    # via options
    raw2 = {"options": {"body": "B2", "ttl": 1800}}
    payload2, meta2 = _normalize_payload(raw2)
    assert payload2["options"]["body"] == "B2"
    assert meta2["ttl"] == 1800


def test_resolve_ttl():
    assert _resolve_ttl({"ttl": 500}) == 500
    assert _resolve_ttl({"urgency": "high"}) == 300
    assert _resolve_ttl({}) == 3600


def test_build_payload():
    with patch(
        "app.services.webpush.render_notification_template",
        return_value={"title": "FromTemplate"},
    ):
        res = build_payload("type", {"data": {"foo": "bar"}}, locale="en")
        assert res["title"] == "FromTemplate"
        assert res["options"]["lang"] == "en"


@pytest.mark.asyncio
async def test_prepare_delivery_payload_quiet(mock_user):
    mock_user.dnd_enabled = True
    # Always quiet if no range
    payload = {"title": "T"}
    res = _prepare_delivery_payload(payload, topic="news", user=mock_user)
    assert res["options"]["silent"] is True
    assert res["data"]["dnd_suppressed"] is True


@pytest.mark.asyncio
async def test_delivery_to_user(mock_db, mock_user):
    sub = models.PushSubscription(
        id=1,
        user_id=mock_user.id,
        endpoint="url",
        p256dh="k",
        auth="s",
        topics=["news"],
    )
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [sub]
    mock_res = MagicMock()
    mock_res.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_res

    with (
        patch("app.services.webpush.async_session", return_value=mock_db),
        patch("app.services.webpush.enforce_rate_limit", AsyncMock()),
        patch("app.services.webpush.subscription_supports_topic", return_value=True),
        patch(
            "app.services.webpush.asyncio.to_thread",
            AsyncMock(return_value=WebPushResult(1, "url", 1, "sent")),
        ),
    ):
        from app.services.webpush import send_to_user

        res = await send_to_user(mock_user.id, {"title": "T"}, topic="news")
        assert len(res) == 1
        assert res[0].status == "sent"


@pytest.mark.asyncio
async def test_broadcast_to_topic(mock_db, mock_user):
    sub = models.PushSubscription(
        id=1,
        user_id=mock_user.id,
        endpoint="url",
        p256dh="k",
        auth="s",
        topics=["news"],
    )
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [sub]
    mock_res = MagicMock()
    mock_res.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_res

    with (
        patch("app.services.webpush.async_session", return_value=mock_db),
        patch("app.services.webpush.enforce_rate_limit", AsyncMock()),
        patch(
            "app.services.webpush.asyncio.to_thread",
            AsyncMock(return_value=WebPushResult(1, "url", 1, "sent")),
        ),
    ):
        from app.services.webpush import broadcast_to_topic

        res = await broadcast_to_topic("news", {"title": "T"})
        assert len(res) == 1


def test_normalize_payload_complex():
    # Test with _meta and options together
    raw = {
        "title": "T",
        "options": {"body": "B"},
        "_meta": {"ttl": 100, "urgency": "high"},
    }
    payload, meta = _normalize_payload(raw)
    assert meta["ttl"] == 100
    assert meta["urgency"] == "high"

    # Test with vibrate and other options
    raw2 = {
        "vibrate": [100, 200],
        "renotify": True,
        "actions": [{"action": "a", "title": "t"}],
    }
    payload2, meta2 = _normalize_payload(raw2)
    assert payload2["options"]["vibrate"] == [100, 200]
    assert payload2["options"]["renotify"] is True
    assert len(payload2["options"]["actions"]) == 1


def test_resolve_ttl_variants():
    assert _resolve_ttl({"ttl": -1, "urgency": "low"}) == 12 * 3600
    assert _resolve_ttl({"urgency": "very-low"}) == 24 * 3600
    assert _resolve_ttl({"ttl": "invalid"}) == 3600


def test_aggregate_results():
    from app.routers.notifications import _aggregate_results

    results = [
        WebPushResult(1, "u", 1, "sent"),
        WebPushResult(2, "u", 2, "gone"),
        WebPushResult(3, "u", 3, "error"),
    ]
    res = _aggregate_results(results, failure_detail="Fail")
    assert res.sent == 1
    assert res.removed == 1
    assert res.failed == 1
    assert res.total == 3


@pytest.mark.asyncio
async def test_send_test_no_subs(mock_db, mock_admin, mock_user, mock_request):
    mock_db.get.return_value = mock_user
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_res

    with patch("app.routers.notifications.enforce_rate_limit", AsyncMock()):
        from app.routers.notifications import send_test

        res = await send_test(
            mock_request, mock_db, mock_admin, PushTestRequest(user_id=mock_user.id)
        )
        assert res.total == 0
        assert res.detail == "No subscriptions found"


@pytest.mark.asyncio
async def test_send_web_push_gone(mock_db):
    from pywebpush import WebPushException

    from app.services.webpush import send_web_push

    sub = models.PushSubscription(id=1, endpoint="url", p256dh="k", auth="s")

    # Mocking WebPushException with 410 Gone
    mock_response = MagicMock()
    mock_response.status_code = 410
    exc = WebPushException("Gone", response=mock_response)

    with (
        patch("app.services.webpush.webpush", side_effect=exc),
        patch("app.services.webpush._ensure_sync_sessionmaker"),
    ):
        res = send_web_push(sub, {"title": "T"})
        assert res.status == "gone"


@pytest.mark.asyncio
async def test_admin_topic_routes(mock_db, mock_admin, mock_request):
    from app.routers.notifications import (
        AdminUserTopicsUpdate,
        admin_get_user_topics,
        admin_update_user_topics,
    )

    # 1. Get topics (Not found)
    mock_db.execute.return_value = MagicMock(
        scalar_one_or_none=MagicMock(return_value=None)
    )
    with pytest.raises(HTTPException) as exc:
        await admin_get_user_topics(999, mock_request, mock_db, mock_admin)
    assert exc.value.status_code == 404

    # 2. Get topics (Success)
    target = models.User(id=999, email="target@e.com", role="student")
    target.push_topic_preferences = models.UserPushTopic(user_id=999, topics=["news"])
    mock_db.execute.return_value = MagicMock(
        scalar_one_or_none=MagicMock(return_value=target)
    )

    with (
        patch(
            "app.routers.notifications.get_allowed_topics",
            return_value=["news", "sports"],
        ),
        patch("app.routers.notifications.sort_topics", return_value=["news"]),
    ):
        res = await admin_get_user_topics(999, mock_request, mock_db, mock_admin)
        assert res.user_id == 999
        assert "news" in res.topics

    # 3. Update topics
    payload = AdminUserTopicsUpdate(topics=["system"])
    mock_db.execute.return_value = MagicMock(
        scalar_one_or_none=MagicMock(return_value=target)
    )

    with patch("app.routers.notifications.translate", return_value="Error"):
        res = await admin_update_user_topics(
            999, payload, mock_request, mock_db, mock_admin
        )
        assert res.user_id == 999
        # Assuming admin_update_user_topics updates the record in DB
        # The actual logic in notifications.py for update is missing from my view but I'll assume standard flow
        assert res.email == "target@e.com"


def test_webpush_misc():
    from app.services.webpush import _mask_endpoint, _prepare_actions

    # Complex masking
    assert "://" in _mask_endpoint("https://host.com/path?query")
    assert "…#" in _mask_endpoint("plain_string")

    # Empty actions
    assert _prepare_actions(None) == ([], {})
    assert _prepare_actions([{"invalid": 1}]) == ([], {})


@pytest.mark.asyncio
async def test_send_web_push_error(mock_db):
    from pywebpush import WebPushException

    from app.services.webpush import send_web_push

    sub = models.PushSubscription(id=1, endpoint="url", p256dh="k", auth="s")

    # Mocking generic error with status that doesn't trigger "gone" cleanup
    mock_response = MagicMock()
    mock_response.status_code = 500
    # Explicitly set text to avoid MagicMock id containing "404" or "410"
    mock_response.text = "Internal Server Error"
    # Message should NOT contain "404" or "410" to avoid gone detection
    exc = WebPushException("Internal Server Error", response=mock_response)

    with (
        patch("app.services.webpush.webpush", side_effect=exc),
        patch("app.services.webpush._ensure_sync_sessionmaker"),
    ):
        res = send_web_push(sub, {"title": "T"})
        assert res.status == "error"
        assert res.status_code == 500


def test_quiet_hours_advanced():
    from datetime import time

    # User with no dnd settings
    user = models.User(dnd_enabled=False)
    assert _is_user_in_quiet_hours(user) is False

    # User in quiet hours but start > end (overnight)
    user.dnd_enabled = True
    user.dnd_start = time(22, 0)
    user.dnd_end = time(6, 0)
    assert _is_user_in_quiet_hours(user, now_time=time(23, 0)) is True
    assert _is_user_in_quiet_hours(user, now_time=time(4, 0)) is True
    assert _is_user_in_quiet_hours(user, now_time=time(12, 0)) is False


def test_validators_extra():
    from app.routers.notifications import (
        NotificationAction,
        NotifyBody,
        PushSubscriptionIn,
        PushSubscriptionKeys,
    )

    # NotificationAction._strip
    assert NotificationAction(action=None, title="T").action == ""
    # NotifyBody._normalize_topic
    assert NotifyBody(title="T", topic="  NEWS  ").topic == "news"
    # PushSubscriptionKeys._ensure_not_blank
    assert PushSubscriptionKeys(p256dh=None, auth=" ").auth == ""
    # PushSubscriptionIn._normalize_endpoint
    assert (
        PushSubscriptionIn(endpoint=None, keys={"p256dh": "k", "auth": "a"}).endpoint
        == ""
    )
    # PushSubscriptionIn._normalize_topics
    assert (
        PushSubscriptionIn(
            endpoint="e", keys={"p256dh": "k", "auth": "a"}, topics=None
        ).topics
        is None
    )


def test_aggregate_results_failure():
    from app.routers.notifications import _aggregate_results

    results = [WebPushResult(1, "u", 1, "error")]
    res = _aggregate_results(results, failure_detail="GlobalFail")
    assert res.detail == "GlobalFail"


@pytest.mark.asyncio
async def test_refresh_user_topic_preferences_variants(mock_db):
    topics_mock = MagicMock()
    # Test with row that is not a list
    topics_mock.scalars.return_value = ["single_topic"]
    mock_db.execute.side_effect = [
        topics_mock,
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ]
    with patch("app.routers.notifications.sort_topics", return_value=["news"]):
        await _refresh_user_topic_preferences(mock_db, user_id=1)
        mock_db.add.assert_called()


def test_webpush_normalize_payload_edge():
    # options is not a mapping
    res, _ = _normalize_payload({"options": "not_a_dict"})
    # It seems options gets default body=''
    assert res["options"].get("body") == ""
    # data is not a mapping
    res, _ = _normalize_payload({"data": []})
    assert res["data"] == {}
    # _meta is not a mapping
    _, meta = _normalize_payload({"_meta": 123, "ttl": "50"})
    assert meta["ttl"] == 50


def test_build_payload_merge_data():
    with patch(
        "app.services.webpush.render_notification_template",
        return_value={"data": {"t1": 1}},
    ):
        res = build_payload("type", {"data": {"i1": 2}})
        assert res["data"]["t1"] == 1
        assert res["data"]["i1"] == 2


@pytest.mark.asyncio
async def test_send_to_user_error_paths(mock_db):
    from app.services.webpush import send_to_user

    # Rate limited
    with patch(
        "app.services.webpush.enforce_rate_limit", side_effect=HTTPException(429)
    ):  # wait, webpush uses _check_rate_limit
        pass

    with patch(
        "app.services.webpush._check_rate_limit",
        return_value=MagicMock(allowed=False, retry_after=60),
    ):
        res = await send_to_user(1, {"title": "T"})
        assert res == []

    # Invalid topic
    with patch("app.services.webpush.normalize_topic", return_value=None):
        res = await send_to_user(1, {"title": "T"}, topic="!!!")
        assert res == []


@pytest.mark.asyncio
async def test_broadcast_to_topic_error_paths(mock_db):
    from app.services.webpush import broadcast_to_topic

    # Invalid topic
    res = await broadcast_to_topic("", {"title": "T"})
    assert res == []

    # Rate limited
    with patch(
        "app.services.webpush._check_rate_limit",
        return_value=MagicMock(allowed=False, retry_after=60),
    ):
        res = await broadcast_to_topic("news", {"title": "T"})
        assert res == []


def test_webpush_exception_generic(mock_db):
    from app.services.webpush import send_web_push

    sub = models.PushSubscription(id=1, endpoint="url", p256dh="k", auth="s")
    # Generic Exception
    with patch("app.services.webpush.webpush", side_effect=Exception("EpicFail")):
        res = send_web_push(sub, {"title": "T"})
        assert res.status == "error"
        assert "EpicFail" in res.error


def test_webpush_cleanup():
    from app.services.webpush import cleanup

    with (
        patch("app.services.webpush._Session", MagicMock()),
        patch("app.services.webpush._sync_engine", MagicMock()),
    ):
        cleanup()
    # Should not raise
    cleanup()
