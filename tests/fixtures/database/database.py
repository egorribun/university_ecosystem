import contextlib
import os
import warnings
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles

from app.core import database
from app.core.database import Base, init_database


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kwargs):
    return "TEXT"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def prepare_database() -> AsyncIterator[None]:
    init_database()
    database_url = os.environ.get("DATABASE_URL", "")
    is_postgresql = database_url.startswith("postgresql")

    if is_postgresql:
        # Safety-net: unconditionally ensure DEFAULT + prev/current/next-month
        # RANGE partitions exist for all partitioned tables.  Using
        # CREATE TABLE IF NOT EXISTS makes every statement idempotent.
        # We skip the relkind pre-check: if the table is not partitioned or
        # does not exist the statement will fail; we suppress that error so
        # other tables are still processed.
        from datetime import UTC, datetime, timedelta

        import sqlalchemy as sa

        _PARTITIONED_TABLES = [
            "data_access_logs",
            "notifications",
            "notification_deliveries",
            "failed_login_attempts",
        ]

        now = datetime.now(UTC)
        # Cover the previous, current, and next calendar month to handle
        # tests that use timestamps near month boundaries.
        months = [
            now - timedelta(days=32),  # prev month
            now,  # current month
            now + timedelta(days=32),  # next month
        ]

        async with database.engine.execution_options(
            isolation_level="AUTOCOMMIT"
        ).connect() as conn:
            for tbl in _PARTITIONED_TABLES:
                # Only partition tables that are actually partitioned (relkind='p').
                rk_row = await conn.execute(
                    sa.text(
                        "SELECT c.relkind FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE c.relname = :t AND n.nspname = 'public'"
                    ),
                    {"t": tbl},
                )
                if rk_row.scalar() != "p":
                    continue  # table absent or not range-partitioned

                # DEFAULT partition — absorbs any out-of-range insert.
                await conn.execute(
                    sa.text(
                        f"CREATE TABLE IF NOT EXISTS {tbl}_default "
                        f"PARTITION OF {tbl} DEFAULT"
                    )
                )

                # Monthly range partitions covering prev, current, and next month.
                for m_dt in months:
                    start_of_month = m_dt.replace(
                        day=1,
                        hour=0,
                        minute=0,
                        second=0,
                        microsecond=0,
                        tzinfo=UTC,
                    )
                    next_month = (start_of_month + timedelta(days=32)).replace(
                        day=1,
                        hour=0,
                        minute=0,
                        second=0,
                        microsecond=0,
                        tzinfo=UTC,
                    )
                    suffix = start_of_month.strftime("%Y_%m")
                    part_name = f"{tbl}_{suffix}"
                    start_iso = start_of_month.strftime("%Y-%m-%d %H:%M:%S+00")
                    end_iso = next_month.strftime("%Y-%m-%d %H:%M:%S+00")
                    await conn.execute(
                        sa.text(
                            f"CREATE TABLE IF NOT EXISTS {part_name} "
                            f"PARTITION OF {tbl} "
                            f"FOR VALUES FROM ('{start_iso}') TO ('{end_iso}')"
                        )
                    )

        yield
        return

    # SQLite-specific cleanup and setup
    db_path = database_url.replace("sqlite+aiosqlite:///./", "")
    if os.path.exists(db_path):
        with contextlib.suppress(OSError):
            os.remove(db_path)

    # Clean up journal and WAL files
    for suffix in ("-journal", "-wal"):
        path = f"{db_path}{suffix}"
        if os.path.exists(path):
            with contextlib.suppress(OSError):
                os.remove(path)

    # Tables with composite PKs or PostgreSQL-specific features
    # We exclude them from create_all and create them separately
    # with SQLite-compatible schema
    excluded_tables = {
        "data_access_logs",
        "notifications",
        "notification_deliveries",
        "events",
        "event_attendance",
        "event_files",
        "stored_events",
    }

    async with database.engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA busy_timeout=5000")
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")

        # Create non-excluded tables
        def _create_non_excluded(connection):
            for table in Base.metadata.sorted_tables:
                if table.name not in excluded_tables:
                    try:
                        table.create(connection, checkfirst=True)
                    except Exception as e:
                        # Log and continue - some tables might have Postgres-only features
                        # like Computed columns with to_tsvector
                        warnings.warn(
                            f"Table creation failed for {table.name}: {e}", stacklevel=1
                        )

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
                id VARCHAR(36) NOT NULL,
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
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id, created_at)
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
                id VARCHAR(36) NOT NULL,
                notification_id VARCHAR(36) NOT NULL,
                notification_created_at TIMESTAMP NOT NULL,
                channel VARCHAR NOT NULL DEFAULT 'inapp',
                subscription_id VARCHAR(36),
                status VARCHAR NOT NULL DEFAULT 'delivered',
                attempted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                delivered_at DATETIME,
                status_code INTEGER,
                detail TEXT,
                UNIQUE (notification_id, channel, subscription_id),
                PRIMARY KEY (id, attempted_at),
                FOREIGN KEY (notification_id, notification_created_at)
                REFERENCES notifications(id, created_at) ON DELETE CASCADE
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
        # StoredEvent table
        await conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS stored_events (
                id VARCHAR(36) PRIMARY KEY,
                event_type VARCHAR(100) NOT NULL,
                aggregate_type VARCHAR(50) NOT NULL,
                aggregate_id VARCHAR(100) NOT NULL,
                payload JSON NOT NULL,
                metadata JSON,
                version INTEGER NOT NULL DEFAULT 1,
                subject VARCHAR(255),
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                trace_context JSON,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                processed_at DATETIME,
                error_count INTEGER NOT NULL DEFAULT 0,
                last_error VARCHAR,
                aggregate_id_uuid UUID,
                sequence_number BIGINT
            )
        """
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_stored_events_event_type ON stored_events(event_type)"
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_stored_events_status ON stored_events(status)"
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_stored_events_pending ON stored_events(status, created_at)"
        )

    yield
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Get a fresh database session for each test."""
    async with database.async_session() as session:
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
    is_postgresql = (
        database.engine.dialect.name == "postgresql"
        or database_url.startswith("postgresql")
    )

    attempts = 5
    delay = 0.1
    for attempt in range(1, attempts + 1):
        try:
            async with database.engine.begin() as conn:
                if is_postgresql:
                    # Get existing tables to avoid UndefinedTableError
                    result = await conn.exec_driver_sql(
                        "SELECT tablename FROM pg_catalog.pg_tables "
                        "WHERE schemaname = 'public'"
                    )
                    existing_tables = {row[0] for row in result.all()}

                    table_names = [
                        f'"{table.name}"'
                        for table in Base.metadata.sorted_tables
                        if table.name in existing_tables
                    ]
                    if table_names:
                        await conn.exec_driver_sql(
                            f"TRUNCATE TABLE {', '.join(table_names)} CASCADE"
                        )
                else:
                    await conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
                    for table in reversed(Base.metadata.sorted_tables):
                        with contextlib.suppress(Exception):
                            await conn.execute(table.delete())
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
        except (RuntimeError, ValueError) as exc:
            # "different loop" is an asyncio *ValueError* (tasks.py ensure_future),
            # NOT a RuntimeError — include ValueError or it escapes the swallow.
            # The message guard below re-raises every other ValueError. Defense-in-
            # depth for mutmut's multi-pytest.main() teardown (the periodic_scheduler
            # daemon — the primary leaker — is gated out of "testing" in lifespan.py).
            error_message = str(exc).lower()
            if (
                "event loop is closed" in error_message
                or "handler is closed" in error_message
                or "different loop" in error_message
            ):
                logging.debug(
                    "Skipping database cleanup: event loop mismatch or closed"
                )
                break
            raise
