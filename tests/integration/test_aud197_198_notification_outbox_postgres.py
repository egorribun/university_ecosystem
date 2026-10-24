"""Real PostgreSQL proof for idempotent content-notification outbox delivery."""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import re
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
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
import app.core.db.listeners as tenant_listeners
import app.core.tenant as tenant_context
import app.services.event_handlers as event_handlers
import app.services.notifications.delivery as notifications_delivery
import app.services.notifications.schedule_reminders as schedule_reminders_module
import app.services.webpush as webpush_module
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
from app.models import Group, Schedule, User
from app.models.domain_events import StoredEvent
from app.models.news import News
from app.models.notifications import (
    Notification,
    NotificationDelivery,
    PushSubscription,
)
from app.models.tenant import Tenant
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


@pytest.fixture
def _owned_push_runtime(
    postgres_app_database: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Keep canonical result processing on this fixture's owned database."""
    monkeypatch.setattr(notifications_delivery, "_is_push_configured", lambda: True)
    monkeypatch.setattr(webpush_module, "_Session", None)
    monkeypatch.setattr(webpush_module, "_sync_engine", None)
    monkeypatch.setattr(
        webpush_module,
        "_sync_url_cache",
        postgres_app_database.url.set(drivername="postgresql+psycopg"),
    )
    try:
        yield
    finally:
        # These globals were isolated above; never dispose the pre-existing engine.
        webpush_module.cleanup()


async def _create_delivery_outbox_batch(
    db_session: AsyncSession, user_ids: list[uuid.UUID]
) -> tuple[StoredEvent, dict[uuid.UUID, uuid.UUID]]:
    created = await notifications_delivery.create_notifications_for_users(
        db_session,
        title="Durable news",
        body="Delivery replay",
        type="news.new",
        url="/news",
        user_ids=user_ids,
        topic="news.published",
        push_via_outbox_only=True,
    )
    assert created == len(user_ids)
    await db_session.commit()
    request = (
        await db_session.scalars(
            select(StoredEvent).where(
                StoredEvent.event_type == NotificationsRequested.EVENT_TYPE
            )
        )
    ).one()
    notifications = list((await db_session.scalars(select(Notification))).all())
    assert len(notifications) == len(user_ids)
    identifiers = {row.user_id: row.id for row in notifications}
    assert set(identifiers) == set(user_ids)
    await db_session.commit()
    return request, identifiers


async def test_delivery_outbox_concurrent_sessions_send_successful_pair_once(
    db_session,
    user_factory,
    push_subscription_factory,
    _owned_push_runtime,
    monkeypatch,
):
    """Dropping the notification row lock must allow a detectable duplicate send."""
    _require_postgres()
    user = await user_factory()
    subscription = await push_subscription_factory(user)
    subscription_id = subscription.id
    request, identifiers = await _create_delivery_outbox_batch(db_session, [user.id])
    notification_id = identifiers[user.id]
    duplicate = StoredEvent(
        event_type=NotificationsRequested.EVENT_TYPE,
        aggregate_type="NotificationBatch",
        aggregate_id=str(uuid.uuid4()),
        payload={
            **request.payload,
            "notification_ids": list(request.payload["notification_ids"]),
        },
    )
    db_session.add(duplicate)
    await db_session.commit()

    bus = EventBus()
    bus.subscribe(
        NotificationsRequested.EVENT_TYPE, event_handlers.handle_notifications_requested
    )
    monkeypatch.setattr(outbox_module, "event_bus", bus)
    worker = outbox_module.OutboxWorker()

    session_pids: asyncio.Queue[int] = asyncio.Queue()
    real_session_factory = database.async_session

    @asynccontextmanager
    async def observed_sessions() -> AsyncIterator[AsyncSession]:
        async with real_session_factory() as session:
            pid = await session.scalar(text("SELECT pg_backend_pid()"))
            assert isinstance(pid, int)
            session_pids.put_nowait(pid)
            yield session

    monkeypatch.setattr(event_handlers, "async_session", observed_sessions)
    first_send_started = asyncio.Event()
    release_first_send = asyncio.Event()
    provider_calls: list[tuple[uuid.UUID, str]] = []

    async def fake_provider(subscription, payload):
        provider_calls.append((subscription.id, payload["data"]["notificationId"]))
        if len(provider_calls) == 1:
            first_send_started.set()
            await release_first_send.wait()
        return webpush_module.WebPushResult(
            subscription_id=subscription.id,
            endpoint=subscription.endpoint,
            user_id=subscription.user_id,
            status="sent",
            status_code=201,
        )

    monkeypatch.setattr(webpush_module, "_send_push_async", fake_provider)
    tasks: list[asyncio.Task[None]] = []
    try:
        async with asyncio.timeout(8):
            tasks.append(asyncio.create_task(worker._dispatch_event(request)))
            await asyncio.wait_for(first_send_started.wait(), timeout=3)
            first_pid = await asyncio.wait_for(session_pids.get(), timeout=3)
            tasks.append(asyncio.create_task(worker._dispatch_event(duplicate)))
            second_pid = await asyncio.wait_for(session_pids.get(), timeout=3)
            assert first_pid != second_pid

            observed_block = False
            # Observe the real PG wait, not merely that a coroutine was scheduled.
            # The query-count cap and deadline are both mandatory; no timing sleeps.
            async with asyncio.timeout(5):
                async with database.async_session() as observer:
                    for _ in range(100):
                        blockers = await observer.scalar(
                            text("SELECT pg_blocking_pids(:waiting_pid)"),
                            {"waiting_pid": second_pid},
                        )
                        if blockers and first_pid in blockers:
                            observed_block = True
                            break
                        assert len(provider_calls) == 1, (
                            "Concurrent replay sent before the first journal committed"
                        )
                        assert not tasks[1].done(), (
                            "Replay completed before the first journal commit"
                        )
            assert observed_block, "PostgreSQL did not report the row-lock wait"
            assert not release_first_send.is_set()
            assert provider_calls == [(subscription_id, str(notification_id))]
            release_first_send.set()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
    finally:
        release_first_send.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        async with asyncio.timeout(15):
            await asyncio.gather(*tasks, return_exceptions=True)

    async with database.async_session() as reader:
        deliveries = list((await reader.scalars(select(NotificationDelivery))).all())
        assert len(deliveries) == 1
        delivery = deliveries[0]
        actual_delivery = (
            delivery.notification_id,
            delivery.subscription_id,
            delivery.channel,
            delivery.status,
            delivery.status_code,
        )
        expected_delivery = (notification_id, subscription_id, "webpush", "sent", 201)
        assert actual_delivery == expected_delivery
        assert delivery.delivered_at is not None
        journal_identity = (delivery.id, delivery.attempted_at)
        notification = (
            await reader.scalars(
                select(Notification).where(Notification.id == notification_id)
            )
        ).one()
        assert notification.read is False
        subscription_row = await reader.get(PushSubscription, subscription_id)
        assert subscription_row is not None
        assert subscription_row.last_seen_at is not None

    # A new handler session must read the committed journal, not an identity map.
    async with asyncio.timeout(15):
        await worker._dispatch_event(request)
    assert provider_calls == [(subscription_id, str(notification_id))]
    async with database.async_session() as reader:
        delivery = (await reader.scalars(select(NotificationDelivery))).one()
        assert (delivery.id, delivery.attempted_at) == journal_identity


async def test_delivery_outbox_partial_failure_commits_before_recipient_retry(
    db_session,
    user_factory,
    push_subscription_factory,
    _owned_push_runtime,
    monkeypatch,
):
    """Losing partial commits or replay filtering must resend the successful pair."""
    _require_postgres()
    first_user = await user_factory()
    second_user = await user_factory()
    first_subscription = await push_subscription_factory(first_user)
    second_subscription = await push_subscription_factory(second_user)
    first_subscription_id = first_subscription.id
    second_subscription_id = second_subscription.id
    request, identifiers = await _create_delivery_outbox_batch(
        db_session, [first_user.id, second_user.id]
    )
    request_id = request.id
    provider_calls: list[uuid.UUID] = []

    async def fake_provider(subscription, payload):
        expected_id = identifiers[subscription.user_id]
        assert payload["data"]["notificationId"] == str(expected_id)
        provider_calls.append(subscription.id)
        failed = (
            subscription.id == second_subscription_id
            and provider_calls.count(second_subscription_id) == 1
        )
        return webpush_module.WebPushResult(
            subscription_id=subscription.id,
            endpoint=subscription.endpoint,
            user_id=subscription.user_id,
            status="error" if failed else "sent",
            status_code=503 if failed else 201,
            error="provider unavailable" if failed else None,
        )

    monkeypatch.setattr(webpush_module, "_send_push_async", fake_provider)
    bus = EventBus()
    bus.subscribe("user.created", event_handlers.handle_user_created)
    bus.subscribe(
        NotificationsRequested.EVENT_TYPE, event_handlers.handle_notifications_requested
    )
    monkeypatch.setattr(outbox_module, "event_bus", bus)
    worker = outbox_module.OutboxWorker(batch_size=100)
    async with asyncio.timeout(20):
        await worker.process_batch()

    async with database.async_session() as reader:
        pending = await reader.get(StoredEvent, request_id)
        assert pending is not None
        assert pending.processed_at is None
        assert pending.error_count == 1
        deliveries = list((await reader.scalars(select(NotificationDelivery))).all())
        assert len(deliveries) == 2
        by_subscription = {row.subscription_id: row for row in deliveries}
        assert set(by_subscription) == {first_subscription_id, second_subscription_id}
        assert by_subscription[first_subscription_id].status == "sent"
        assert by_subscription[first_subscription_id].delivered_at is not None
        assert by_subscription[second_subscription_id].status == "error"
        assert by_subscription[second_subscription_id].delivered_at is None
        assert by_subscription[second_subscription_id].status_code == 503
        journal_identities = {
            row.subscription_id: (row.id, row.attempted_at) for row in deliveries
        }
    assert provider_calls.count(first_subscription_id) == 1
    assert provider_calls.count(second_subscription_id) == 1

    async with asyncio.timeout(20):
        await worker.process_batch()

    async with database.async_session() as reader:
        processed = await reader.get(StoredEvent, request_id)
        assert processed is not None
        assert processed.processed_at is not None
        assert processed.error_count == 1
        deliveries = list((await reader.scalars(select(NotificationDelivery))).all())
        assert len(deliveries) == 2
        persisted_identities = {
            row.subscription_id: (row.id, row.attempted_at) for row in deliveries
        }
        assert persisted_identities == journal_identities
        assert all(
            row.channel == "webpush"
            and row.status == "sent"
            and row.status_code == 201
            and row.delivered_at is not None
            for row in deliveries
        )
        assert all(
            not notification.read
            for notification in (await reader.scalars(select(Notification))).all()
        )
        subscriptions = list((await reader.scalars(select(PushSubscription))).all())
        assert len(subscriptions) == 2
        assert all(row.last_seen_at is not None for row in subscriptions)
    assert provider_calls.count(first_subscription_id) == 1
    assert provider_calls.count(second_subscription_id) == 2

    async with asyncio.timeout(15):
        await worker._dispatch_event(request)
    async with asyncio.timeout(20):
        assert await worker.process_batch() == 0
    assert provider_calls.count(first_subscription_id) == 1
    assert provider_calls.count(second_subscription_id) == 2


@contextmanager
def _tenant_proof_context(tenant_id: str) -> Iterator[None]:
    tenant_token = tenant_context.tenant_id_ctx.set(tenant_id)
    bypass_token = tenant_context.bypass_rls_ctx.set(False)
    try:
        yield
    finally:
        tenant_context.bypass_rls_ctx.reset(bypass_token)
        tenant_context.tenant_id_ctx.reset(tenant_token)


@pytest_asyncio.fixture
async def _owned_tenant_worker(postgres_app_database: AsyncEngine):
    """Grant one new NOLOGIN role access only to this owned child database."""
    engine = postgres_app_database
    role_name = f"ue_aud197_role_{uuid.uuid4().hex}"
    assert re.fullmatch(r"ue_aud197_role_[0-9a-f]{32}", role_name)
    role_created = False
    grants_applied = False
    role_listener_registered = False
    tenant_listener_owned = False
    transaction_pids: list[int] = []
    grants = (
        ("USAGE", "SCHEMA public"),
        (
            "SELECT",
            "TABLE public.news, public.events, public.users, "
            "public.user_push_topics, public.notifications, public.stored_events",
        ),
        ("INSERT", "TABLE public.notifications, public.stored_events"),
        ("UPDATE", "TABLE public.stored_events"),
    )

    class TenantProofSession(Session):
        pass

    def constrain_role(_session, _transaction, connection):
        # The identifier is solely the checked random name generated above.
        connection.exec_driver_sql(f'SET LOCAL ROLE "{role_name}"')
        current_role, pid = connection.execute(
            text("SELECT current_user, pg_backend_pid()")
        ).one()
        assert current_role == role_name
        transaction_pids.append(pid)

    try:
        async with asyncio.timeout(20):
            async with engine.begin() as connection:
                database_name = await connection.scalar(
                    text("SELECT current_database()")
                )
                assert database_name == engine.url.database
                assert re.fullmatch(r"ue_aud197198_[0-9a-f]{32}", database_name)
                await connection.exec_driver_sql(
                    f'CREATE ROLE "{role_name}" NOLOGIN NOSUPERUSER NOBYPASSRLS '
                    "NOCREATEDB NOCREATEROLE NOINHERIT"
                )
            # CREATE must commit before this fixture acquires cleanup ownership.
            role_created = True
            async with engine.begin() as connection:
                for privileges, objects in grants:
                    await connection.exec_driver_sql(
                        f'GRANT {privileges} ON {objects} TO "{role_name}"'
                    )
            grants_applied = True

        tenant_listener_owned = not sqlalchemy_event.contains(
            Session, "after_begin", tenant_listeners.set_pg_tenant_context
        )
        if tenant_listener_owned:
            tenant_listeners.register_tenant_listeners()
        sqlalchemy_event.listen(TenantProofSession, "after_begin", constrain_role)
        role_listener_registered = True
        sessions = async_sessionmaker(
            engine,
            class_=AsyncSession,
            sync_session_class=TenantProofSession,
            expire_on_commit=False,
        )
        yield SimpleNamespace(
            role_name=role_name,
            sessions=sessions,
            transaction_pids=transaction_pids,
        )
    finally:
        try:
            if role_listener_registered:
                sqlalchemy_event.remove(
                    TenantProofSession, "after_begin", constrain_role
                )
            if tenant_listener_owned:
                sqlalchemy_event.remove(
                    Session, "after_begin", tenant_listeners.set_pg_tenant_context
                )
        finally:
            if role_created:
                async with asyncio.timeout(20):
                    async with engine.begin() as connection:
                        if grants_applied:
                            for privileges, objects in reversed(grants):
                                await connection.exec_driver_sql(
                                    f"REVOKE {privileges} ON {objects} "
                                    f'FROM "{role_name}"'
                                )
                        # No IF EXISTS, DROP OWNED, CASCADE or pre-existing role.
                        await connection.exec_driver_sql(f'DROP ROLE "{role_name}"')
                    async with engine.connect() as connection:
                        remaining = await connection.scalar(
                            text("SELECT count(*) FROM pg_roles WHERE rolname = :role"),
                            {"role": role_name},
                        )
                        assert remaining == 0


async def _assert_tenant_worker_transaction(
    session: AsyncSession, role_name: str, tenant_id: str
) -> int:
    result = await session.execute(
        text(
            "SELECT current_user AS role_name, pg_backend_pid() AS pid, "
            "rolsuper, rolbypassrls, rolcanlogin, rolcreatedb, rolcreaterole, "
            "rolinherit, has_schema_privilege(current_user, 'public', 'CREATE') "
            "AS can_create, "
            "coalesce(current_setting('app.current_tenant', true), '') "
            "AS tenant_id, "
            "coalesce(current_setting('app.bypass_rls', true), '') AS bypass "
            "FROM pg_roles WHERE rolname = current_user"
        )
    )
    row = result.mappings().one()
    assert row["role_name"] == role_name
    assert row["can_create"] is False
    flags = tuple(
        row[name]
        for name in (
            "rolsuper",
            "rolbypassrls",
            "rolcanlogin",
            "rolcreatedb",
            "rolcreaterole",
            "rolinherit",
        )
    )
    assert flags == (False, False, False, False, False, False)
    assert row["tenant_id"] == tenant_id
    assert row["bypass"] == ""
    return row["pid"]


@pytest.mark.parametrize(
    ("kind", "initial_context"),
    [
        pytest.param("news", "A", id="news-A"),
        pytest.param("event", "A", id="event-A"),
        pytest.param("news", "empty", id="news-empty"),
        pytest.param("event", "empty", id="event-empty"),
        pytest.param("news", "B", id="news-B"),
        pytest.param("event", "B", id="event-B"),
    ],
)
async def test_content_outbox_restores_tenant_scope(
    db_session,
    user_factory,
    _owned_tenant_worker,
    monkeypatch,
    kind,
    initial_context,
):
    """A worker must not acknowledge a tenant-hidden source without notifications."""
    _require_postgres()
    harness = _owned_tenant_worker
    tenant_a_id, tenant_b_id = uuid.uuid4(), uuid.uuid4()
    db_session.add_all(
        [
            Tenant(
                id=tenant_a_id, name="Tenant A", slug=f"aud197-a-{uuid.uuid4().hex}"
            ),
            Tenant(
                id=tenant_b_id, name="Tenant B", slug=f"aud197-b-{uuid.uuid4().hex}"
            ),
        ]
    )
    await db_session.commit()
    first_a = await user_factory()
    second_a = await user_factory()
    user_b = await user_factory()
    a_recipients = {first_a.id, second_a.id}
    await db_session.execute(
        text("UPDATE public.users SET tenant_id = :tenant_id WHERE id = :user_id"),
        [
            {"tenant_id": tenant_a_id, "user_id": first_a.id},
            {"tenant_id": tenant_a_id, "user_id": second_a.id},
            {"tenant_id": tenant_b_id, "user_id": user_b.id},
        ],
    )
    await db_session.commit()

    # tenant_id is migrated but unmapped on these ORM models. This deliberately
    # models existing/imported tenant-owned rows, not API tenant assignment.
    with _tenant_proof_context(str(tenant_a_id)):
        if kind == "news":
            content = await NewsRepository(db_session).create(
                {
                    "title": "Tenant-owned news",
                    "content": "Synthetic tenant proof",
                    "author_id": first_a.id,
                },
                locale="en",
            )
            tenant_update = text(
                "UPDATE public.news SET tenant_id = :tenant_id WHERE id = :source_id"
            )
            tenant_query = text(
                "SELECT tenant_id FROM public.news WHERE id = :source_id"
            )
            source_query = text("SELECT id FROM public.news WHERE id = :source_id")
            event_type = "news.created"
            dedupe_key = f"news.created:{content.id}"
            handler = event_handlers.handle_news_created_notification
        else:
            now = datetime.now(UTC)
            content = await EventRepository(db_session).create(
                {
                    "title": "Tenant-owned event",
                    "description": "Synthetic tenant proof",
                    "location": "Room 1",
                    "event_type": "meeting",
                    "starts_at": now + timedelta(days=1),
                    "ends_at": now + timedelta(days=1, hours=1),
                    "created_by": first_a.id,
                },
                locale="en",
            )
            tenant_update = text(
                "UPDATE public.events SET tenant_id = :tenant_id WHERE id = :source_id"
            )
            tenant_query = text(
                "SELECT tenant_id FROM public.events WHERE id = :source_id"
            )
            source_query = text("SELECT id FROM public.events WHERE id = :source_id")
            event_type = "event.created"
            dedupe_key = f"events.created:{content.id}"
            handler = event_handlers.handle_event_created_notification
        source_id = content.id
        await db_session.execute(
            tenant_update,
            {"tenant_id": tenant_a_id, "source_id": source_id},
        )
        await db_session.commit()
        stored = await _source_event(db_session, event_type, source_id)
        stored_id = stored.id
        await db_session.commit()

    async with database.async_session() as administrator:
        physical_tenant = await administrator.scalar(
            tenant_query,
            {"source_id": source_id},
        )
        assert physical_tenant == tenant_a_id
        policies = (
            await administrator.execute(
                text(
                    "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
                    "c.relowner <> r.oid AS foreign_owner "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "CROSS JOIN pg_roles r "
                    "WHERE n.nspname = 'public' AND r.rolname = :role "
                    "AND c.relname IN ('users', 'news', 'events', 'notifications')"
                ),
                {"role": harness.role_name},
            )
        ).all()
        assert {row.relname for row in policies} == {
            "users",
            "news",
            "events",
            "notifications",
        }
        assert all(
            row.relrowsecurity and row.relforcerowsecurity and row.foreign_owner
            for row in policies
        )

    for scope, expected_source, expected_users in (
        ("", None, set()),
        (str(tenant_b_id), None, {user_b.id}),
        (str(tenant_a_id), source_id, a_recipients),
    ):
        with _tenant_proof_context(scope):
            async with asyncio.timeout(10):
                async with harness.sessions() as reader:
                    await _assert_tenant_worker_transaction(
                        reader, harness.role_name, scope
                    )
                    visible_source = await reader.scalar(
                        source_query, {"source_id": source_id}
                    )
                    assert visible_source == expected_source
                    visible_users = set((await reader.scalars(select(User.id))).all())
                    assert visible_users == expected_users

    monkeypatch.setattr(notifications_delivery, "_is_push_configured", lambda: False)
    monkeypatch.setattr(
        webpush_module,
        "_send_push_async",
        AsyncMock(side_effect=AssertionError("tenant proof must defer push delivery")),
    )
    monkeypatch.setattr(event_handlers, "async_session", harness.sessions)
    monkeypatch.setattr(outbox_module, "async_session", harness.sessions)
    bus = EventBus()
    bus.subscribe("user.created", event_handlers.handle_user_created)
    bus.subscribe(event_type, handler)
    monkeypatch.setattr(outbox_module, "event_bus", bus)
    worker_scope = {"A": str(tenant_a_id), "empty": "", "B": str(tenant_b_id)}[
        initial_context
    ]
    prior_tenant = tenant_context.tenant_id_ctx.get()
    prior_bypass = tenant_context.bypass_rls_ctx.get()
    with _tenant_proof_context(worker_scope):
        harness.transaction_pids.clear()
        try:
            async with asyncio.timeout(20):
                await outbox_module.OutboxWorker(batch_size=100).process_batch()
        finally:
            assert tenant_context.tenant_id_ctx.get() == worker_scope
            assert tenant_context.bypass_rls_ctx.get() is False
        worker_pids = set(harness.transaction_pids)
        assert len(worker_pids) >= 2
        async with asyncio.timeout(10):
            async with harness.sessions() as next_transaction:
                reused_pid = await _assert_tenant_worker_transaction(
                    next_transaction, harness.role_name, worker_scope
                )
                assert reused_pid in worker_pids
    assert tenant_context.tenant_id_ctx.get() == prior_tenant
    assert tenant_context.bypass_rls_ctx.get() == prior_bypass

    async with database.async_session() as administrator:
        source = await administrator.get(StoredEvent, stored_id)
        assert source is not None
        assert source.error_count == 0
        assert source.processed_at is not None
        notifications = list(
            (
                await administrator.scalars(
                    select(Notification).where(Notification.dedupe_key == dedupe_key)
                )
            ).all()
        )
        assert len(notifications) == 2, (
            f"{kind}: tenant-owned source was acknowledged without its notifications"
        )
        assert {row.user_id for row in notifications} == a_recipients
        all_recipients = set(
            (await administrator.scalars(select(Notification.user_id))).all()
        )
        assert all_recipients == a_recipients
        requests = list(
            (
                await administrator.scalars(
                    select(StoredEvent).where(
                        StoredEvent.event_type == NotificationsRequested.EVENT_TYPE
                    )
                )
            ).all()
        )
        assert len(requests) == 1
        notification_ids = {str(row.id) for row in notifications}
        assert set(requests[0].payload["notification_ids"]) == notification_ids
        assert requests[0].processed_at is None


@pytest.mark.parametrize("kind", ["news", "event"])
async def test_legacy_null_tenant_content_ignores_worker_ambient_scope(
    db_session,
    user_factory,
    _owned_tenant_worker,
    monkeypatch,
    kind,
):
    """Legacy NULL-tenant content must not inherit a different worker tenant."""
    _require_postgres()
    harness = _owned_tenant_worker
    tenant_b_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_b_id, name="Tenant B", slug=f"aud197-legacy-{uuid.uuid4().hex}"
        )
    )
    await db_session.commit()
    first_global = await user_factory()
    second_global = await user_factory()
    user_b = await user_factory()
    global_recipients = {first_global.id, second_global.id}
    await db_session.execute(
        text("UPDATE public.users SET tenant_id = :tenant_id WHERE id = :user_id"),
        {"tenant_id": tenant_b_id, "user_id": user_b.id},
    )
    await db_session.commit()

    with _tenant_proof_context(""):
        if kind == "news":
            content = await NewsRepository(db_session).create(
                {
                    "title": "Legacy global news",
                    "content": "Synthetic legacy tenant proof",
                    "author_id": first_global.id,
                },
                locale="en",
            )
            tenant_query = text(
                "SELECT tenant_id FROM public.news WHERE id = :source_id"
            )
            source_query = text("SELECT id FROM public.news WHERE id = :source_id")
            event_type = "news.created"
            dedupe_key = f"news.created:{content.id}"
            handler = event_handlers.handle_news_created_notification
            legacy_metadata = None
        else:
            now = datetime.now(UTC)
            content = await EventRepository(db_session).create(
                {
                    "title": "Legacy global event",
                    "description": "Synthetic legacy tenant proof",
                    "location": "Room 1",
                    "event_type": "meeting",
                    "starts_at": now + timedelta(days=1),
                    "ends_at": now + timedelta(days=1, hours=1),
                    "created_by": first_global.id,
                },
                locale="en",
            )
            tenant_query = text(
                "SELECT tenant_id FROM public.events WHERE id = :source_id"
            )
            source_query = text("SELECT id FROM public.events WHERE id = :source_id")
            event_type = "event.created"
            dedupe_key = f"events.created:{content.id}"
            handler = event_handlers.handle_event_created_notification
            legacy_metadata = {}
        source_id = content.id
        await db_session.commit()
        stored = await _source_event(db_session, event_type, source_id)
        stored.metadata_ = legacy_metadata
        stored_id = stored.id
        await db_session.commit()

    async with database.async_session() as administrator:
        physical_tenant = await administrator.scalar(
            tenant_query, {"source_id": source_id}
        )
        assert physical_tenant is None
        user_tenants = (
            await administrator.execute(
                text("SELECT id, tenant_id FROM public.users ORDER BY id")
            )
        ).all()
        assert dict(user_tenants) == {
            first_global.id: None,
            second_global.id: None,
            user_b.id: tenant_b_id,
        }
        policies = (
            await administrator.execute(
                text(
                    "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
                    "c.relowner <> r.oid AS foreign_owner "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "CROSS JOIN pg_roles r "
                    "WHERE n.nspname = 'public' AND r.rolname = :role "
                    "AND c.relname IN ('users', 'news', 'events', 'notifications')"
                ),
                {"role": harness.role_name},
            )
        ).all()
        assert {row.relname for row in policies} == {
            "users",
            "news",
            "events",
            "notifications",
        }
        assert all(
            row.relrowsecurity and row.relforcerowsecurity and row.foreign_owner
            for row in policies
        )

    for scope, expected_users in (
        ("", global_recipients),
        (str(tenant_b_id), global_recipients | {user_b.id}),
    ):
        with _tenant_proof_context(scope):
            async with asyncio.timeout(10):
                async with harness.sessions() as reader:
                    await _assert_tenant_worker_transaction(
                        reader, harness.role_name, scope
                    )
                    visible_source = await reader.scalar(
                        source_query, {"source_id": source_id}
                    )
                    assert visible_source == source_id
                    visible_users = set((await reader.scalars(select(User.id))).all())
                    assert visible_users == expected_users

    monkeypatch.setattr(notifications_delivery, "_is_push_configured", lambda: False)
    monkeypatch.setattr(
        webpush_module,
        "_send_push_async",
        AsyncMock(side_effect=AssertionError("legacy proof must defer push delivery")),
    )
    monkeypatch.setattr(event_handlers, "async_session", harness.sessions)
    monkeypatch.setattr(outbox_module, "async_session", harness.sessions)
    bus = EventBus()
    bus.subscribe("user.created", event_handlers.handle_user_created)
    bus.subscribe(event_type, handler)
    monkeypatch.setattr(outbox_module, "event_bus", bus)
    prior_tenant = tenant_context.tenant_id_ctx.get()
    prior_bypass = tenant_context.bypass_rls_ctx.get()
    with _tenant_proof_context(str(tenant_b_id)):
        bypass_token = tenant_context.bypass_rls_ctx.set(True)
        harness.transaction_pids.clear()
        try:
            async with asyncio.timeout(20):
                await outbox_module.OutboxWorker(batch_size=100).process_batch()
            worker_pids = set(harness.transaction_pids)
            assert len(worker_pids) >= 2
            # Observe a subsequent transaction without inheriting the caller's
            # intentional bypass probe, then restore that caller flag as well.
            with _tenant_proof_context(str(tenant_b_id)):
                async with asyncio.timeout(10):
                    async with harness.sessions() as next_transaction:
                        reused_pid = await _assert_tenant_worker_transaction(
                            next_transaction, harness.role_name, str(tenant_b_id)
                        )
                        assert reused_pid in worker_pids
        finally:
            try:
                assert tenant_context.tenant_id_ctx.get() == str(tenant_b_id)
                assert tenant_context.bypass_rls_ctx.get() is True
            finally:
                tenant_context.bypass_rls_ctx.reset(bypass_token)
    assert tenant_context.tenant_id_ctx.get() == prior_tenant
    assert tenant_context.bypass_rls_ctx.get() == prior_bypass

    async with database.async_session() as administrator:
        source = await administrator.get(StoredEvent, stored_id)
        assert source is not None
        assert source.metadata_ == legacy_metadata
        assert source.error_count == 0
        assert source.processed_at is not None
        notifications = list(
            (
                await administrator.scalars(
                    select(Notification).where(Notification.dedupe_key == dedupe_key)
                )
            ).all()
        )
        assert len(notifications) == 2
        assert {row.user_id for row in notifications} == global_recipients
        all_recipients = set(
            (await administrator.scalars(select(Notification.user_id))).all()
        )
        assert all_recipients == global_recipients
        requests = list(
            (
                await administrator.scalars(
                    select(StoredEvent).where(
                        StoredEvent.event_type == NotificationsRequested.EVENT_TYPE
                    )
                )
            ).all()
        )
        assert len(requests) == 1
        assert requests[0].metadata_ is None
        notification_ids = {str(row.id) for row in notifications}
        assert set(requests[0].payload["notification_ids"]) == notification_ids
        assert requests[0].processed_at is None
