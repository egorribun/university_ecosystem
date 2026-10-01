from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.models.events import Event
from app.models.news import News
from app.models.schedule import Group, Schedule
from app.models.stories import Story
from app.models.users import User
from scripts import seed_demo_data

_STATE_FIELDS = {
    User: ("id", "email", "role", "hashed_password", "group_id", "demo_seed_key"),
    News: ("id", "title", "title_en", "content", "content_en", "author_id"),
    Story: (
        "id",
        "title",
        "title_en",
        "short_text",
        "short_text_en",
        "cover_url",
        "is_active",
        "created_by",
    ),
    Event: (
        "id",
        "title",
        "title_en",
        "description",
        "description_en",
        "location",
        "location_en",
        "event_type",
        "event_type_en",
        "starts_at",
        "ends_at",
        "is_active",
        "created_by",
    ),
    Schedule: (
        "id",
        "group_id",
        "creator_id",
        "subject",
        "teacher",
        "room",
        "weekday",
        "start_time",
        "end_time",
        "parity",
        "lesson_type",
    ),
}


def _state(row: object) -> tuple[object, ...]:
    return tuple(getattr(row, field) for field in _STATE_FIELDS[type(row)])


async def _ids_by_table(db: AsyncSession) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for model in (User, Group, News, Story, Event, Schedule):
        rows = (await db.scalars(select(model))).all()
        result[model.__tablename__] = tuple(sorted(str(row.id) for row in rows))
    return result


async def _ownership_markers(
    db: AsyncSession,
) -> dict[str, tuple[tuple[str, str | None], ...]]:
    result: dict[str, tuple[tuple[str, str | None], ...]] = {}
    for model in (User, Group):
        rows = (await db.scalars(select(model))).all()
        result[model.__tablename__] = tuple(
            sorted((str(row.id), row.demo_seed_key) for row in rows)
        )
    return result


@pytest.mark.asyncio(loop_scope="session")
async def test_full_demo_seed_rerun_preserves_owned_markers_and_foreign_rows(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    foreign_owner = User.create(
        email="unrelated-owner@example.test",
        hashed_password="synthetic-test-hash",  # pragma: allowlist secret -- synthetic seeded-user test password
        role=UserRole.TEACHER,
    )
    db_session.add(foreign_owner)
    await db_session.flush()

    group = await seed_demo_data.seed_group(db_session)
    now = datetime.now(UTC)
    news_data = seed_demo_data.NEWS_DATA[0]
    story_data = seed_demo_data.STORIES_DATA[0]
    event_data = seed_demo_data.EVENTS_DATA[0]
    weekday, pair_number, subject, _teacher, _room, lesson_type, parity = (
        seed_demo_data.SCHEDULE_DATA[0]
    )
    start, end = seed_demo_data._pair(seed_demo_data._DAY_BASE[weekday], pair_number)

    foreign_rows = [
        foreign_owner,
        News(
            title=news_data["title"],
            title_en="Foreign synthetic news title",
            content="Foreign synthetic news content",
            content_en="Foreign synthetic news translation",
            author_id=foreign_owner.id,
        ),
        Story(
            title=story_data["title"],
            title_en="Foreign synthetic story title",
            short_text="Foreign synthetic story text",
            short_text_en="Foreign synthetic story translation",
            cover_url="https://example.test/foreign-story.png",
            is_active=False,
            published_at=now,
            expires_at=now + timedelta(days=14),
            created_by=foreign_owner.id,
        ),
        Event(
            title=event_data["title"],
            title_en="Foreign synthetic event title",
            description="Foreign synthetic event description",
            description_en="Foreign synthetic event translation",
            location="Foreign synthetic location",
            location_en="Foreign synthetic location translation",
            event_type="Foreign synthetic type",
            event_type_en="Foreign synthetic type translation",
            starts_at=event_data["starts_at"],
            ends_at=event_data["ends_at"],
            created_by=foreign_owner.id,
            is_active=False,
        ),
        Schedule(
            group_id=group.id,
            creator_id=foreign_owner.id,
            subject=subject,
            teacher="Foreign synthetic teacher",
            room="Foreign synthetic room",
            weekday=weekday,
            start_time=start,
            end_time=end,
            parity=parity,
            lesson_type=lesson_type,
        ),
    ]
    db_session.add_all(foreign_rows[1:])
    await db_session.flush()
    foreign_state = tuple(_state(row) for row in foreign_rows)

    @asynccontextmanager
    async def use_test_session():
        yield db_session

    monkeypatch.setattr(
        seed_demo_data, "require_owned_live_stand_target", lambda: "synthetic-test"
    )
    monkeypatch.setattr(seed_demo_data, "init_database", lambda: None)
    monkeypatch.setattr(seed_demo_data, "async_session", use_test_session)
    monkeypatch.setattr(seed_demo_data, "_is_live_stand_demo_target", lambda _: False)

    await seed_demo_data.main()
    first_ids = await _ids_by_table(db_session)
    first_markers = await _ownership_markers(db_session)
    first_foreign_state = tuple(_state(row) for row in foreign_rows)
    assert first_foreign_state == foreign_state

    await seed_demo_data.main()

    assert await _ids_by_table(db_session) == first_ids
    assert await _ownership_markers(db_session) == first_markers
    assert tuple(_state(row) for row in foreign_rows) == first_foreign_state

    seeded_user = await db_session.scalar(
        select(User).where(
            User.demo_seed_key == seed_demo_data.DEMO_PRIMARY_USER_SEED_KEY
        )
    )
    assert seeded_user is not None
    assert first_markers["groups"] == (
        (str(group.id), seed_demo_data.DEMO_CLASS_GROUP_SEED_KEY),
    )
    assert first_markers["users"] == (
        (str(foreign_owner.id), None),
        (str(seeded_user.id), seed_demo_data.DEMO_PRIMARY_USER_SEED_KEY),
    )

    seeded_news = (
        await db_session.scalars(select(News).where(News.author_id == seeded_user.id))
    ).all()
    seeded_stories = (
        await db_session.scalars(
            select(Story).where(Story.created_by == seeded_user.id)
        )
    ).all()
    seeded_events = (
        await db_session.scalars(
            select(Event).where(Event.created_by == seeded_user.id)
        )
    ).all()
    assert seeded_news and all(row.title_en and row.content_en for row in seeded_news)
    assert seeded_stories and all(
        row.title_en and row.short_text_en for row in seeded_stories
    )
    assert seeded_events and all(
        row.title_en and row.description_en and row.location_en and row.event_type_en
        for row in seeded_events
    )
