from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.schemas import notifications
from app.services import push_topics


@pytest.fixture(autouse=True)
def allowed_topics(monkeypatch):
    monkeypatch.setattr(
        push_topics,
        "app_settings",
        type(
            "Settings",
            (),
            {
                "notifications_allowed_push_topics_set": frozenset(
                    {"news", "events", "system"}
                ),
                "notifications_allowed_push_topics_list": ["news", "events", "system"],
            },
        )(),
    )


def test_notification_action_and_body_normalize_values():
    action = notifications.NotificationAction(action=None, title="  Open  ", url=None)
    assert action.action == ""
    assert action.title == "Open"

    body = notifications.NotifyBody(title="Title", topic=" NEWS ", actions=[action])
    assert body.topic == "news"
    assert body.actions == [action]
    assert notifications.NotifyBody(title="Title", topic=None).topic is None


def test_subscription_input_validators_cover_none_and_topic_lists():
    keys = notifications.PushSubscriptionKeys(p256dh=None, auth=" secret ")
    assert keys.p256dh == ""
    assert keys.auth == "secret"

    payload = notifications.PushSubscriptionIn(
        endpoint=None,
        keys=keys,
        topics=["news", "NEWS", "unknown"],
    )
    assert payload.endpoint == ""
    assert payload.topics == ["news"]
    assert (
        notifications.PushSubscriptionIn(endpoint="x", keys=keys, topics=None).topics
        is None
    )


def test_subscription_output_topics_from_attributes_and_fallbacks():
    now = datetime.now(UTC)
    values = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "endpoint": "https://push.example/sub",
        "p256dh": "p256dh",
        "auth": "auth",
        "created_at": now,
        "topics": ["events", "events", "unknown"],
    }
    output = notifications.PushSubscriptionOut.model_validate(values)
    assert output.topics == ["events"]
    assert (
        notifications.PushSubscriptionOut.model_validate(
            {**values, "topics": None}
        ).topics
        == []
    )
    assert (
        notifications.PushSubscriptionOut.model_validate(
            {**values, "topics": "events"}
        ).topics
        == []
    )


def test_topic_update_delete_and_admin_strict_validation():
    keys = notifications.PushSubscriptionTopicsUpdate(endpoint=None, topics=None)
    assert keys.endpoint == ""
    assert keys.topics == []

    populated = notifications.PushSubscriptionTopicsUpdate(
        endpoint=" endpoint ", topics=["system", "system", "unknown"]
    )
    assert populated.endpoint == "endpoint"
    assert populated.topics == ["system"]
    assert notifications.PushSubscriptionDelete(endpoint=None).endpoint == ""
    assert (
        notifications.PushSubscriptionDelete(endpoint=" endpoint ").endpoint
        == "endpoint"
    )

    assert notifications.AdminUserTopicsUpdate(topics=None).topics == []
    assert notifications.AdminUserTopicsUpdate(topics=["news", "news"]).topics == [
        "news"
    ]
    with pytest.raises(ValueError, match="Unknown notification topic"):
        notifications.AdminUserTopicsUpdate(topics=["unknown"])


def test_notification_response_models_and_defaults():
    user_id = uuid.uuid4()
    assert notifications.DisableUserPushRequest(user_id=user_id).user_id == user_id
    response = notifications.PushTopicsResponse(allowed=["news"], topics=["news"])
    assert response.has_preferences is False
    assert response.updated_at is None

    admin = notifications.AdminUserTopicsResponse(
        user_id=user_id,
        email="user@example.com",
        topics=["news"],
        allowed_topics=["news", "events"],
    )
    assert admin.updated_at is None

    sent = notifications.SendTestResponse(sent=1, removed=0, failed=0)
    assert sent.total == 0
    assert sent.detail is None


def test_push_test_request_inherits_notify_body_defaults():
    request = notifications.PushTestRequest()
    assert request.title
    assert request.body
    assert request.topic is None
    custom = notifications.PushTestRequest(title="Custom", topic="events")
    assert custom.title == "Custom"
    assert custom.topic == "events"
