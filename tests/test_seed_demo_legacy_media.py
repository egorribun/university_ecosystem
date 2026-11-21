from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from scripts import seed_demo_data

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _legacy_urls() -> dict[str, str]:
    provenance = json.loads(
        (seed_demo_data.DEMO_MEDIA_DIR / "PROVENANCE.json").read_text(encoding="utf-8")
    )
    return {
        seed_demo_data.demo_media_url(entry["file"]): entry["replaces"]
        for entry in provenance["images"]
    }


async def test_reseed_replaces_exact_legacy_media_for_owned_canonical_rows(
    db_session, user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await user_factory()
    legacy = _legacy_urls()
    now = datetime.now(UTC)
    monkeypatch.setattr(
        seed_demo_data, "_event_now_utc", lambda: datetime(2026, 4, 1, tzinfo=UTC)
    )

    news = [
        seed_demo_data.News(
            **{**item, "image_url": legacy[item["image_url"]]}, author_id=owner.id
        )
        for item in seed_demo_data.NEWS_DATA
    ]
    stories = [
        seed_demo_data.Story(
            **{**item, "cover_url": legacy[item["cover_url"]]},
            created_by=owner.id,
            published_at=now - timedelta(days=2),
            expires_at=now - timedelta(days=1),
            is_active=False,
        )
        for item in seed_demo_data.STORIES_DATA
    ]
    events = [
        seed_demo_data.Event(
            **{**item, "image_url": legacy[item["image_url"]]},
            created_by=owner.id,
            is_active=True,
        )
        for item in seed_demo_data.EVENTS_DATA
    ]
    earlier_events = [
        seed_demo_data.Event(
            **{
                **item,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "image_url": legacy[item["image_url"]],
            },
            created_by=owner.id,
            is_active=True,
        )
        for item, starts_at, ends_at in seed_demo_data._event_schedule(
            datetime(2026, 3, 27, 15, tzinfo=UTC)
        )
    ]
    earlier_events[0].is_active = False
    archived = [
        seed_demo_data.Event(
            **{**item, "image_url": legacy[item["image_url"]]},
            created_by=owner.id,
            is_active=False,
        )
        for item in seed_demo_data.ARCHIVE_EVENTS_DATA
    ]
    db_session.add_all([*news, *stories, *events, *earlier_events, *archived])
    await db_session.flush()

    for _ in range(2):
        await seed_demo_data.seed_news(db_session, owner)
        await seed_demo_data.seed_stories(db_session, owner)
        await seed_demo_data.seed_events(db_session, owner)
        await seed_demo_data.seed_archived_events(db_session, owner)

    assert all(
        row.image_url == item["image_url"]
        for row, item in zip(news, seed_demo_data.NEWS_DATA, strict=True)
    )
    assert all(
        row.cover_url == item["cover_url"]
        for row, item in zip(stories, seed_demo_data.STORIES_DATA, strict=True)
    )
    assert all(row.is_active and row.expires_at > now for row in stories)
    assert all(
        row.image_url == item["image_url"]
        for row, item in zip(events, seed_demo_data.EVENTS_DATA, strict=True)
    )
    assert all(
        row.image_url == item["image_url"]
        for row, item in zip(earlier_events, seed_demo_data.EVENTS_DATA, strict=True)
    )
    assert earlier_events[0].is_active is False
    assert all(
        row.image_url == item["image_url"] and row.is_active
        for row, item in zip(archived, seed_demo_data.ARCHIVE_EVENTS_DATA, strict=True)
    )


async def test_reseed_preserves_custom_media_and_edited_source(
    db_session, user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await user_factory()
    other_owner = await user_factory()
    legacy = _legacy_urls()
    now = datetime.now(UTC)
    monkeypatch.setattr(
        seed_demo_data, "_event_now_utc", lambda: datetime(2026, 4, 1, tzinfo=UTC)
    )
    news_item = seed_demo_data.NEWS_DATA[0]
    story_item = seed_demo_data.STORIES_DATA[0]
    event_item = seed_demo_data.EVENTS_DATA[0]
    archive_item = seed_demo_data.ARCHIVE_EVENTS_DATA[0]
    custom_url = "/static/custom.webp"
    news = seed_demo_data.News(
        **{**news_item, "image_url": custom_url}, author_id=owner.id
    )
    story = seed_demo_data.Story(
        **{
            **story_item,
            "short_text": "edited",
            "cover_url": legacy[story_item["cover_url"]],
        },
        created_by=owner.id,
        published_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
        is_active=False,
    )
    event = seed_demo_data.Event(
        **{
            **event_item,
            "description": "edited",
            "image_url": legacy[event_item["image_url"]],
        },
        created_by=owner.id,
        is_active=True,
    )
    archive = seed_demo_data.Event(
        **{
            **archive_item,
            "ends_at": archive_item["ends_at"] + timedelta(hours=1),
            "image_url": legacy[archive_item["image_url"]],
        },
        created_by=owner.id,
        is_active=False,
    )
    foreign_item = seed_demo_data.NEWS_DATA[1]
    foreign = seed_demo_data.News(
        **{**foreign_item, "image_url": legacy[foreign_item["image_url"]]},
        author_id=other_owner.id,
    )
    other_news_item = seed_demo_data.NEWS_DATA[2]
    different_legacy_url = legacy[seed_demo_data.NEWS_DATA[3]["image_url"]]
    mismatch = seed_demo_data.News(
        **{**other_news_item, "image_url": different_legacy_url}, author_id=owner.id
    )
    shifted_item = seed_demo_data.EVENTS_DATA[1]
    shifted = seed_demo_data.Event(
        **{
            **shifted_item,
            "starts_at": shifted_item["starts_at"] + timedelta(days=1),
            "ends_at": shifted_item["ends_at"] + timedelta(days=1),
            "image_url": legacy[shifted_item["image_url"]],
        },
        created_by=owner.id,
        is_active=True,
    )
    db_session.add_all([news, story, event, archive, foreign, mismatch, shifted])
    await db_session.flush()

    await seed_demo_data.seed_news(db_session, owner)
    await seed_demo_data.seed_stories(db_session, owner)
    await seed_demo_data.seed_events(db_session, owner)
    await seed_demo_data.seed_archived_events(db_session, owner)

    assert news.image_url == custom_url
    assert story.cover_url == legacy[story_item["cover_url"]] and not story.is_active
    assert event.image_url == legacy[event_item["image_url"]]
    assert (
        archive.image_url == legacy[archive_item["image_url"]] and not archive.is_active
    )
    assert foreign.image_url == legacy[foreign_item["image_url"]]
    assert mismatch.image_url == different_legacy_url
    assert shifted.image_url == legacy[shifted_item["image_url"]]
