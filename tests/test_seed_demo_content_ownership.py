from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.events import Event
from app.models.news import News
from app.models.schedule import Schedule
from app.models.stories import Story
from scripts import seed_demo_data


class Rows:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return list(self._rows)


class DemoContentSession:
    def __init__(self, content_rows: list[object]) -> None:
        self.content_rows = list(content_rows)
        self.schedule_rows: list[Schedule] = []
        self.added: list[object] = []

    async def scalar(self, statement: object) -> object:
        entity = statement.column_descriptions[0].get("entity")
        compiled = statement.compile()
        where_sql = str(statement).partition("WHERE")[2]
        parameters = compiled.params
        for row in self.content_rows:
            matched = True
            for field in ("title", "starts_at", "author_id", "created_by"):
                if f"{entity.__tablename__}.{field}" not in where_sql:
                    continue
                parameter = next(
                    (
                        value
                        for name, value in parameters.items()
                        if name == f"{field}_1" or name.startswith(f"{field}_")
                    ),
                    None,
                )
                if getattr(row, field, None) != parameter:
                    matched = False
                    break
            if matched:
                return row
        return None

    async def scalars(self, statement: object) -> Rows:
        entity = statement.column_descriptions[0].get("entity")
        if entity is not Schedule:
            raise AssertionError(f"Unexpected query entity: {entity!r}")
        compiled = statement.compile()
        parameters = compiled.params
        group_id = parameters["group_id_1"]
        return Rows([row for row in self.schedule_rows if row.group_id == group_id])

    def add(self, entity: object) -> None:
        self.added.append(entity)
        if isinstance(entity, Schedule):
            self.schedule_rows.append(entity)
        elif isinstance(entity, (News, Story, Event)):
            self.content_rows.append(entity)

    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "data", "owner_field", "seed_function"),
    [
        (News, seed_demo_data.NEWS_DATA[0], "author_id", seed_demo_data.seed_news),
        (
            Story,
            seed_demo_data.STORIES_DATA[0],
            "created_by",
            seed_demo_data.seed_stories,
        ),
        (
            Event,
            seed_demo_data.EVENTS_DATA[0],
            "created_by",
            seed_demo_data.seed_events,
        ),
    ],
)
async def test_same_title_user_content_is_not_adopted_or_mutated(
    model: type[News] | type[Story] | type[Event],
    data: dict[str, object],
    owner_field: str,
    seed_function,
) -> None:
    demo_user = SimpleNamespace(id=uuid4())
    unrelated_owner_id = uuid4()
    user_row = SimpleNamespace(
        title=data["title"],
        starts_at=data.get("starts_at"),
        author_id=unrelated_owner_id,
        created_by=unrelated_owner_id,
        title_en=None,
        content_en=None,
        short_text_en=None,
        description_en=None,
        location_en=None,
        event_type_en=None,
        content="user-authored synthetic content",
        short_text="user-authored synthetic story",
        description="user-authored synthetic event",
    )
    database = DemoContentSession([user_row])

    await seed_function(database, demo_user)

    assert user_row.title_en is None
    assert user_row.content_en is None
    assert user_row.short_text_en is None
    assert user_row.description_en is None
    assert user_row.location_en is None
    assert user_row.event_type_en is None
    seeded = [
        row
        for row in database.added
        if isinstance(row, model) and row.title == data["title"]
    ]
    assert seeded == []

    await seed_function(database, demo_user)
    second_run_seeded = [
        row
        for row in database.added
        if isinstance(row, model)
        and row.title == data["title"]
        and getattr(row, owner_field) == demo_user.id
    ]
    assert second_run_seeded == []
    assert user_row.title_en is None
    assert user_row.content_en is None
    assert user_row.short_text_en is None
    assert user_row.description_en is None
    assert user_row.location_en is None
    assert user_row.event_type_en is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "data", "owner_field", "source_field", "seed_function"),
    [
        (
            News,
            seed_demo_data.NEWS_DATA[0],
            "author_id",
            "content",
            seed_demo_data.seed_news,
        ),
        (
            Story,
            seed_demo_data.STORIES_DATA[0],
            "created_by",
            "short_text",
            seed_demo_data.seed_stories,
        ),
        (
            Event,
            seed_demo_data.EVENTS_DATA[0],
            "created_by",
            "description",
            seed_demo_data.seed_events,
        ),
    ],
)
async def test_same_owner_custom_source_content_is_not_backfilled_or_duplicated(
    model: type[News] | type[Story] | type[Event],
    data: dict[str, object],
    owner_field: str,
    source_field: str,
    seed_function,
) -> None:
    demo_user = SimpleNamespace(id=uuid4())
    user_row = SimpleNamespace(
        title=data["title"],
        starts_at=data.get("starts_at"),
        author_id=demo_user.id,
        created_by=demo_user.id,
        title_en=None,
        content_en=None,
        short_text_en=None,
        description_en=None,
        location_en=None,
        event_type_en=None,
        content="user-edited synthetic news text",
        short_text="user-edited synthetic story text",
        description="user-edited synthetic event description",
        location="user-edited synthetic event location",
        event_type="user-edited synthetic event type",
    )
    database = DemoContentSession([user_row])

    await seed_function(database, demo_user)

    assert getattr(user_row, source_field) != data[source_field]
    assert user_row.title_en is None
    assert user_row.content_en is None
    assert user_row.short_text_en is None
    assert user_row.description_en is None
    assert user_row.location_en is None
    assert user_row.event_type_en is None
    assert not [
        row
        for row in database.added
        if isinstance(row, model)
        and row.title == data["title"]
        and getattr(row, owner_field) == demo_user.id
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "data", "owner_field", "source_field", "english_field", "seed_function"),
    [
        (
            News,
            seed_demo_data.NEWS_DATA[0],
            "author_id",
            "content",
            "content_en",
            seed_demo_data.seed_news,
        ),
        (
            Story,
            seed_demo_data.STORIES_DATA[0],
            "created_by",
            "short_text",
            "short_text_en",
            seed_demo_data.seed_stories,
        ),
        (
            Event,
            seed_demo_data.EVENTS_DATA[0],
            "created_by",
            "description",
            "description_en",
            seed_demo_data.seed_events,
        ),
    ],
)
async def test_seed_owned_matching_source_content_backfills_translation_only_once(
    model: type[News] | type[Story] | type[Event],
    data: dict[str, object],
    owner_field: str,
    source_field: str,
    english_field: str,
    seed_function,
) -> None:
    demo_user = SimpleNamespace(id=uuid4())
    user_row = SimpleNamespace(
        title=data["title"],
        starts_at=data.get("starts_at"),
        author_id=demo_user.id,
        created_by=demo_user.id,
        title_en=data["title_en"],
        content_en=None,
        short_text_en=None,
        description_en=None,
        location_en=None,
        event_type_en=None,
        cover_url=data.get("cover_url"),
        cta_url=None,
        is_active=True,
        expires_at=None,
        content=data.get("content"),
        short_text=data.get("short_text"),
        description=data.get("description"),
        location=data.get("location"),
        event_type=data.get("event_type"),
    )
    database = DemoContentSession([user_row])

    await seed_function(database, demo_user)

    assert getattr(user_row, source_field) == data[source_field]
    assert getattr(user_row, english_field) == data[english_field]
    assert user_row.title_en == data["title_en"]

    await seed_function(database, demo_user)

    assert getattr(user_row, english_field) == data[english_field]
    assert user_row.title_en == data["title_en"]
    assert not [
        row
        for row in database.added
        if isinstance(row, model)
        and row.title == data["title"]
        and getattr(row, owner_field) == demo_user.id
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("user_row_creator", ["other", None])
async def test_schedule_seed_skips_natural_key_collision_without_mutation_or_duplicate(
    user_row_creator: str | None,
) -> None:
    group_id = uuid4()
    demo_user_id = uuid4()
    user_row_id = uuid4()
    weekday, pair_number, subject, *_rest, parity = seed_demo_data.SCHEDULE_DATA[0]
    start, end = seed_demo_data._pair(seed_demo_data._DAY_BASE[weekday], pair_number)
    user_row = Schedule(
        group_id=group_id,
        creator_id=user_row_id if user_row_creator == "other" else None,
        subject=subject,
        teacher="Synthetic user-edited teacher",
        room="Synthetic user-edited room",
        weekday=weekday,
        start_time=start,
        end_time=end,
        parity=parity,
    )
    database = DemoContentSession([])
    database.schedule_rows.append(user_row)

    await seed_demo_data.seed_schedule(
        database,
        SimpleNamespace(id=group_id),
        SimpleNamespace(id=demo_user_id),
    )

    matching = [
        row
        for row in database.schedule_rows
        if row.weekday == weekday
        and row.start_time == start
        and row.parity == parity
        and row.subject == subject
    ]
    assert matching == [user_row]
    assert not [
        row
        for row in database.added
        if isinstance(row, Schedule)
        and row.weekday == weekday
        and row.start_time == start
        and row.parity == parity
        and row.subject == subject
    ]
    assert user_row.teacher == "Synthetic user-edited teacher"
    assert user_row.room == "Synthetic user-edited room"

    await seed_demo_data.seed_schedule(
        database,
        SimpleNamespace(id=group_id),
        SimpleNamespace(id=demo_user_id),
    )

    assert matching == [user_row]
    assert not [
        row
        for row in database.added
        if isinstance(row, Schedule)
        and row.weekday == weekday
        and row.start_time == start
        and row.parity == parity
        and row.subject == subject
    ]
    assert user_row.teacher == "Synthetic user-edited teacher"
    assert user_row.room == "Synthetic user-edited room"
