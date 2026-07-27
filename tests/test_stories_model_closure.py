"""Closure tests for the Story model lifecycle hooks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import inspect

from app.models.stories import Story, _set_story_expiration, _utcnow


def test_utcnow_returns_timezone_aware_datetime():
    value = _utcnow()
    assert value.tzinfo is UTC


def test_story_before_insert_sets_missing_timestamps_from_published_time():
    story = Story(title="Story", short_text="Text")

    _set_story_expiration(None, None, story)

    assert story.published_at is not None
    assert story.expires_at == story.published_at + timedelta(hours=24)


def test_story_before_insert_preserves_published_time_and_fills_only_expiry():
    published_at = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
    story = Story(title="Story", short_text="Text", published_at=published_at)

    _set_story_expiration(None, None, story)

    assert story.published_at == published_at
    assert story.expires_at == published_at + timedelta(hours=24)


def test_story_before_insert_keeps_expiry_missing_if_clock_returns_none():
    story = Story(title="Story", short_text="Text")

    with patch("app.models.stories._utcnow", return_value=None):
        _set_story_expiration(None, None, story)

    assert story.published_at is None
    assert story.expires_at is None


def test_story_before_insert_preserves_both_existing_timestamps():
    published_at = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
    expires_at = published_at + timedelta(hours=1)
    story = Story(
        title="Story",
        short_text="Text",
        published_at=published_at,
        expires_at=expires_at,
    )

    _set_story_expiration(None, None, story)

    assert story.published_at == published_at
    assert story.expires_at == expires_at


def test_story_repr_and_relationship_use_safe_defaults():
    story = Story(title="A short title", short_text="Text", is_active=True)

    assert "Story(" in repr(story)
    assert "A short title" in repr(story)
    assert inspect(Story).relationships["created_by_user"].lazy == "noload"
