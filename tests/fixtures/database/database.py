import os
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles

from app.core.database import Base, async_session, engine
from app.models import models


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kwargs):
    return "TEXT"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def prepare_database() -> AsyncIterator[None]:
    database_url = os.environ.get("DATABASE_URL", "")
    is_postgresql = database_url.startswith("postgresql")

    if is_postgresql:
        yield
        return

    # SQLite-specific cleanup and setup
    db_path = database_url.replace("sqlite+aiosqlite:///./", "")
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass

    # Clean up journal and WAL files
    for suffix in ("-journal", "-wal"):
        path = f"{db_path}{suffix}"
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    # Tables with composite PKs or PostgreSQL-specific features
    # We exclude them from create_all and create them separately
    # with SQLite-compatible schema
    excluded_tables = {
        models.DataAccessLog.__table__.name,
        models.Notification.__table__.name,
        models.NotificationDelivery.__table__.name,
        models.Event.__table__.name,
        models.EventAttendance.__table__.name,
        models.EventFile.__table__.name,
    }

    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA busy_timeout=5000")
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")

        # Create non-excluded tables
        def _create_non_excluded(connection):
            for table in Base.metadata.sorted_tables:
                if table.name not in excluded_tables:
                    table.create(connection, checkfirst=True)

        await conn.run_sync(_create_non_excluded)

        # Create partitioned tables with modified schema for SQLite compatibility
        # DataAccessLog
        await conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS data_access_logs (
                id VARCHAR(36) PRIMARY KEY,
                actor_user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
                subject_user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
                resource_type VARCHAR(64) NOT NULL,
                resource_id VARCHAR(128),
                action VARCHAR(64) NOT NULL,
                context JSON,
                ip_address VARCHAR(64),
                user_agent VARCHAR(512),
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                signature VARCHAR(512)
            )
        """
        )

        # Notification
        await conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title VARCHAR NOT NULL,
                title_en VARCHAR,
                body TEXT,
                body_en TEXT,
                type VARCHAR,
                url VARCHAR,
                dedupe_key VARCHAR(255),
                read BOOLEAN DEFAULT 0,
                read_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_notifications_user_created ON "
            "notifications(user_id, created_at)"
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_notifications_dupe_check ON "
            "notifications(user_id, title, url, created_at)"
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_notifications_user_dedupe ON "
            "notifications(user_id, dedupe_key)"
        )

        # NotificationDelivery
        await conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS notification_deliveries (
                id VARCHAR(36) PRIMARY KEY,
                notification_id VARCHAR(36) NOT NULL,
                notification_created_at TIMESTAMP NOT NULL,
                channel VARCHAR NOT NULL DEFAULT 'inapp',
                status VARCHAR NOT NULL DEFAULT 'delivered',
                attempted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                delivered_at DATETIME,
                status_code INTEGER,
                detail TEXT,
                FOREIGN KEY (notification_id)
                REFERENCES notifications(id) ON DELETE CASCADE
            )
        """
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_notification_deliveries_notif_channel ON "
            "notification_deliveries(notification_id, channel)"
        )

        # Events table
        await conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS events (
                id VARCHAR(36) PRIMARY KEY,
                title VARCHAR NOT NULL,
                title_en VARCHAR,
                description TEXT,
                description_en TEXT,
                location VARCHAR,
                location_en VARCHAR,
                event_type VARCHAR,
                event_type_en VARCHAR,
                starts_at DATETIME NOT NULL,
                ends_at DATETIME NOT NULL,
                created_by VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                search_vector TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                speaker VARCHAR,
                image_url VARCHAR,
                about TEXT,
                about_en TEXT,
                embedding TEXT,
                CONSTRAINT ck_event_time_order CHECK (ends_at > starts_at)
            )
        """
        )
        for idx in ("starts_at", "ends_at", "event_type", "created_at", "is_active"):
            await conn.exec_driver_sql(
                f"CREATE INDEX IF NOT EXISTS ix_events_{idx} ON events({idx})"
            )

        # EventAttendance table
        await conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS event_attendance (
                id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                event_id VARCHAR(36) NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                qr_secret VARCHAR NOT NULL,
                qr_hmac VARCHAR NOT NULL,
                UNIQUE (user_id, event_id)
            )
        """
        )
        for idx in ("user_id", "event_id", "registered_at"):
            await conn.exec_driver_sql(
                f"CREATE INDEX IF NOT EXISTS ix_event_attendance_{idx} ON "
                f"event_attendance({idx})"
            )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_event_attendance_event_user ON "
            "event_attendance(event_id, user_id)"
        )

        # EventFile table
        await conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS event_files (
                id VARCHAR(36) PRIMARY KEY,
                event_id VARCHAR(36) NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                file_url VARCHAR NOT NULL,
                description VARCHAR
            )
        """
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_event_files_event_id ON "
            "event_files(event_id)"
        )

    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Get a fresh database session for each test."""
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(autouse=True)
async def clean_database(prepare_database: None) -> AsyncIterator[None]:
    """
    Clean up tables between tests to ensure isolation.
    Uses TRUNCATE on PostgreSQL or DELETE on SQLite.
    """
    import asyncio
    import logging

    from sqlalchemy.exc import OperationalError

    from app.services import notification_queue

    # Clear wait queue before test
    await notification_queue.reset_testing_state()
    yield

    database_url = os.environ.get("DATABASE_URL", "")
    is_postgresql = engine.dialect.name == "postgresql" or database_url.startswith(
        "postgresql"
    )

    attempts = 5
    delay = 0.1
    for attempt in range(1, attempts + 1):
        try:
            async with engine.begin() as conn:
                if is_postgresql:
                    table_names = [
                        f'"{table.name}"' for table in Base.metadata.sorted_tables
                    ]
                    if table_names:
                        await conn.exec_driver_sql(
                            f"TRUNCATE TABLE {', '.join(table_names)} CASCADE"
                        )
                else:
                    await conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
                    for table in reversed(Base.metadata.sorted_tables):
                        try:
                            await conn.execute(table.delete())
                        except Exception:
                            pass
                    await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            break
        except OperationalError as exc:
            if "database is locked" not in str(exc).lower() or attempt == attempts:
                raise
            logging.warning(
                "SQLite database locked during test cleanup, retrying in %.1fs "
                "(attempt %d/%d)",
                delay,
                attempt,
                attempts,
            )
            await asyncio.sleep(delay)
            delay *= 2
        except RuntimeError as exc:
            error_message = str(exc).lower()
            if (
                "event loop is closed" in error_message
                or "handler is closed" in error_message
            ):
                logging.debug("Skipping database cleanup: event loop already closed")
                break
            raise
