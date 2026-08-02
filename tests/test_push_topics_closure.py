"""Deterministic closure tests for push-topic settings and persistence helpers."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.push_topics import (
    normalize_topic,
    subscription_supports_topic,
    synchronize_user_topics,
    upsert_user_topics,
)


class _Result:
    def __init__(self, scalar=None, rows=()):
        self._scalar = scalar
        self._rows = rows

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _Database:
    def __init__(self, *results):
        self._results = list(results)
        self.added = []

    async def execute(self, _statement):
        return self._results.pop(0)

    def add(self, value):
        self.added.append(value)


def test_settings_backed_topic_resolution_uses_topic_set():
    settings = MagicMock()
    settings.notifications_allowed_push_topics_set = frozenset({"news"})

    assert normalize_topic(" NEWS ", settings_obj=settings) == "news"
    assert normalize_topic("alerts", settings_obj=settings) is None


def test_subscription_topic_checks_loaded_preferences_and_state_errors():
    user = SimpleNamespace(
        push_topic_preferences=SimpleNamespace(topics=["news"]),
    )
    subscription = SimpleNamespace(user=user, topics=None)

    with patch(
        "app.services.push_topics.orm_attributes.instance_state",
        return_value=SimpleNamespace(unloaded=set()),
    ):
        assert (
            subscription_supports_topic(
                subscription,
                "news",
                allowed_topics=["news"],
            )
            is True
        )

    with patch(
        "app.services.push_topics.orm_attributes.instance_state",
        side_effect=TypeError("detached"),
    ):
        assert (
            subscription_supports_topic(
                subscription,
                "news",
                allowed_topics=["news"],
            )
            is True
        )

    with patch(
        "app.services.push_topics.orm_attributes.instance_state",
        return_value=SimpleNamespace(unloaded={"push_topic_preferences"}),
    ):
        assert (
            subscription_supports_topic(
                subscription,
                "news",
                allowed_topics=["news"],
            )
            is True
        )


@pytest.mark.asyncio
async def test_upsert_user_topics_creates_and_updates_without_commit():
    user_id = uuid.uuid4()
    create_db = _Database(_Result(None))

    created = await upsert_user_topics(
        create_db,
        user_id=user_id,
        topics=["NEWS", "unknown"],
        allowed_topics=["news"],
    )

    assert created == ["news"]
    assert create_db.added[0].topics == ["news"]

    existing = SimpleNamespace(topics=[])
    update_db = _Database(_Result(existing))
    updated = await upsert_user_topics(
        update_db,
        user_id=user_id,
        topics=["news"],
        allowed_topics=["news"],
    )

    assert updated == ["news"]
    assert existing.topics == ["news"]
    assert update_db.added == []


@pytest.mark.asyncio
async def test_synchronize_user_topics_mirrors_preferences_to_subscriptions():
    user_id = uuid.uuid4()
    preference = SimpleNamespace(topics=[])
    subscriptions = [SimpleNamespace(topics=["old"]), SimpleNamespace(topics=None)]
    db = _Database(_Result(preference), _Result(rows=subscriptions))

    result = await synchronize_user_topics(
        db,
        user_id=user_id,
        topics=["news", "unknown"],
        allowed_topics=["news"],
    )

    assert result == ["news"]
    assert preference.topics == ["news"]
    assert [subscription.topics for subscription in subscriptions] == [
        ["news"],
        ["news"],
    ]
