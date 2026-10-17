from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone, tzinfo
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.models.stories import Story
from scripts import seed_demo_data

FROZEN_NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz: tzinfo | None = None) -> datetime:
        assert tz is UTC
        return FROZEN_NOW


def _story_row(
    owner_id,
    *,
    short_text: str | None = None,
    cover_url: str | None = None,
    is_active: bool = False,
    expires_at: datetime | None = None,
) -> Story:
    item = seed_demo_data.STORIES_DATA[0]
    story = Story(
        title=item["title"],
        title_en=item["title_en"],
        short_text=short_text if short_text is not None else item["short_text"],
        short_text_en=item["short_text_en"],
        cover_url=cover_url if cover_url is not None else item["cover_url"],
        cta_url=None,
        is_active=is_active,
        published_at=FROZEN_NOW - timedelta(days=10),
        expires_at=expires_at or FROZEN_NOW - timedelta(days=1),
        created_by=owner_id,
    )
    return story


def _session_for(existing: Story | None) -> SimpleNamespace:
    return SimpleNamespace(
        scalar=AsyncMock(return_value=existing),
        flush=AsyncMock(),
        add=Mock(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("naive_expiry", [False, True])
async def test_seed_reactivates_expired_owned_story_with_exact_seed_content(
    monkeypatch: pytest.MonkeyPatch,
    naive_expiry: bool,
) -> None:
    monkeypatch.setattr(seed_demo_data, "STORIES_DATA", seed_demo_data.STORIES_DATA[:1])
    monkeypatch.setattr(seed_demo_data, "datetime", FrozenDateTime)
    owner = SimpleNamespace(id=uuid4())
    expired_at = FROZEN_NOW - timedelta(days=1)
    if naive_expiry:
        expired_at = expired_at.replace(tzinfo=None)
    story = _story_row(owner.id, expires_at=expired_at)
    session = _session_for(story)
    original = {
        "title": story.title,
        "title_en": story.title_en,
        "short_text": story.short_text,
        "short_text_en": story.short_text_en,
        "cover_url": story.cover_url,
        "cta_url": story.cta_url,
        "published_at": story.published_at,
        "created_by": story.created_by,
    }

    await seed_demo_data.seed_stories(session, owner)

    assert story.is_active is True
    assert story.expires_at == FROZEN_NOW + timedelta(days=365)
    assert {field: getattr(story, field) for field in original} == original
    session.add.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("expiry_zone", "initial_active"),
    [("utc", False), ("naive", True), ("offset", False)],
)
async def test_reseeding_expired_owned_story_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    expiry_zone: str,
    initial_active: bool,
) -> None:
    monkeypatch.setattr(seed_demo_data, "STORIES_DATA", seed_demo_data.STORIES_DATA[:1])
    monkeypatch.setattr(seed_demo_data, "datetime", FrozenDateTime)
    owner = SimpleNamespace(id=uuid4())
    expiry_at_boundary = FROZEN_NOW
    if expiry_zone == "naive":
        expiry_at_boundary = expiry_at_boundary.replace(tzinfo=None)
    elif expiry_zone == "offset":
        expiry_at_boundary = expiry_at_boundary.astimezone(timezone(timedelta(hours=3)))
    story = _story_row(
        owner.id,
        is_active=initial_active,
        expires_at=expiry_at_boundary,
    )
    session = _session_for(story)

    await seed_demo_data.seed_stories(session, owner)
    first_expiry = story.expires_at
    await seed_demo_data.seed_stories(session, owner)

    assert story.is_active is True
    assert story.expires_at == first_expiry == FROZEN_NOW + timedelta(days=365)
    assert session.scalar.await_count == 2
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_seed_preserves_inactive_story_that_has_not_expired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(seed_demo_data, "STORIES_DATA", seed_demo_data.STORIES_DATA[:1])
    monkeypatch.setattr(seed_demo_data, "datetime", FrozenDateTime)
    owner = SimpleNamespace(id=uuid4())
    future_expiry = FROZEN_NOW + timedelta(days=30)
    story = _story_row(owner.id, is_active=False, expires_at=future_expiry)
    session = _session_for(story)

    await seed_demo_data.seed_stories(session, owner)

    assert story.is_active is False
    assert story.expires_at == future_expiry
    session.add.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "edited_field",
    ["short_text", "cover_url", "title_en", "short_text_en", "cta_url"],
)
async def test_seed_does_not_reactivate_story_with_edited_seed_content(
    monkeypatch: pytest.MonkeyPatch,
    edited_field: str,
) -> None:
    monkeypatch.setattr(seed_demo_data, "STORIES_DATA", seed_demo_data.STORIES_DATA[:1])
    monkeypatch.setattr(seed_demo_data, "datetime", FrozenDateTime)
    owner = SimpleNamespace(id=uuid4())
    item = seed_demo_data.STORIES_DATA[0]
    story = _story_row(owner.id)
    setattr(story, edited_field, f"user-edited {edited_field}")
    session = _session_for(story)
    before = {
        "title": story.title,
        "short_text": story.short_text,
        "cover_url": story.cover_url,
        "is_active": story.is_active,
        "expires_at": story.expires_at,
    }

    await seed_demo_data.seed_stories(session, owner)

    assert {field: getattr(story, field) for field in before} == before
    assert getattr(story, edited_field) != item.get(edited_field)
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_edited_translation_is_preserved_while_other_translation_backfills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(seed_demo_data, "STORIES_DATA", seed_demo_data.STORIES_DATA[:1])
    monkeypatch.setattr(seed_demo_data, "datetime", FrozenDateTime)
    owner = SimpleNamespace(id=uuid4())
    story = _story_row(owner.id)
    story.title_en = "User-edited English headline"
    story.short_text_en = None
    session = _session_for(story)
    before_lifecycle = (story.is_active, story.expires_at)

    await seed_demo_data.seed_stories(session, owner)

    assert (story.is_active, story.expires_at) == before_lifecycle
    assert story.title_en == "User-edited English headline"
    assert story.short_text_en == seed_demo_data.STORIES_DATA[0]["short_text_en"]
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_seed_does_not_reactivate_same_title_story_from_another_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(seed_demo_data, "STORIES_DATA", seed_demo_data.STORIES_DATA[:1])
    monkeypatch.setattr(seed_demo_data, "datetime", FrozenDateTime)
    owner = SimpleNamespace(id=uuid4())
    other_owner = uuid4()
    story = _story_row(other_owner)
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[None, story]),
        flush=AsyncMock(),
        add=Mock(),
    )
    before = (story.is_active, story.expires_at, story.created_by)

    await seed_demo_data.seed_stories(session, owner)

    assert (story.is_active, story.expires_at, story.created_by) == before
    session.add.assert_not_called()
