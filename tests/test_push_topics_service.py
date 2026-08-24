"""Behavioral tests for app/services/push_topics.py.

Covers normalize_topic, normalize_topics, resolve_topics, sort_topics,
get_allowed_topics, subscription_supports_topic, and async DB operations.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.push_topics import (
    get_allowed_topics,
    normalize_topic,
    normalize_topics,
    resolve_topics,
    sort_topics,
    subscription_supports_topic,
    synchronize_user_topics,
    upsert_user_topics,
)

# Minimal set of allowed topics for tests
ALLOWED = ["news", "events", "announcements"]


# ---------------------------------------------------------------------------
# normalize_topic
# ---------------------------------------------------------------------------


def test_normalize_topic_valid():
    result = normalize_topic("news", allowed_topics=ALLOWED)
    assert result == "news"


def test_normalize_topic_case_insensitive():
    result = normalize_topic("NEWS", allowed_topics=ALLOWED)
    assert result == "news"


def test_normalize_topic_with_whitespace():
    result = normalize_topic("  events  ", allowed_topics=ALLOWED)
    assert result == "events"


def test_normalize_topic_none_returns_none():
    result = normalize_topic(None, allowed_topics=ALLOWED)
    assert result is None


def test_normalize_topic_empty_string_returns_none():
    result = normalize_topic("", allowed_topics=ALLOWED)
    assert result is None


def test_normalize_topic_whitespace_only_returns_none():
    result = normalize_topic("   ", allowed_topics=ALLOWED)
    assert result is None


def test_normalize_topic_unknown_returns_none():
    result = normalize_topic("unknown-topic", allowed_topics=ALLOWED)
    assert result is None


def test_normalize_topic_strict_raises():
    with pytest.raises(ValueError, match="Unknown notification topic"):
        normalize_topic("bad-topic", allowed_topics=ALLOWED, strict=True)


def test_normalize_topic_valid_strict():
    result = normalize_topic("news", allowed_topics=ALLOWED, strict=True)
    assert result == "news"


# ---------------------------------------------------------------------------
# normalize_topics
# ---------------------------------------------------------------------------


def test_normalize_topics_empty_input():
    result = normalize_topics(None, allowed_topics=ALLOWED)
    assert result == []


def test_normalize_topics_valid_list():
    result = normalize_topics(["news", "events"], allowed_topics=ALLOWED)
    assert "news" in result
    assert "events" in result


def test_normalize_topics_deduplicates():
    result = normalize_topics(["news", "news", "NEWS"], allowed_topics=ALLOWED)
    assert result.count("news") == 1


def test_normalize_topics_filters_unknown():
    result = normalize_topics(["news", "unknown"], allowed_topics=ALLOWED)
    assert "unknown" not in result
    assert "news" in result


def test_normalize_topics_empty_list():
    result = normalize_topics([], allowed_topics=ALLOWED)
    assert result == []


def test_normalize_topics_all_unknown():
    result = normalize_topics(["bad1", "bad2"], allowed_topics=ALLOWED)
    assert result == []


# ---------------------------------------------------------------------------
# sort_topics
# ---------------------------------------------------------------------------


def test_sort_topics_ordered_by_allowed_list():
    topics = ["events", "news"]
    allowed = ["news", "events", "announcements"]
    result = sort_topics(topics, allowed_topics=allowed)
    assert result == ["news", "events"]


def test_sort_topics_none_input():
    result = sort_topics(None, allowed_topics=ALLOWED)
    assert result == []


def test_sort_topics_unknown_topics_go_to_end():
    # Unknown topics not in allowed list should be filtered out by normalize
    result = sort_topics(["unknown", "news"], allowed_topics=ALLOWED)
    assert "unknown" not in result
    assert "news" in result


# ---------------------------------------------------------------------------
# resolve_topics
# ---------------------------------------------------------------------------


def test_resolve_topics_none_falls_back_to_existing():
    existing = ["news", "events"]
    result = resolve_topics(None, existing=existing, allowed_topics=ALLOWED)
    assert "news" in result
    assert "events" in result


def test_resolve_topics_raw_topics_used_when_provided():
    result = resolve_topics(["news"], existing=["events"], allowed_topics=ALLOWED)
    assert "news" in result
    assert "events" not in result  # raw_topics overrides existing


def test_resolve_topics_none_raw_and_none_existing():
    result = resolve_topics(None, existing=None, allowed_topics=ALLOWED)
    assert result == []


# ---------------------------------------------------------------------------
# get_allowed_topics
# ---------------------------------------------------------------------------


def test_get_allowed_topics_with_mock_settings():
    mock_settings = MagicMock()
    mock_settings.notifications_allowed_push_topics_list = ["news", "events"]
    result = get_allowed_topics(mock_settings)
    assert "news" in result
    assert "events" in result


# ---------------------------------------------------------------------------
# subscription_supports_topic
# ---------------------------------------------------------------------------


def test_subscription_supports_topic_none_topic():
    """Unknown/None topic → always supported."""
    mock_sub = MagicMock()
    result = subscription_supports_topic(mock_sub, None, allowed_topics=ALLOWED)
    assert result is True


def test_subscription_supports_topic_none_subscription():
    """Valid topic + None subscription → not supported."""
    result = subscription_supports_topic(None, "news", allowed_topics=ALLOWED)
    assert result is False


def test_subscription_supports_topic_unknown_topic():
    """Unknown topic (not in allowed list) → normalize returns None → supported."""
    mock_sub = MagicMock()
    result = subscription_supports_topic(
        mock_sub, "unknown-topic", allowed_topics=ALLOWED
    )
    assert result is True


def test_subscription_supports_topic_no_preferences():
    """Subscription with no user preferences subscribes to all topics."""
    mock_sub = MagicMock()
    mock_sub.user = None
    mock_sub.topics = ["news"]

    result = subscription_supports_topic(mock_sub, "news", allowed_topics=ALLOWED)
    assert result is True


def test_subscription_supports_topic_empty_stored_topics():
    """When subscription has no stored topics, preference is all-inclusive."""
    mock_sub = MagicMock()
    mock_sub.user = None
    mock_sub.topics = []  # no stored restriction

    result = subscription_supports_topic(mock_sub, "news", allowed_topics=ALLOWED)
    assert result is True


def test_subscription_supports_topic_not_in_stored_list():
    """Topic not in subscription stored topics → not supported."""
    mock_sub = MagicMock()
    mock_sub.user = None
    mock_sub.topics = ["events"]

    result = subscription_supports_topic(mock_sub, "news", allowed_topics=ALLOWED)
    assert result is False


def test_subscription_supports_topic_with_user_preferences():
    """User preferences restrict allowed topics."""

    mock_prefs = MagicMock()
    mock_prefs.topics = ["news"]

    mock_user = MagicMock()
    mock_user.push_topic_preferences = mock_prefs

    mock_sub = MagicMock()
    mock_sub.user = mock_user
    mock_sub.topics = ["news", "events"]

    # Patch orm_attributes.instance_state to simulate loaded state
    mock_state = MagicMock()
    mock_state.unloaded = set()  # nothing unloaded

    with patch(
        "app.services.push_topics.orm_attributes.instance_state",
        return_value=mock_state,
    ):
        result = subscription_supports_topic(mock_sub, "news", allowed_topics=ALLOWED)
    assert result is True


def test_subscription_supports_topic_user_prefs_deny():
    """User preferences don't include topic → denied even if sub has it."""

    mock_prefs = MagicMock()
    mock_prefs.topics = ["events"]  # user only wants events

    mock_user = MagicMock()
    mock_user.push_topic_preferences = mock_prefs

    mock_sub = MagicMock()
    mock_sub.user = mock_user
    mock_sub.topics = ["news", "events"]

    mock_state = MagicMock()
    mock_state.unloaded = set()

    with patch(
        "app.services.push_topics.orm_attributes.instance_state",
        return_value=mock_state,
    ):
        result = subscription_supports_topic(mock_sub, "news", allowed_topics=ALLOWED)
    assert result is False


# ---------------------------------------------------------------------------
# upsert_user_topics (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_user_topics_creates_new_record():
    db = AsyncMock()
    db.add = MagicMock()
    user_id = uuid.uuid4()

    # No existing record
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result

    result = await upsert_user_topics(
        db, user_id=user_id, topics=["news"], allowed_topics=ALLOWED
    )

    db.add.assert_called_once()
    assert "news" in result


@pytest.mark.asyncio
async def test_upsert_user_topics_updates_existing_record():
    db = AsyncMock()
    user_id = uuid.uuid4()

    existing = MagicMock()
    existing.topics = ["events"]
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    db.execute.return_value = mock_result

    result = await upsert_user_topics(
        db, user_id=user_id, topics=["news"], allowed_topics=ALLOWED
    )

    assert existing.topics == ["news"]
    assert "news" in result


@pytest.mark.asyncio
async def test_upsert_user_topics_filters_unknown():
    db = AsyncMock()
    db.add = MagicMock()
    user_id = uuid.uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result

    result = await upsert_user_topics(
        db, user_id=user_id, topics=["news", "unknown-bad"], allowed_topics=ALLOWED
    )

    assert "unknown-bad" not in result
    assert "news" in result


# ---------------------------------------------------------------------------
# synchronize_user_topics (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synchronize_user_topics_updates_subscriptions():
    db = AsyncMock()
    db.add = MagicMock()
    user_id = uuid.uuid4()

    # No existing UserPushTopic
    mock_upsert_result = MagicMock()
    mock_upsert_result.scalar_one_or_none.return_value = None

    # Two subscriptions
    sub1 = MagicMock()
    sub2 = MagicMock()
    mock_subs_result = MagicMock()
    mock_subs_result.scalars.return_value.all.return_value = [sub1, sub2]

    db.execute.side_effect = [mock_upsert_result, mock_subs_result]

    result = await synchronize_user_topics(
        db, user_id=user_id, topics=["news", "events"], allowed_topics=ALLOWED
    )

    assert sub1.topics == result
    assert sub2.topics == result
    assert "news" in result
    assert "events" in result
