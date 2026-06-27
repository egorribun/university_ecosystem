import uuid
from typing import ClassVar
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.models import PushSubscription, UserPushTopic
from app.services import push_topics as pt


def test_get_allowed_topics():
    topics = pt.get_allowed_topics()
    assert isinstance(topics, list)


def test_sort_topics():
    allowed = ["a", "b", "c"]
    sorted_list = pt.sort_topics(["c", "a", "b", "unknown"], allowed_topics=allowed)
    assert sorted_list == ["a", "b", "c"]


def test_normalize_topic():
    allowed = ["news", "alerts"]
    assert pt.normalize_topic(None, allowed_topics=allowed) is None
    assert pt.normalize_topic("", allowed_topics=allowed) is None
    assert pt.normalize_topic("  ", allowed_topics=allowed) is None
    assert pt.normalize_topic("NEWS", allowed_topics=allowed) == "news"
    assert pt.normalize_topic("unknown", allowed_topics=allowed) is None

    with pytest.raises(ValueError, match="Unknown notification topic"):
        pt.normalize_topic("unknown", allowed_topics=allowed, strict=True)


def test_normalize_topics():
    allowed = ["news", "alerts"]
    assert pt.normalize_topics(None, allowed_topics=allowed) == []
    assert pt.normalize_topics(
        ["NEWS", "alerts", "NEWS", "unknown"], allowed_topics=allowed
    ) == ["news", "alerts"]


def test_resolve_topics():
    allowed = ["news", "alerts"]
    assert pt.resolve_topics(
        None, existing=["alerts", "unknown"], allowed_topics=allowed
    ) == ["alerts"]
    assert pt.resolve_topics(["news"], existing=["alerts"], allowed_topics=allowed) == [
        "news"
    ]


def test_subscription_supports_topic_none_topic():
    assert pt.subscription_supports_topic(None, None) is True


def test_subscription_supports_topic_none_subscription():
    assert (
        pt.subscription_supports_topic(None, "news", allowed_topics=["news"]) is False
    )


def test_subscription_supports_topic_user_without_preferences():
    sub = MagicMock(spec=PushSubscription)
    sub.user = None
    sub.topics = None
    assert pt.subscription_supports_topic(sub, "news", allowed_topics=["news"]) is True


def test_subscription_supports_topic_user_with_matching_preferences(monkeypatch):
    class MockPrefs:
        topics: ClassVar[list[str]] = ["news"]

    class MockUser:
        id = "user-123"
        push_topic_preferences = MockPrefs()

    sub = MagicMock(spec=PushSubscription)
    sub.user = MockUser()
    sub.topics = None

    class MockState:
        unloaded: ClassVar[set[str]] = set()

    monkeypatch.setattr(
        "sqlalchemy.orm.attributes.instance_state", lambda obj: MockState()
    )

    assert pt.subscription_supports_topic(sub, "news", allowed_topics=["news"]) is True
    assert (
        pt.subscription_supports_topic(sub, "alerts", allowed_topics=["news", "alerts"])
        is False
    )


def test_subscription_supports_topic_subscription_topics_restriction(monkeypatch):
    class MockPrefs:
        topics: ClassVar[list[str]] = ["news", "alerts"]

    class MockUser:
        id = "user-123"
        push_topic_preferences = MockPrefs()

    sub = MagicMock(spec=PushSubscription)
    sub.user = MockUser()
    sub.topics = ["news"]

    class MockState:
        unloaded: ClassVar[set[str]] = set()

    monkeypatch.setattr(
        "sqlalchemy.orm.attributes.instance_state", lambda obj: MockState()
    )

    assert (
        pt.subscription_supports_topic(sub, "news", allowed_topics=["news", "alerts"])
        is True
    )
    assert (
        pt.subscription_supports_topic(sub, "alerts", allowed_topics=["news", "alerts"])
        is False
    )


@pytest.mark.asyncio
async def test_upsert_user_topics(db_session):
    user_id = uuid.uuid4()
    allowed = ["news", "alerts"]

    # New preference
    topics = await pt.upsert_user_topics(
        db_session, user_id=user_id, topics=["news"], allowed_topics=allowed
    )
    assert topics == ["news"]

    # Verify in DB
    pref = (
        await db_session.execute(
            select(UserPushTopic).where(UserPushTopic.user_id == user_id)
        )
    ).scalar_one()
    assert pref.topics == ["news"]

    # Update existing preference
    topics2 = await pt.upsert_user_topics(
        db_session, user_id=user_id, topics=["news", "alerts"], allowed_topics=allowed
    )
    assert topics2 == ["news", "alerts"]
    assert pref.topics == ["news", "alerts"]


@pytest.mark.asyncio
async def test_synchronize_user_topics(db_session):
    user_id = uuid.uuid4()
    allowed = ["news", "alerts"]

    sub1 = PushSubscription(
        endpoint="https://sub1",
        p256dh="dh1",
        auth="auth1",
        user_id=user_id,
        topics=["news"],
    )
    sub2 = PushSubscription(
        endpoint="https://sub2",
        p256dh="dh2",
        auth="auth2",
        user_id=user_id,
        topics=["alerts"],
    )
    db_session.add_all([sub1, sub2])
    await db_session.flush()

    # Sync topics
    topics = await pt.synchronize_user_topics(
        db_session, user_id=user_id, topics=["news", "alerts"], allowed_topics=allowed
    )
    assert topics == ["news", "alerts"]

    # Verify subscriptions are updated
    assert sub1.topics == ["news", "alerts"]
    assert sub2.topics == ["news", "alerts"]
