"""Real PostgreSQL proof for idempotent content-notification outbox delivery."""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import re
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import asyncpg
import pytest
import pytest_asyncio
import yaml
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

import app.core.database as database
import app.services.event_handlers as event_handlers
import app.services.notifications.delivery as notifications_delivery
import app.services.notifications.schedule_reminders as schedule_reminders_module
import app.workers.notifications as notifications_worker
import app.workers.outbox as outbox_module
from alembic import command
from app.core.config import settings
from app.core.events import (
    EventBus,
    NotificationsRequested,
    capture_domain_events,
    register_event_listeners,
)
from app.models import Group, Schedule
from app.models.domain_events import StoredEvent
from app.models.news import News
from app.models.notifications import Notification
from app.repositories.event_repository import EventRepository
from app.repositories.news_repository import NewsRepository
from tests.integration.owned_postgres import _LoopbackMigrationPostgres

_RUN_INTEGRATION_TESTS = os.getenv("RUN_INTEGRATION_TESTS") == "1"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _pinned_postgres_image() -> str:
    """Read the test database's immutable image pin from the Compose source."""
    compose = yaml.safe_load(
        (_PROJECT_ROOT / "docker-compose.test.yml").read_text(encoding="utf-8")
    )
    image = compose["services"]["postgres"]["image"]
    if (
        not isinstance(image, str)
        or re.fullmatch(r"pgvector/pgvector:pg17@sha256:[0-9a-f]{64}", image) is None
    ):
        raise ValueError("docker-compose.test.yml must pin pgvector/pg17 by SHA-256")
    return image


_POSTGRES_IMAGE = _pinned_postgres_image()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _RUN_INTEGRATION_TESTS,
        reason="Set RUN_INTEGRATION_TESTS=1 to run owned PostgreSQL integration",
    ),
]


@pytest.fixture(scope="module", autouse=True)
def prepare_database() -> Iterator[None]:
    """Keep this module off the shared suite database; tests own fresh PG."""
    yield


@pytest.fixture(autouse=True)
def clean_database() -> Iterator[None]:
    """Do not truncate the shared suite database from this isolated module."""
    yield


@pytest.fixture(scope="module")
def postgres_server():
    assert _RUN_INTEGRATION_TESTS, "Owned PostgreSQL integration was not enabled"

    operator_url = os.environ.get("MIGRATION_ROUNDTRIP_DATABASE_URL")
    if operator_url:
        # The root operator owns the server; each test owns its child database.
        yield _LoopbackMigrationPostgres(operator_url)
        return

    run_id = uuid.uuid4().hex
    postgres = PostgresContainer(
        _POSTGRES_IMAGE,
        name=f"ue-aud197198-pg17-{run_id}",
        labels={
            "university-ecosystem.dev/test-owner": f"aud197198-{run_id}",
            "university-ecosystem.dev/test-purpose": "notification-outbox-integration",
        },
        mem_limit=1024**3,
        memswap_limit=1024**3,
        nano_cpus=2_000_000_000,
        pids_limit=256,
    )
    # Docker SDK accepts a host-IP/host-port tuple; None requests a random host port.
    cast(Any, postgres.ports)[str(postgres.port)] = ("127.0.0.1", None)
    with postgres:
        yield postgres


def _upgrade_owned_database(connection, database_url: str) -> None:
    config = Config(str(_PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


def _expected_alembic_heads() -> set[str]:
    config = Config(str(_PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    return set(ScriptDirectory.from_config(config).get_heads())


@pytest_asyncio.fixture
async def postgres_app_database(
    postgres_server,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncEngine]:
    base_url = make_url(postgres_server.get_connection_url(driver="asyncpg"))
    database_name = f"ue_aud197198_{uuid.uuid4().hex}"
    maintenance_url = base_url.set(
        drivername="postgresql", database="postgres"
    ).render_as_string(hide_password=False)
    target_url = base_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    administrator = await asyncpg.connect(maintenance_url, timeout=10)
    database_created = False
    engine: AsyncEngine | None = None
    try:
        # The random name is solely an identifier in this fixture-owned container.
        # Set ownership only after CREATE succeeds; never drop a colliding database.
        await administrator.execute(f'CREATE DATABASE "{database_name}"')
        database_created = True
        engine = create_async_engine(target_url, pool_size=4, max_overflow=0)
        session_factory = async_sessionmaker(
            engine, expire_on_commit=False, class_=AsyncSession
        )

        with monkeypatch.context() as database_patch:
            database_patch.setattr(database, "_engine", engine)
            database_patch.setattr(database, "_async_session", session_factory)
            database_patch.setattr(database, "_read_replica_engine", None)
            database_patch.setattr(database, "_read_session_factory", None)
            database_patch.setenv("DATABASE_URL", target_url)

            assert database.engine.dialect.name == "postgresql"
            async with engine.connect() as connection:
                actual_database = await connection.scalar(
                    text("SELECT current_database()")
                )
                assert actual_database == database_name
                # The identity SELECT autobegins; leave transaction control to Alembic.
                await connection.rollback()
                await connection.run_sync(
                    lambda sync_connection: _upgrade_owned_database(
                        sync_connection, target_url
                    )
                )

            async with engine.connect() as connection:
                applied_revisions = list(
                    (
                        await connection.scalars(
                            text("SELECT version_num FROM alembic_version")
                        )
                    ).all()
                )
                assert set(applied_revisions) == _expected_alembic_heads()

            if not sqlalchemy_event.contains(
                Session, "after_flush", capture_domain_events
            ):
                await register_event_listeners()

            yield engine
    finally:
        try:
            if engine is not None:
                await engine.dispose()
        finally:
            try:
                if database_created:
                    await administrator.execute(
                        f'DROP DATABASE "{database_name}" WITH (FORCE)'
                    )
            finally:
                await administrator.close()


@pytest_asyncio.fixture
async def db_session(postgres_app_database: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with database.async_session() as session:
        yield session
        await session.rollback()


def _require_postgres() -> None:
    if database.engine.dialect.name != "postgresql":
        pytest.fail("owned notification outbox fixture must use PostgreSQL")


async def _source_event(db_session, event_type: str, aggregate_id: uuid.UUID):
    result = await db_session.scalars(
        select(StoredEvent).where(
            StoredEvent.event_type == event_type,
            StoredEvent.aggregate_id == str(aggregate_id),
        )
    )
    event = result.one()
    assert event.status == "pending"
    return event


async def _dispatch_replay(worker, event: StoredEvent) -> None:
    await asyncio.gather(worker._dispatch_event(event), worker._dispatch_event(event))


async def _assert_one_notification_and_request(
    *, dedupe_key: str, expected_users: set[uuid.UUID]
) -> None:
    async with database.async_session() as db:
        rows = list(
            (
                await db.scalars(
                    select(Notification).where(Notification.dedupe_key == dedupe_key)
                )
            ).all()
        )
        assert len(rows) == len(expected_users)
        assert {row.user_id for row in rows} == expected_users
        ids = {str(row.id) for row in rows}
        requests = list(
            (
                await db.scalars(
                    select(StoredEvent).where(
                        StoredEvent.event_type == "notification.delivery_requested"
                    )
                )
            ).all()
        )
        matching = [
            event
            for event in requests
            if set(event.payload.get("notification_ids", [])) == ids
        ]
        assert len(matching) == 1


async def test_content_created_outbox_replay_is_idempotent(
    db_session, user_factory, monkeypatch
):
    _require_postgres()
    author = await user_factory(role="student")
    administrator = await user_factory(role="admin")

    news_dto = await NewsRepository(db_session).create(
        {"title": "Outbox news", "content": "News body", "author_id": author.id},
        locale="en",
    )
    now = datetime.now(UTC)
    event_dto = await EventRepository(db_session).create(
        {
            "title": "Outbox event",
            "description": "Event body",
            "location": "Room 1",
            "event_type": "meeting",
            "starts_at": now + timedelta(days=1),
            "ends_at": now + timedelta(days=1, hours=1),
            "created_by": author.id,
        },
        locale="en",
    )
    comment = await NewsRepository(db_session).create_comment(
        news_dto.id, author.id, "Comment body", locale="en"
    )
    await db_session.commit()

    news_event = await _source_event(db_session, "news.created", news_dto.id)
    event_event = await _source_event(db_session, "event.created", event_dto.id)
    comment_event = await _source_event(db_session, "news.comment_created", comment.id)
    assert news_event.payload["locale"] == "en"
    assert event_event.payload["locale"] == "en"
    assert comment_event.payload == {
        "_schema_version": 1,
        "comment_id": str(comment.id),
        "locale": "en",
    }

    bus = EventBus()
    monkeypatch.setattr(event_handlers, "event_bus", bus)
    monkeypatch.setattr(outbox_module, "event_bus", bus)
    monkeypatch.setattr(event_handlers, "generate_event_embedding", AsyncMock())
    monkeypatch.setattr(event_handlers, "generate_news_embedding", AsyncMock())
    monkeypatch.setattr(event_handlers, "index_event_for_search", AsyncMock())
    monkeypatch.setattr(event_handlers, "index_news_for_search", AsyncMock())
    event_handlers.configure_event_handlers()
    worker = outbox_module.OutboxWorker()

    monkeypatch.setattr(
        "app.services.notifications.delivery.send_web_push",
        AsyncMock(
            side_effect=AssertionError("push must remain behind its outbox event")
        ),
    )
    await _dispatch_replay(worker, news_event)
    await _dispatch_replay(worker, event_event)
    await _dispatch_replay(worker, comment_event)

    await _assert_one_notification_and_request(
        dedupe_key=f"news.created:{news_dto.id}",
        expected_users={author.id, administrator.id},
    )
    await _assert_one_notification_and_request(
        dedupe_key=f"events.created:{event_dto.id}",
        expected_users={author.id, administrator.id},
    )
    await _assert_one_notification_and_request(
        dedupe_key=f"news.comment:{comment.id}",
        expected_users={administrator.id},
    )


async def test_comment_outbox_process_batch_retries_and_acknowledges_durable_delivery(
    db_session, user_factory, monkeypatch
):
    """Process a committed comment through the outbox, then replay safely."""
    _require_postgres()
    author = await user_factory(role="student")
    administrator = await user_factory(role="admin")
    news_dto = await NewsRepository(db_session).create(
        {"title": "Comment outbox", "content": "News body", "author_id": author.id},
        locale="en",
    )
    comment = await NewsRepository(db_session).create_comment(
        news_dto.id, author.id, "Comment body", locale="en"
    )
    await db_session.commit()
    comment_event = await _source_event(db_session, "news.comment_created", comment.id)

    original_notify_about_comment = event_handlers.notify_about_comment
    failures_remaining = 1

    async def fail_once_before_notification_commit(
        db, news, comment_record, comment_author, *, locale=None
    ):
        nonlocal failures_remaining
        count = await original_notify_about_comment(
            db, news, comment_record, comment_author, locale=locale
        )
        if failures_remaining:
            failures_remaining -= 1
            raise RuntimeError("injected failure before comment notification commit")
        return count

    bus = EventBus()

    async def acknowledge(_event):
        return None

    bus.subscribe("user.created", acknowledge)
    bus.subscribe("news.created", acknowledge)
    bus.subscribe("notification.delivery_requested", acknowledge)
    bus.subscribe(
        "news.comment_created",
        event_handlers.handle_news_comment_created_notification,
    )
    monkeypatch.setattr(
        event_handlers, "notify_about_comment", fail_once_before_notification_commit
    )
    monkeypatch.setattr(outbox_module, "event_bus", bus)
    monkeypatch.setattr(
        "app.services.notifications.delivery.send_web_push",
        AsyncMock(
            side_effect=AssertionError("push must remain behind its outbox event")
        ),
    )
    worker = outbox_module.OutboxWorker(batch_size=100)

    await worker.process_batch()

    async with database.async_session() as verification_session:
        failed_event = await verification_session.get(StoredEvent, comment_event.id)
        assert failed_event is not None
        assert failed_event.processed_at is None
        assert failed_event.error_count == 1
        failed_notifications = await verification_session.scalars(
            select(Notification).where(
                Notification.dedupe_key == f"news.comment:{comment.id}"
            )
        )
        assert list(failed_notifications.all()) == []
        failed_requests = await verification_session.scalars(
            select(StoredEvent).where(
                StoredEvent.event_type == "notification.delivery_requested"
            )
        )
        assert list(failed_requests.all()) == []

    await worker.process_batch()

    async with database.async_session() as verification_session:
        processed_event = await verification_session.get(StoredEvent, comment_event.id)
        assert processed_event is not None
        assert processed_event.processed_at is not None
        assert processed_event.error_count == 1

    await _assert_one_notification_and_request(
        dedupe_key=f"news.comment:{comment.id}",
        expected_users={administrator.id},
    )

    async with database.async_session() as replay_session:
        replay_event = await replay_session.get(StoredEvent, comment_event.id)
        assert replay_event is not None
        assert replay_event.processed_at is not None
        await _dispatch_replay(worker, replay_event)

    await _assert_one_notification_and_request(
        dedupe_key=f"news.comment:{comment.id}",
        expected_users={administrator.id},
    )


async def test_legacy_news_created_without_locale_reaches_notifications(
    db_session, user_factory, monkeypatch
):
    """Legacy repository calls still create durable content notifications."""
    _require_postgres()
    author = await user_factory(role="student")
    administrator = await user_factory(role="admin")
    news_dto = await NewsRepository(db_session).create(
        {"title": "Legacy news", "content": "Legacy body", "author_id": author.id}
    )
    await db_session.commit()

    news_event = await _source_event(db_session, "news.created", news_dto.id)
    bus = EventBus()
    monkeypatch.setattr(event_handlers, "event_bus", bus)
    monkeypatch.setattr(outbox_module, "event_bus", bus)
    monkeypatch.setattr(event_handlers, "generate_news_embedding", AsyncMock())
    monkeypatch.setattr(event_handlers, "index_news_for_search", AsyncMock())
    event_handlers.configure_event_handlers()
    worker = outbox_module.OutboxWorker()
    monkeypatch.setattr(
        "app.services.notifications.delivery.send_web_push",
        AsyncMock(side_effect=AssertionError("push remains behind its outbox event")),
    )

    await worker._dispatch_event(news_event)

    await _assert_one_notification_and_request(
        dedupe_key=f"news.created:{news_dto.id}",
        expected_users={author.id, administrator.id},
    )


async def test_news_and_source_event_rollback_together(db_session, user_factory):
    author = await user_factory(role="student")
    news_dto = await NewsRepository(db_session).create(
        {
            "title": "Rolled back news",
            "content": "Not committed",
            "author_id": author.id,
        },
        locale="en",
    )

    source_events = list(
        (
            await db_session.scalars(
                select(StoredEvent).where(
                    StoredEvent.event_type == "news.created",
                    StoredEvent.aggregate_id == str(news_dto.id),
                )
            )
        ).all()
    )
    assert len(source_events) == 1
    assert source_events[0].payload["locale"] == "en"

    await db_session.rollback()
    async with database.async_session() as verification_session:
        assert await verification_session.get(News, news_dto.id) is None
        persisted_events = await verification_session.scalars(
            select(StoredEvent).where(
                StoredEvent.event_type == "news.created",
                StoredEvent.aggregate_id == str(news_dto.id),
            )
        )
        assert list(persisted_events.all()) == []


async def test_notification_transaction_failure_recovers_on_outbox_replay(
    db_session, user_factory, monkeypatch
):
    author = await user_factory(role="student")
    administrator = await user_factory(role="admin")
    news_dto = await NewsRepository(db_session).create(
        {"title": "Retryable news", "content": "Retry body", "author_id": author.id},
        locale="en",
    )
    await db_session.commit()
    news_event = await _source_event(db_session, "news.created", news_dto.id)

    original_notify_about_news = event_handlers.notify_about_news
    failures_remaining = 1

    async def fail_once_before_notification_commit(db, news, *, locale=None):
        nonlocal failures_remaining
        count = await original_notify_about_news(db, news, locale=locale)
        if failures_remaining:
            failures_remaining -= 1
            raise RuntimeError(
                "injected failure before notification transaction commit"
            )
        return count

    bus = EventBus()

    async def acknowledge(_event):
        return None

    bus.subscribe("user.created", acknowledge)
    bus.subscribe("notification.delivery_requested", acknowledge)
    bus.subscribe("news.created", event_handlers.handle_news_created_notification)
    monkeypatch.setattr(
        event_handlers, "notify_about_news", fail_once_before_notification_commit
    )
    monkeypatch.setattr(outbox_module, "event_bus", bus)
    monkeypatch.setattr(
        "app.services.notifications.delivery.send_web_push",
        AsyncMock(
            side_effect=AssertionError("push must remain behind its outbox event")
        ),
    )
    worker = outbox_module.OutboxWorker(batch_size=100)

    await worker.process_batch()

    async with database.async_session() as verification_session:
        failed_event = await verification_session.get(StoredEvent, news_event.id)
        assert failed_event is not None
        assert failed_event.processed_at is None
        assert failed_event.error_count == 1
        failed_notifications = await verification_session.scalars(
            select(Notification).where(
                Notification.dedupe_key == f"news.created:{news_dto.id}"
            )
        )
        assert list(failed_notifications.all()) == []
        failed_requests = await verification_session.scalars(
            select(StoredEvent).where(
                StoredEvent.event_type == "notification.delivery_requested"
            )
        )
        assert list(failed_requests.all()) == []

    await worker.process_batch()

    async with database.async_session() as verification_session:
        recovered_event = await verification_session.get(StoredEvent, news_event.id)
        assert recovered_event is not None
        assert recovered_event.processed_at is not None
        assert recovered_event.error_count == 1

    await _assert_one_notification_and_request(
        dedupe_key=f"news.created:{news_dto.id}",
        expected_users={author.id, administrator.id},
    )


async def test_scheduler_ticks_commit_one_campus_reminder_and_outbox(
    postgres_app_database, db_session, user_factory, monkeypatch
):
    """Two actual scheduler ticks persist one reminder without a caller commit."""
    _require_postgres()
    fixed_now = dt.datetime(2026, 1, 4, 23, 55, tzinfo=dt.UTC)

    class _FixedDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    clock = SimpleNamespace(**vars(dt))
    clock.datetime = _FixedDateTime
    monkeypatch.setattr(schedule_reminders_module, "dt", clock)
    monkeypatch.setattr(notifications_delivery, "dt", clock)
    monkeypatch.setattr(settings, "campus_timezone", "Europe/Istanbul")
    monkeypatch.setattr(notifications_delivery, "_is_push_configured", lambda: False)

    group = Group(name="Scheduler PostgreSQL reminder")
    db_session.add(group)
    await db_session.flush()
    user = await user_factory(group_id=group.id)
    user_id = user.id
    db_session.add_all(
        [
            Schedule(
                group_id=group.id,
                creator_id=user_id,
                subject="Matching local Monday",
                weekday="monday",
                parity="even",
                start_time=dt.datetime(1970, 1, 5, 3, 0, tzinfo=dt.UTC),
                end_time=dt.datetime(1970, 1, 5, 4, 0, tzinfo=dt.UTC),
            ),
            Schedule(
                group_id=group.id,
                creator_id=user_id,
                subject="Wrong local parity",
                weekday="monday",
                parity="odd",
                start_time=dt.datetime(1970, 1, 5, 3, 0, tzinfo=dt.UTC),
                end_time=dt.datetime(1970, 1, 5, 4, 0, tzinfo=dt.UTC),
            ),
            Schedule(
                group_id=group.id,
                creator_id=user_id,
                subject="Wrong local weekday",
                weekday="tuesday",
                parity="both",
                start_time=dt.datetime(1970, 1, 6, 3, 0, tzinfo=dt.UTC),
                end_time=dt.datetime(1970, 1, 6, 4, 0, tzinfo=dt.UTC),
            ),
        ]
    )
    await db_session.commit()

    scheduler = notifications_worker.NotificationsScheduler(
        poll_seconds=1,
        window_minutes=10,
        max_backoff_seconds=1,
        metrics=None,
    )
    assert await scheduler.run_once() == 1
    assert await scheduler.run_once() == 0

    # No test-side commit after either tick: the worker owns durability.
    reader_factory = async_sessionmaker(postgres_app_database, expire_on_commit=False)
    async with reader_factory() as reader:
        notifications = list(
            (
                await reader.scalars(
                    select(Notification).where(
                        Notification.user_id == user_id,
                        Notification.type == "schedule.reminder",
                        Notification.url == "/schedule",
                    )
                )
            ).all()
        )
        outbox_events = list(
            (
                await reader.scalars(
                    select(StoredEvent).where(
                        StoredEvent.event_type == NotificationsRequested.EVENT_TYPE,
                        StoredEvent.aggregate_type == "NotificationBatch",
                    )
                )
            ).all()
        )

    assert len(notifications) == 1
    assert "05.01 · 03:00" in notifications[0].body
    assert len(outbox_events) == 1
    assert outbox_events[0].payload["notification_ids"] == [str(notifications[0].id)]
