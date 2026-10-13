from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from scripts import seed_admin_data, seed_demo_data, seed_target

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_seed_group_reuses_matching_partial_state(db_session, capsys) -> None:
    try:
        first = await seed_demo_data.seed_group(db_session)
        await db_session.commit()

        second = await seed_demo_data.seed_group(db_session)
        assert second.id == first.id
        assert (
            await db_session.scalar(
                select(func.count()).select_from(seed_demo_data.Group)
            )
            == 1
        )
    finally:
        capsys.readouterr()


async def test_seed_user_reuses_matching_partial_state(capsys) -> None:
    from types import SimpleNamespace
    from uuid import uuid4

    class RecordingSession:
        def __init__(self) -> None:
            self.users = []
            self.objects = []

        async def scalar(self, _statement):
            return self.users[0] if self.users else None

        def add(self, entity) -> None:
            self.objects.append(entity)
            if isinstance(entity, seed_demo_data.User):
                if entity.id is None:
                    entity.id = uuid4()
                self.users.append(entity)

        async def flush(self) -> None:
            return None

    db = RecordingSession()
    group = SimpleNamespace(id=uuid4())
    try:
        first = await seed_demo_data.seed_user(db, group)
        original_hash = first.hashed_password
        different_group_id = uuid4()
        first.group_id = different_group_id
        second = await seed_demo_data.seed_user(db, group)

        assert second.id == first.id
        assert first.hashed_password == original_hash
        assert first.group_id == different_group_id
        assert len(db.users) == 1
        assert len(db.objects) == 3
    finally:
        capsys.readouterr()


async def test_seed_user_repairs_missing_demo_relations(
    db_session, user_factory, capsys
):
    try:
        group = await seed_demo_data.seed_group(db_session)
        existing = await user_factory(
            email=seed_demo_data.DEMO_PRIMARY_USER_EMAIL,
            demo_seed_key=seed_demo_data.DEMO_PRIMARY_USER_SEED_KEY,
            role="student",
            group_id=group.id,
        )
        profile = await db_session.scalar(
            select(seed_demo_data.UserProfile).where(
                seed_demo_data.UserProfile.user_id == existing.id
            )
        )
        assert profile is not None
        await db_session.delete(profile)
        await db_session.flush()

        seeded = await seed_demo_data.seed_user(db_session, group)
        await db_session.flush()

        restored_profile = await db_session.scalar(
            select(seed_demo_data.UserProfile).where(
                seed_demo_data.UserProfile.user_id == existing.id
            )
        )
        education_path = await db_session.scalar(
            select(seed_demo_data.EducationPath).where(
                seed_demo_data.EducationPath.user_id == existing.id
            )
        )
        assert seeded.id == existing.id
        assert seeded.group_id == group.id
        assert restored_profile is not None
        assert restored_profile.full_name == "Тест Студентов"
        assert education_path is not None
        assert education_path.program == "Информационные системы и технологии"
    finally:
        capsys.readouterr()


async def test_seed_content_sections_are_idempotent_from_partial_state(
    db_session, capsys
) -> None:
    try:
        group = await seed_demo_data.seed_group(db_session)
        user = await seed_demo_data.seed_user(db_session, group)
        await seed_demo_data.seed_news(db_session, user)
        await db_session.commit()

        await seed_demo_data.seed_news(db_session, user)
        await seed_demo_data.seed_stories(db_session, user)
        await seed_demo_data.seed_events(db_session, user)
        await seed_demo_data.seed_schedule(db_session, group, user)
        await db_session.commit()

        await seed_demo_data.seed_news(db_session, user)
        await seed_demo_data.seed_stories(db_session, user)
        await seed_demo_data.seed_events(db_session, user)
        await seed_demo_data.seed_schedule(db_session, group, user)
        await db_session.commit()

        assert await db_session.scalar(
            select(func.count()).select_from(seed_demo_data.News)
        ) == len(seed_demo_data.NEWS_DATA)
        assert await db_session.scalar(
            select(func.count()).select_from(seed_demo_data.Story)
        ) == len(seed_demo_data.STORIES_DATA)
        assert await db_session.scalar(
            select(func.count()).select_from(seed_demo_data.Event)
        ) == len(seed_demo_data.EVENTS_DATA)
        assert await db_session.scalar(
            select(func.count()).select_from(seed_demo_data.Schedule)
        ) == len(seed_demo_data.SCHEDULE_DATA)

        news_rows = await db_session.scalars(select(seed_demo_data.News))
        assert all(row.title_en and row.content_en for row in news_rows.all())
        story_rows = await db_session.scalars(select(seed_demo_data.Story))
        assert all(row.title_en and row.short_text_en for row in story_rows.all())
        event_rows = await db_session.scalars(select(seed_demo_data.Event))
        assert all(
            row.title_en
            and row.description_en
            and row.location_en
            and row.event_type_en
            for row in event_rows.all()
        )
    finally:
        capsys.readouterr()


async def test_seed_content_backfills_missing_english_fields(
    db_session, capsys
) -> None:
    try:
        group = await seed_demo_data.seed_group(db_session)
        user = await seed_demo_data.seed_user(db_session, group)
        now = datetime.now(UTC)

        news_data = seed_demo_data.NEWS_DATA[0]
        story_data = seed_demo_data.STORIES_DATA[0]
        event_data = seed_demo_data.EVENTS_DATA[0]
        legacy_news = seed_demo_data.News(
            title=news_data["title"],
            title_en="Preserved existing English headline",
            content=news_data["content"],
            author_id=user.id,
        )
        legacy_story = seed_demo_data.Story(
            title=story_data["title"],
            title_en="Preserved existing English story headline",
            short_text=story_data["short_text"],
            cover_url=story_data["cover_url"],
            is_active=True,
            published_at=now,
            expires_at=now + timedelta(days=30),
            created_by=user.id,
        )
        legacy_event = seed_demo_data.Event(
            title=event_data["title"],
            title_en="Preserved existing English event headline",
            description=event_data["description"],
            location=event_data["location"],
            event_type=event_data["event_type"],
            starts_at=event_data["starts_at"],
            ends_at=event_data["ends_at"],
            created_by=user.id,
        )
        db_session.add_all([legacy_news, legacy_story, legacy_event])
        await db_session.flush()

        await seed_demo_data.seed_news(db_session, user)
        await seed_demo_data.seed_stories(db_session, user)
        await seed_demo_data.seed_events(db_session, user)
        await db_session.flush()

        assert legacy_news.title_en == "Preserved existing English headline"
        assert legacy_news.content_en == news_data["content_en"]
        assert legacy_news.content == news_data["content"]
        assert legacy_story.title_en == "Preserved existing English story headline"
        assert legacy_story.short_text_en == story_data["short_text_en"]
        assert legacy_story.short_text == story_data["short_text"]
        assert legacy_event.title_en == "Preserved existing English event headline"
        assert legacy_event.description_en == event_data["description_en"]
        assert legacy_event.location_en == event_data["location_en"]
        assert legacy_event.event_type_en == event_data["event_type_en"]
        assert legacy_event.description == event_data["description"]
    finally:
        capsys.readouterr()


async def test_seed_events_are_upcoming_for_the_current_date(
    db_session, capsys
) -> None:
    now = datetime.now(UTC)
    try:
        group = await seed_demo_data.seed_group(db_session)
        user = await seed_demo_data.seed_user(db_session, group)
        await seed_demo_data.seed_events(db_session, user)
        await db_session.commit()

        events = await db_session.scalars(
            select(seed_demo_data.Event).where(
                seed_demo_data.Event.created_by == user.id,
                seed_demo_data.Event.title.in_(
                    tuple(item["title"] for item in seed_demo_data.EVENTS_DATA)
                ),
            )
        )
        rows = events.all()
        assert len(rows) == len(seed_demo_data.EVENTS_DATA)
        assert all(_event_utc(event.starts_at) > now for event in rows)
    finally:
        capsys.readouterr()


def _event_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def _owned_demo_events(db_session, user):
    result = await db_session.scalars(
        select(seed_demo_data.Event)
        .where(
            seed_demo_data.Event.created_by == user.id,
            seed_demo_data.Event.title.in_(
                tuple(item["title"] for item in seed_demo_data.EVENTS_DATA)
            ),
        )
        .order_by(seed_demo_data.Event.starts_at)
    )
    return result.all()


async def test_seed_events_reuses_a_future_batch_across_days(
    db_session, monkeypatch, capsys
) -> None:
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    monkeypatch.setattr(seed_demo_data, "_event_now_utc", lambda: now)
    try:
        group = await seed_demo_data.seed_group(db_session)
        user = await seed_demo_data.seed_user(db_session, group)
        await seed_demo_data.seed_events(db_session, user)
        await db_session.commit()

        initial = await _owned_demo_events(db_session, user)
        assert len(initial) == len(seed_demo_data.EVENTS_DATA)
        anchor = datetime(2026, 10, 9, 15, tzinfo=UTC)
        source_anchor = _event_utc(seed_demo_data.EVENTS_DATA[0]["starts_at"])
        initial_snapshot = [
            (event.title, _event_utc(event.starts_at), _event_utc(event.ends_at))
            for event in initial
        ]
        assert initial_snapshot[0][1] == anchor
        assert initial_snapshot == [
            (
                source["title"],
                anchor + (_event_utc(source["starts_at"]) - source_anchor),
                anchor + (_event_utc(source["ends_at"]) - source_anchor),
            )
            for source in seed_demo_data.EVENTS_DATA
        ]

        monkeypatch.setattr(
            seed_demo_data,
            "_event_now_utc",
            lambda: datetime(2026, 10, 10, 18, tzinfo=UTC),
        )
        await seed_demo_data.seed_events(db_session, user)
        await db_session.commit()

        rerun = await _owned_demo_events(db_session, user)
        assert len(rerun) == len(seed_demo_data.EVENTS_DATA)
        assert [
            (event.title, _event_utc(event.starts_at), _event_utc(event.ends_at))
            for event in rerun
        ] == initial_snapshot
    finally:
        capsys.readouterr()


async def test_seed_events_starts_a_new_batch_only_after_expiration(
    db_session, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        seed_demo_data,
        "_event_now_utc",
        lambda: datetime(2026, 10, 7, 12, tzinfo=UTC),
    )
    try:
        group = await seed_demo_data.seed_group(db_session)
        user = await seed_demo_data.seed_user(db_session, group)
        await seed_demo_data.seed_events(db_session, user)
        await db_session.commit()
        original = await _owned_demo_events(db_session, user)
        original_snapshot = [
            (
                event.id,
                event.title,
                _event_utc(event.starts_at),
                _event_utc(event.ends_at),
            )
            for event in original
        ]
        expired_at = _event_utc(original[-1].ends_at) + timedelta(minutes=1)
        monkeypatch.setattr(seed_demo_data, "_event_now_utc", lambda: expired_at)

        await seed_demo_data.seed_events(db_session, user)
        await db_session.commit()

        all_events = await _owned_demo_events(db_session, user)
        batch_size = len(seed_demo_data.EVENTS_DATA)
        assert len(all_events) == 2 * batch_size
        assert [
            (
                event.id,
                event.title,
                _event_utc(event.starts_at),
                _event_utc(event.ends_at),
            )
            for event in all_events[:batch_size]
        ] == original_snapshot
        next_batch = all_events[batch_size:]
        assert all(_event_utc(event.starts_at) > expired_at for event in next_batch)
        assert next_batch[0].starts_at.weekday() == original[0].starts_at.weekday()
    finally:
        capsys.readouterr()


async def test_seed_events_does_not_reuse_a_batch_with_no_active_future_rows(
    db_session, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        seed_demo_data,
        "_event_now_utc",
        lambda: datetime(2026, 10, 7, 12, tzinfo=UTC),
    )
    try:
        group = await seed_demo_data.seed_group(db_session)
        user = await seed_demo_data.seed_user(db_session, group)
        await seed_demo_data.seed_events(db_session, user)
        await db_session.commit()

        original = await _owned_demo_events(db_session, user)
        later_now = datetime(2026, 10, 10, 18, tzinfo=UTC)
        monkeypatch.setattr(seed_demo_data, "_event_now_utc", lambda: later_now)
        for event in original:
            if _event_utc(event.starts_at) > later_now:
                event.is_active = False
        await db_session.commit()
        original_snapshot = [
            (event.id, _event_utc(event.starts_at), event.is_active)
            for event in original
        ]

        await seed_demo_data.seed_events(db_session, user)
        await db_session.commit()

        all_events = await _owned_demo_events(db_session, user)
        batch_size = len(seed_demo_data.EVENTS_DATA)
        assert len(all_events) == 2 * batch_size
        all_by_id = {event.id: event for event in all_events}
        assert [
            (event.id, _event_utc(event.starts_at), event.is_active)
            for event in (all_by_id[row_id] for row_id, *_ in original_snapshot)
        ] == original_snapshot
        original_ids = {row_id for row_id, *_ in original_snapshot}
        new_batch = [event for event in all_events if event.id not in original_ids]
        assert _event_utc(new_batch[0].starts_at) == datetime(
            2026, 10, 16, 15, tzinfo=UTC
        )
        assert all(event.is_active for event in new_batch)
    finally:
        capsys.readouterr()


async def test_seed_events_does_not_claim_a_foreign_natural_key(
    db_session, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        seed_demo_data,
        "_event_now_utc",
        lambda: datetime(2026, 10, 7, 12, tzinfo=UTC),
    )
    try:
        group = await seed_demo_data.seed_group(db_session)
        user = await seed_demo_data.seed_user(db_session, group)
        source = seed_demo_data.EVENTS_DATA[0]
        collision_start = datetime(2026, 10, 9, 15, tzinfo=UTC)
        collision = seed_demo_data.Event(
            title=source["title"],
            description=source["description"],
            location=source["location"],
            event_type=source["event_type"],
            starts_at=collision_start,
            ends_at=collision_start + timedelta(hours=2),
            created_by=None,
        )
        db_session.add(collision)
        await db_session.flush()

        await seed_demo_data.seed_events(db_session, user)
        await db_session.commit()

        owned = await _owned_demo_events(db_session, user)
        assert len(owned) == len(seed_demo_data.EVENTS_DATA) - 1
        assert not any(event.title == source["title"] for event in owned)
        assert collision.created_by is None
        assert _event_utc(collision.starts_at) == collision_start
    finally:
        capsys.readouterr()


async def test_demo_content_includes_english_fields() -> None:
    for records, required_fields in (
        (seed_demo_data.NEWS_DATA, ("title_en", "content_en")),
        (seed_demo_data.STORIES_DATA, ("title_en", "short_text_en")),
        (
            seed_demo_data.EVENTS_DATA,
            ("title_en", "description_en", "location_en", "event_type_en"),
        ),
    ):
        assert all(
            all(record.get(field) for field in required_fields) for record in records
        ), "every seeded content record must have its English fields"


async def test_seed_target_rejects_a_database_outside_compose_postgres(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LIVE_STAND_SEED_PROJECT", "ue-live-testproject")
    monkeypatch.setenv("LIVE_STAND_OWNER_VERIFIED", "1")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "ue-live-testproject")
    monkeypatch.setattr(
        seed_target,
        "_configured_database_url",
        lambda: "postgresql+asyncpg://tester@remote-db/testdb",
    )

    with pytest.raises(RuntimeError, match="postgres service"):
        seed_target.require_owned_live_stand_target()


async def test_seed_target_accepts_the_verified_compose_postgres_service(
    monkeypatch,
) -> None:
    project = "ue-live-testproject"
    monkeypatch.setenv("LIVE_STAND_SEED_PROJECT", project)
    monkeypatch.setenv("LIVE_STAND_OWNER_VERIFIED", "1")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", project)
    monkeypatch.setattr(
        seed_target,
        "_configured_database_url",
        lambda: "postgresql+asyncpg://tester@postgres:5432/demo",
    )

    assert seed_target.require_owned_live_stand_target() == project


async def test_seed_target_accepts_only_the_explicit_admin_smoke_test_database(
    monkeypatch,
) -> None:
    workspace = str(Path(seed_target.__file__).resolve().parents[1])
    for name, value in {
        "ENVIRONMENT": "testing",
        "UE_SEED_TARGET": "admin-smoke",
        "GITHUB_ACTIONS": "true",
        "GITHUB_WORKFLOW": "Admin Smoke Monitoring (Linux Periodic)",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REPOSITORY": "egorribun/university_ecosystem",
        "GITHUB_RUN_ID": "123456789",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_WORKSPACE": workspace,
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        seed_target,
        "_configured_database_url",
        lambda: "postgresql+asyncpg://test@127.0.0.1:5432/test_admin_smoke",
    )

    assert seed_target.require_owned_live_stand_target() == "ci-admin-smoke"


@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("ENVIRONMENT", "production"),
        ("UE_SEED_TARGET", "other"),
        ("GITHUB_WORKFLOW", "another workflow"),
        ("GITHUB_EVENT_NAME", "pull_request"),
        ("GITHUB_REF", "refs/tags/v1.0.0"),
        ("GITHUB_RUN_ID", "not-a-run-id"),
    ),
)
async def test_seed_target_rejects_non_admin_smoke_workflow_context(
    monkeypatch, name: str, value: str
) -> None:
    workspace = str(Path(seed_target.__file__).resolve().parents[1])
    for key, item in {
        "ENVIRONMENT": "testing",
        "UE_SEED_TARGET": "admin-smoke",
        "GITHUB_ACTIONS": "true",
        "GITHUB_WORKFLOW": "Admin Smoke Monitoring (Linux Periodic)",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REPOSITORY": "egorribun/university_ecosystem",
        "GITHUB_RUN_ID": "123456789",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_WORKSPACE": workspace,
    }.items():
        monkeypatch.setenv(key, item)
    monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        seed_target,
        "_configured_database_url",
        lambda: "postgresql+asyncpg://test@127.0.0.1:5432/test_admin_smoke",
    )

    with pytest.raises(RuntimeError, match="seed"):
        seed_target.require_owned_live_stand_target()


def _admin_smoke_database_url_for_target_case(
    host: str, port: int, database: str
) -> str:
    from sqlalchemy.engine import URL

    return URL.create(
        drivername="postgresql+asyncpg",
        username="test",
        host=host,
        port=port,
        database=database,
    ).render_as_string()


@pytest.mark.parametrize(
    ("host", "port", "database"),
    (
        ("localhost", 5432, "other_db"),
        ("127.0.0.1", 5433, "test_admin_smoke"),
        ("remote-db", 5432, "test_admin_smoke"),
    ),
)
async def test_seed_target_rejects_database_outside_admin_smoke_service(
    monkeypatch, host: str, port: int, database: str
) -> None:
    from sqlalchemy.engine import make_url

    database_url = _admin_smoke_database_url_for_target_case(host, port, database)
    parsed_url = make_url(database_url)
    assert parsed_url.username == "test"
    assert parsed_url.password is None

    workspace = str(Path(seed_target.__file__).resolve().parents[1])
    for key, value in {
        "ENVIRONMENT": "testing",
        "UE_SEED_TARGET": "admin-smoke",
        "GITHUB_ACTIONS": "true",
        "GITHUB_WORKFLOW": "Admin Smoke Monitoring (Linux Periodic)",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REPOSITORY": "egorribun/university_ecosystem",
        "GITHUB_RUN_ID": "123456789",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_WORKSPACE": workspace,
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(seed_target, "_configured_database_url", lambda: database_url)

    with pytest.raises(RuntimeError, match="seed"):
        seed_target.require_owned_live_stand_target()


async def test_seed_target_rejects_mismatched_compose_project(monkeypatch) -> None:
    monkeypatch.setenv("LIVE_STAND_SEED_PROJECT", "ue-live-owned")
    monkeypatch.setenv("LIVE_STAND_OWNER_VERIFIED", "1")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "ue-live-other")
    monkeypatch.setattr(
        seed_target,
        "_configured_database_url",
        lambda: pytest.fail("database target checked before project ownership"),
    )

    with pytest.raises(RuntimeError, match="owned live stand"):
        seed_target.require_owned_live_stand_target()


async def test_seed_target_fails_closed_when_database_url_cannot_be_read(
    monkeypatch,
) -> None:
    project = "ue-live-testproject"
    monkeypatch.setenv("LIVE_STAND_SEED_PROJECT", project)
    monkeypatch.setenv("LIVE_STAND_OWNER_VERIFIED", "1")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", project)

    def unreadable_url() -> str:
        raise ValueError("unavailable")

    monkeypatch.setattr(seed_target, "_configured_database_url", unreadable_url)

    with pytest.raises(RuntimeError, match="cannot verify"):
        seed_target.require_owned_live_stand_target()


@pytest.mark.parametrize(
    "module",
    (seed_demo_data, seed_admin_data),
    ids=("demo", "admin"),
)
async def test_standalone_seeders_require_live_stand_ownership_before_database_init(
    module, monkeypatch, capsys
) -> None:
    for name in (
        "LIVE_STAND_SEED_PROJECT",
        "LIVE_STAND_OWNER_VERIFIED",
        "COMPOSE_PROJECT_NAME",
    ):
        monkeypatch.delenv(name, raising=False)
    initialized = False

    def record_init() -> None:
        nonlocal initialized
        initialized = True

    monkeypatch.setattr(module, "init_database", record_init)
    monkeypatch.setattr(
        module,
        "async_session",
        lambda: pytest.fail("seed session opened before ownership validation"),
    )
    if module is seed_admin_data:
        monkeypatch.setattr(module, "_required_test_password", lambda: "test")

    try:
        with pytest.raises(RuntimeError, match="owned live stand"):
            await module.main()
    finally:
        capsys.readouterr()

    assert not initialized


async def test_seed_schedule_uses_shared_mutation_lock_before_schedule_reads(
    db_session, monkeypatch, capsys
) -> None:
    from app.repositories.schedule_repository import ScheduleRepository

    group = await seed_demo_data.seed_group(db_session)
    user = await seed_demo_data.seed_user(db_session, group)
    events: list[str] = []
    session_type = type(db_session)
    original_scalars = session_type.scalars
    original_execute = session_type.execute
    original_flush = session_type.flush

    async def observed_lock(_repository) -> None:
        events.append("lock")

    async def observed_scalars(session, statement, *args, **kwargs):
        events.append("read")
        return await original_scalars(session, statement, *args, **kwargs)

    async def observed_execute(session, statement, *args, **kwargs):
        events.append("read")
        return await original_execute(session, statement, *args, **kwargs)

    async def observed_flush(session, *args, **kwargs):
        events.append("flush")
        return await original_flush(session, *args, **kwargs)

    monkeypatch.setattr(
        ScheduleRepository,
        "lock_schedule_mutations",
        observed_lock,
        raising=False,
    )
    monkeypatch.setattr(session_type, "scalars", observed_scalars)
    monkeypatch.setattr(session_type, "execute", observed_execute)
    monkeypatch.setattr(session_type, "flush", observed_flush)
    try:
        await seed_demo_data.seed_schedule(db_session, group, user)

        assert events[0] == "lock"
        assert events.index("lock") < events.index("read") < events.index("flush")
    finally:
        capsys.readouterr()


async def test_seed_schedule_rejects_cross_group_teacher_conflict_atomically(
    db_session, capsys
) -> None:
    from app.core.exceptions.domain import BusinessRuleViolation

    group = await seed_demo_data.seed_group(db_session)
    user = await seed_demo_data.seed_user(db_session, group)
    other_group = seed_demo_data.Group(name="Unrelated API schedule group")
    db_session.add(other_group)
    await db_session.flush()
    start, end = seed_demo_data._pair(seed_demo_data._DAY_BASE["monday"], 1)
    db_session.add(
        seed_demo_data.Schedule(
            group_id=other_group.id,
            subject="Existing API-created lesson",
            teacher="Иванов А.В.",
            room="X-101",
            weekday="monday",
            start_time=start,
            end_time=end,
            parity="both",
            lesson_type="lecture",
        )
    )
    await db_session.commit()

    try:
        with pytest.raises(BusinessRuleViolation):
            await seed_demo_data.seed_schedule(db_session, group, user)

        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(seed_demo_data.Schedule)
                .where(seed_demo_data.Schedule.group_id == group.id)
            )
            == 0
        )
    finally:
        await db_session.rollback()
        capsys.readouterr()


async def test_seed_schedule_ignores_unrelated_group_different_fixture_teacher(
    db_session, capsys
) -> None:
    group = await seed_demo_data.seed_group(db_session)
    user = await seed_demo_data.seed_user(db_session, group)
    other_group = seed_demo_data.Group(name="Unrelated different-teacher schedule")
    db_session.add(other_group)
    await db_session.flush()

    weekday, pair_num, _subject, target_teacher, _room, _kind, parity = (
        seed_demo_data.SCHEDULE_DATA[0]
    )
    other_teacher = next(
        item[3]
        for item in seed_demo_data.SCHEDULE_DATA
        if item[3] and item[3] != target_teacher
    )
    start, end = seed_demo_data._pair(seed_demo_data._DAY_BASE[weekday], pair_num)
    unrelated_row = seed_demo_data.Schedule(
        group_id=other_group.id,
        subject="Unrelated group overlap",
        teacher=other_teacher,
        room="Different room",
        weekday=weekday,
        start_time=start,
        end_time=end,
        parity=parity,
        lesson_type="lecture",
    )
    db_session.add(unrelated_row)
    await db_session.flush()

    try:
        await seed_demo_data.seed_schedule(db_session, group, user)

        seeded_rows = await db_session.scalars(
            select(seed_demo_data.Schedule).where(
                seed_demo_data.Schedule.group_id == group.id
            )
        )
        assert len(seeded_rows.all()) == len(seed_demo_data.SCHEDULE_DATA)
        persisted_unrelated = await db_session.get(
            seed_demo_data.Schedule, unrelated_row.id
        )
        assert persisted_unrelated is not None
        assert persisted_unrelated.group_id == other_group.id
        assert persisted_unrelated.teacher == other_teacher
    finally:
        await db_session.rollback()
        capsys.readouterr()


async def test_seed_schedule_completes_a_valid_partial_natural_key_population(
    db_session, capsys
) -> None:
    group = await seed_demo_data.seed_group(db_session)
    user = await seed_demo_data.seed_user(db_session, group)
    weekday, pair_num, subject, teacher, room, lesson_type, parity = (
        seed_demo_data.SCHEDULE_DATA[0]
    )
    start, end = seed_demo_data._pair(seed_demo_data._DAY_BASE[weekday], pair_num)
    partial_row = seed_demo_data.Schedule(
        group_id=group.id,
        creator_id=user.id,
        subject=subject,
        teacher=teacher,
        room=room,
        weekday=weekday,
        start_time=start,
        end_time=end,
        parity=parity,
        lesson_type=lesson_type,
    )
    db_session.add(partial_row)
    await db_session.flush()
    partial_id = partial_row.id

    try:
        await seed_demo_data.seed_schedule(db_session, group, user)
        await seed_demo_data.seed_schedule(db_session, group, user)

        seeded_rows = await db_session.scalars(
            select(seed_demo_data.Schedule).where(
                seed_demo_data.Schedule.group_id == group.id
            )
        )
        saved_rows = seeded_rows.all()
        assert len(saved_rows) == len(seed_demo_data.SCHEDULE_DATA)
        assert sum(row.id == partial_id for row in saved_rows) == 1
        natural_key_rows = [
            row
            for row in saved_rows
            if row.weekday == weekday
            and _event_utc(row.start_time) == _event_utc(start)
            and row.subject == subject
            and row.parity == parity
        ]
        assert len(natural_key_rows) == 1
        assert natural_key_rows[0].id == partial_id
    finally:
        await db_session.rollback()
        capsys.readouterr()


async def test_seed_schedule_checks_existing_partial_seed_teacher_against_other_groups(
    db_session, capsys
) -> None:
    from app.core.exceptions.domain import BusinessRuleViolation

    group = await seed_demo_data.seed_group(db_session)
    user = await seed_demo_data.seed_user(db_session, group)
    other_group = seed_demo_data.Group(name="Legacy teacher conflict group")
    db_session.add(other_group)
    await db_session.flush()

    weekday, pair_num, subject, teacher, room, lesson_type, parity = (
        seed_demo_data.SCHEDULE_DATA[0]
    )
    start, end = seed_demo_data._pair(seed_demo_data._DAY_BASE[weekday], pair_num)
    partial_row = seed_demo_data.Schedule(
        group_id=group.id,
        creator_id=user.id,
        subject=subject,
        teacher=teacher,
        room=room,
        weekday=weekday,
        start_time=start,
        end_time=end,
        parity=parity,
        lesson_type=lesson_type,
    )
    external_row = seed_demo_data.Schedule(
        group_id=other_group.id,
        subject="Existing external teacher lesson",
        teacher=teacher,
        room="Different room",
        weekday=weekday,
        start_time=start,
        end_time=end,
        parity=parity,
        lesson_type="lecture",
    )
    db_session.add_all([partial_row, external_row])
    await db_session.flush()
    partial_id = partial_row.id
    external_id = external_row.id

    try:
        with pytest.raises(BusinessRuleViolation):
            await seed_demo_data.seed_schedule(db_session, group, user)

        target_rows = await db_session.scalars(
            select(seed_demo_data.Schedule).where(
                seed_demo_data.Schedule.group_id == group.id
            )
        )
        saved_target_rows = target_rows.all()
        assert [row.id for row in saved_target_rows] == [partial_id]
        preserved_external = await db_session.get(seed_demo_data.Schedule, external_id)
        assert preserved_external is not None
        assert preserved_external.group_id == other_group.id
        assert preserved_external.teacher == teacher
    finally:
        await db_session.rollback()
        capsys.readouterr()


async def test_demo_schedule_data_has_no_internal_conflicts() -> None:
    from app.services.schedule_optimizer import (
        ScheduleItemInternal,
        ScheduleOptimizerService,
    )

    items: list[ScheduleItemInternal] = []
    for (
        weekday,
        pair_num,
        _subject,
        teacher,
        room,
        _lesson_type,
        parity,
    ) in seed_demo_data.SCHEDULE_DATA:
        start, end = seed_demo_data._pair(seed_demo_data._DAY_BASE[weekday], pair_num)
        items.append(
            ScheduleItemInternal(
                weekday=weekday,
                start_time=start,
                end_time=end,
                parity=parity,
                teacher=teacher,
                room=room,
            )
        )

    conflicts = await ScheduleOptimizerService().batch_detect_conflicts(items)

    assert conflicts == []


async def test_seed_schedule_rejects_but_preserves_legacy_group_conflicts(
    db_session, capsys
) -> None:
    from app.core.exceptions.domain import BusinessRuleViolation

    group = await seed_demo_data.seed_group(db_session)
    user = await seed_demo_data.seed_user(db_session, group)
    start, end = seed_demo_data._pair(seed_demo_data._DAY_BASE["friday"], 4)
    legacy_rows = [
        seed_demo_data.Schedule(
            group_id=group.id,
            creator_id=user.id,
            subject=subject,
            teacher=teacher,
            room=room,
            weekday="friday",
            start_time=start,
            end_time=end,
            parity="even",
            lesson_type="lecture",
        )
        for subject, teacher, room in (
            ("Защита информации", "Лебедев П.А.", "В-215"),
            ("Компьютерные сети", "Морозов С.Г.", "А-203"),
        )
    ]
    db_session.add_all(legacy_rows)
    await db_session.flush()

    try:
        with pytest.raises(BusinessRuleViolation):
            await seed_demo_data.seed_schedule(db_session, group, user)

        rows = await db_session.scalars(
            select(seed_demo_data.Schedule).where(
                seed_demo_data.Schedule.group_id == group.id
            )
        )
        saved_rows = rows.all()
        assert len(saved_rows) == 2
        assert {row.subject for row in saved_rows} == {
            "Защита информации",
            "Компьютерные сети",
        }
    finally:
        await db_session.rollback()
        capsys.readouterr()
