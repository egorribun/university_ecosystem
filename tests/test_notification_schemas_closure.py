"""Behavioral closure tests for push notification schemas."""

from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.notifications import (
    AdminUserTopicsUpdate,
    NotificationAction,
    NotifyBody,
    PushSubscriptionDelete,
    PushSubscriptionIn,
    PushSubscriptionKeys,
    PushSubscriptionOut,
    PushSubscriptionTopicsUpdate,
)


def test_notification_action_and_subscription_keys_normalize_none_and_values():
    action = NotificationAction(action=None, title="  Open  ")
    keys = PushSubscriptionKeys(p256dh=None, auth="  secret  ")

    assert action.action == ""
    assert action.title == "Open"
    assert keys.p256dh == ""
    assert keys.auth == "secret"


def test_push_subscription_input_normalizes_endpoint_and_optional_topics():
    empty_topics = PushSubscriptionIn(
        endpoint=None,
        keys={"p256dh": "p256", "auth": "auth"},
        topics=None,
    )
    normalized_topics = PushSubscriptionIn(
        endpoint="  https://push.example  ",
        keys={"p256dh": "p256", "auth": "auth"},
        topics=["news", " news ", ""],
    )

    assert empty_topics.endpoint == ""
    assert empty_topics.topics is None
    assert normalized_topics.endpoint == "https://push.example"
    assert normalized_topics.topics == ["news"]


def test_push_subscription_output_handles_empty_and_legacy_topics_values():
    common = {
        "id": uuid4(),
        "user_id": uuid4(),
        "endpoint": "https://push.example",
        "p256dh": "p256",
        "auth": "auth",
        "created_at": datetime.now(UTC),
    }

    assert PushSubscriptionOut(**common, topics=None).topics == []
    assert PushSubscriptionOut(**common, topics="legacy").topics == []
    assert PushSubscriptionOut(**common, topics=["news", " news "]).topics == ["news"]


def test_push_subscription_update_and_delete_accept_none_endpoints_and_topics():
    update = PushSubscriptionTopicsUpdate(endpoint=None, topics=None)
    delete = PushSubscriptionDelete(endpoint=None)

    assert update.endpoint == ""
    assert update.topics == []
    assert delete.endpoint == ""

    normalized_update = PushSubscriptionTopicsUpdate(
        endpoint="  https://push.example  ", topics=["news", " news "]
    )
    normalized_delete = PushSubscriptionDelete(endpoint="  https://push.example  ")
    assert normalized_update.endpoint == "https://push.example"
    assert normalized_update.topics == ["news"]
    assert normalized_delete.endpoint == "https://push.example"


def test_notify_body_normalizes_topics():
    assert NotifyBody(title="Title", topic=None).topic is None
    assert NotifyBody(title="Title", topic="  news  ").topic == "news"


def test_admin_topics_update_accepts_none_and_strictly_normalizes_values():
    empty = AdminUserTopicsUpdate(topics=None)
    normalized = AdminUserTopicsUpdate(topics=["news", " news "])

    assert empty.topics == []
    assert normalized.topics == ["news"]
