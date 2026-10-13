"""Semantic PostgreSQL checks for two legacy Alembic revisions.

Downgrade assertions here describe historical schema compatibility only. The
owner-approved release barrier does not support production rollback below
202608250001/2; these isolated checks are not a rollback guarantee.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
import yaml
from alembic.migration import MigrationContext
from alembic.operations import Operations
from testcontainers.community.postgres import PostgresContainer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRUSTED_DEVICES_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "db31ef5d7ea4_add_trusted_devices.py"
)
PARTITIONING_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "6a898bba5589_implement_partitioning.py"
)
_RUN = os.getenv("RUN_INTEGRATION_TESTS") == "1"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]


def _load_migration(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _pinned_postgres_image() -> str:
    """Read the test database's immutable image pin from the Compose source."""
    compose = yaml.safe_load(
        (PROJECT_ROOT / "docker-compose.test.yml").read_text(encoding="utf-8")
    )
    image = compose["services"]["postgres"]["image"]
    if (
        not isinstance(image, str)
        or re.fullmatch(r"pgvector/pgvector:pg17@sha256:[0-9a-f]{64}", image) is None
    ):
        raise ValueError("docker-compose.test.yml must pin pgvector/pg17 by SHA-256")
    return image


@pytest.fixture(scope="module")
def postgres_engine():
    """Use the audited, digest-pinned PostgreSQL 17 test image and resource cap."""
    run_id = uuid4().hex
    with PostgresContainer(
        _pinned_postgres_image(),
        name=f"ue-historical-migrations-pg17-{run_id}",
        labels={
            "university-ecosystem.dev/test-owner": f"historical-migrations-{run_id}",
            "university-ecosystem.dev/test-purpose": "historical-migration-semantics",
        },
        mem_limit=1024**3,
        memswap_limit=1024**3,
        nano_cpus=2_000_000_000,
    ) as postgres:
        engine = sa.create_engine(postgres.get_connection_url(driver="psycopg"))
        try:
            yield engine
        finally:
            engine.dispose()


@contextmanager
def _isolated_schema(engine: sa.Engine) -> Iterator[sa.Connection]:
    """Run each revision against a private schema in one rollback-safe transaction."""
    schema = f"historic_{uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(sa.text("SET LOCAL TIME ZONE 'UTC'"))
        connection.execute(
            sa.text("SELECT set_config('search_path', :schema, true)"),
            {"schema": schema},
        )
        try:
            yield connection
        finally:
            connection.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))


def _run_revision(migration, connection: sa.Connection, operation: str) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        getattr(migration, operation)()


def _columns(connection: sa.Connection, table: str) -> dict[str, dict]:
    return {
        column["name"]: column for column in sa.inspect(connection).get_columns(table)
    }


def _indexes(connection: sa.Connection, table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(connection).get_indexes(table)}


def _is_timezone_aware(connection: sa.Connection, table: str, column: str) -> bool:
    return bool(getattr(_columns(connection, table)[column]["type"], "timezone", False))


def _fk_delete_action(connection: sa.Connection, table: str, constraint: str) -> str:
    return connection.execute(
        sa.text(
            "SELECT confdeltype::text FROM pg_constraint "
            "WHERE conrelid = to_regclass(:table_name) AND conname = :constraint_name"
        ),
        {"table_name": table, "constraint_name": constraint},
    ).scalar_one()


def _relation_kind(connection: sa.Connection, table: str) -> str:
    return connection.execute(
        sa.text(
            "SELECT relation.relkind::text FROM pg_class AS relation "
            "JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace "
            "WHERE namespace.nspname = current_schema() AND relation.relname = :name"
        ),
        {"name": table},
    ).scalar_one()


def _count(connection: sa.Connection, table: str) -> int:
    statement = sa.select(sa.func.count()).select_from(sa.table(table))
    return int(connection.execute(statement).scalar_one())


def _create_trusted_devices_legacy_schema(connection: sa.Connection) -> None:
    statements = (
        "CREATE TABLE users (id integer PRIMARY KEY, email text NOT NULL, "
        "spotify_token_expires_at timestamp without time zone, "
        "spotify_last_checked_at timestamp without time zone)",
        "CREATE UNIQUE INDEX ux_users_lower_email ON users (lower(email::text))",
        "CREATE TABLE active_sessions (id integer PRIMARY KEY, jti text NOT NULL, "
        "CONSTRAINT uq_active_sessions_jti UNIQUE (jti))",
        "CREATE TABLE events (id integer PRIMARY KEY, "
        "starts_at timestamp without time zone NOT NULL, "
        "ends_at timestamp without time zone NOT NULL, "
        "created_at timestamp without time zone DEFAULT now(), search_vector tsvector)",
        "CREATE INDEX ix_events_search_vector ON events USING gin (search_vector)",
        "CREATE TABLE event_attendance (id integer PRIMARY KEY, "
        "registered_at timestamp without time zone)",
        "CREATE TABLE invite_codes (id integer PRIMARY KEY, "
        "created_at timestamp without time zone)",
        "CREATE TABLE mfa_challenges (id integer PRIMARY KEY, session_id text)",
        "CREATE INDEX ix_mfa_challenges_session_id ON mfa_challenges (session_id)",
        "CREATE TABLE news (id integer PRIMARY KEY, "
        "created_at timestamp without time zone DEFAULT now())",
        "CREATE INDEX ix_news_published_at_desc ON news (created_at DESC)",
        "CREATE TABLE notifications (id integer PRIMARY KEY, dedupe_key varchar(255), "
        "created_at timestamp without time zone, read_at timestamp without time zone)",
        "CREATE TABLE notification_deliveries (id integer PRIMARY KEY, "
        "delivered_at timestamp without time zone)",
        "CREATE TABLE password_reset_tokens (id integer PRIMARY KEY, "
        "expires_at timestamp without time zone NOT NULL, "
        "created_at timestamp without time zone)",
        "CREATE TABLE push_subscriptions (id integer PRIMARY KEY, user_id integer, "
        "created_at timestamp without time zone, "
        "last_seen_at timestamp without time zone, "
        "active boolean, updated_at timestamp without time zone, "
        "CONSTRAINT push_subscriptions_user_id_fkey FOREIGN KEY (user_id) "
        "REFERENCES users(id) ON DELETE SET NULL)",
        "CREATE INDEX ix_push_subscriptions_active ON push_subscriptions (active)",
        "CREATE INDEX ix_push_subscriptions_updated_at "
        "ON push_subscriptions (updated_at)",
        "CREATE TABLE schedule (id integer PRIMARY KEY, group_id integer NOT NULL, "
        "parity integer NOT NULL, start_time timestamp without time zone NOT NULL, "
        "end_time timestamp without time zone NOT NULL)",
        "CREATE INDEX ix_schedule_group_week_parity_date "
        "ON schedule (group_id, parity, start_time)",
        "CREATE TABLE user_push_topics (id integer PRIMARY KEY, "
        "user_id integer NOT NULL, "
        "updated_at timestamp without time zone)",
        "CREATE INDEX ix_user_push_topics_updated_at ON user_push_topics (updated_at)",
    )
    for statement in statements:
        connection.execute(sa.text(statement))

    inserts = (
        "INSERT INTO users VALUES (1, 'student@example.edu', "
        "'2025-10-12 08:00:00', '2025-10-12 09:00:00')",
        "INSERT INTO active_sessions VALUES (1, 'jti-1')",
        "INSERT INTO events VALUES (1, '2025-10-12 10:00:00', "
        "'2025-10-12 11:00:00', '2025-10-12 09:00:00', NULL)",
        "INSERT INTO event_attendance VALUES (1, '2025-10-12 09:30:00')",
        "INSERT INTO invite_codes VALUES (1, '2025-10-12 08:30:00')",
        "INSERT INTO mfa_challenges VALUES (1, 'session-1')",
        "INSERT INTO news VALUES (1, '2025-10-12 07:00:00')",
        "INSERT INTO notifications VALUES (1, 'dedupe-1', '2025-10-12 06:00:00', "
        "'2025-10-12 06:30:00')",
        "INSERT INTO notification_deliveries VALUES (1, '2025-10-12 06:45:00')",
        "INSERT INTO password_reset_tokens VALUES (1, '2025-10-13 08:00:00', "
        "'2025-10-12 08:00:00')",
        "INSERT INTO push_subscriptions VALUES (1, 1, '2025-10-12 07:00:00', "
        "'2025-10-12 07:30:00', true, '2025-10-12 07:45:00')",
        "INSERT INTO schedule VALUES (1, 10, 1, '2025-10-12 09:00:00', "
        "'2025-10-12 10:00:00')",
        "INSERT INTO user_push_topics VALUES (1, 1, '2025-10-12 08:00:00')",
    )
    for statement in inserts:
        connection.execute(sa.text(statement))


def test_trusted_devices_gate_skips_when_event_attendance_is_absent(
    postgres_engine: sa.Engine,
) -> None:
    migration = _load_migration(TRUSTED_DEVICES_PATH, "historic_trusted_devices_gate")
    with _isolated_schema(postgres_engine) as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE users (id integer PRIMARY KEY, email text NOT NULL, "
                "spotify_token_expires_at timestamp without time zone, "
                "spotify_last_checked_at timestamp without time zone)"
            )
        )
        connection.execute(
            sa.text(
                "CREATE UNIQUE INDEX ux_users_lower_email ON users (lower(email::text))"
            )
        )
        connection.execute(
            sa.text("INSERT INTO users VALUES (1, 'fresh@example.edu', NULL, NULL)")
        )

        _run_revision(migration, connection, "upgrade")

        assert not _is_timezone_aware(connection, "users", "spotify_token_expires_at")
        assert "ux_users_lower_email" in _indexes(connection, "users")
        assert (
            connection.execute(sa.text("SELECT count(*) FROM users")).scalar_one() == 1
        )


def test_trusted_devices_upgrade_idempotence_and_historical_downgrade(
    postgres_engine: sa.Engine,
) -> None:
    migration = _load_migration(TRUSTED_DEVICES_PATH, "historic_trusted_devices_data")
    with _isolated_schema(postgres_engine) as connection:
        _create_trusted_devices_legacy_schema(connection)
        _run_revision(migration, connection, "upgrade")

        for table, column in (
            ("users", "spotify_token_expires_at"),
            ("users", "spotify_last_checked_at"),
            ("events", "starts_at"),
            ("events", "ends_at"),
            ("events", "created_at"),
            ("event_attendance", "registered_at"),
            ("invite_codes", "created_at"),
            ("news", "created_at"),
            ("notifications", "created_at"),
            ("notifications", "read_at"),
            ("notification_deliveries", "delivered_at"),
            ("password_reset_tokens", "expires_at"),
            ("password_reset_tokens", "created_at"),
            ("push_subscriptions", "created_at"),
            ("schedule", "start_time"),
            ("schedule", "end_time"),
        ):
            assert _is_timezone_aware(connection, table, column), (table, column)

        push_columns = _columns(connection, "push_subscriptions")
        assert push_columns["user_id"]["nullable"] is False
        assert "active" not in push_columns and "updated_at" not in push_columns
        assert (
            _fk_delete_action(
                connection, "push_subscriptions", "push_subscriptions_user_id_fkey"
            )
            == "c"
        )
        assert _indexes(connection, "push_subscriptions") == {
            "ix_push_subscriptions_last_seen_at"
        }
        assert "ix_notifications_dedupe_key" in _indexes(connection, "notifications")
        delivery_columns = _columns(connection, "notification_deliveries")
        assert {"status_code", "detail"} <= set(delivery_columns)
        assert all(
            delivery_columns[column]["nullable"] for column in ("status_code", "detail")
        )
        assert "ux_users_lower_email" not in _indexes(connection, "users")
        assert "uq_active_sessions_jti" not in {
            constraint["name"]
            for constraint in sa.inspect(connection).get_unique_constraints(
                "active_sessions"
            )
        }

        expected_push = connection.execute(
            sa.text(
                "SELECT user_id, created_at, last_seen_at "
                "FROM push_subscriptions WHERE id = 1"
            )
        ).one()
        assert expected_push.user_id == 1
        assert expected_push.created_at.isoformat() == "2025-10-12T07:00:00+00:00"
        # This revision changes created_at; the legacy last_seen_at type is retained.
        assert not _is_timezone_aware(connection, "push_subscriptions", "last_seen_at")
        assert expected_push.last_seen_at.isoformat() == "2025-10-12T07:30:00"
        assert (
            connection.execute(sa.text("SELECT starts_at FROM events WHERE id = 1"))
            .scalar_one()
            .isoformat()
            == "2025-10-12T10:00:00+00:00"
        )

        expected_counts = {
            table: _count(connection, table)
            for table in (
                "users",
                "active_sessions",
                "events",
                "event_attendance",
                "invite_codes",
                "mfa_challenges",
                "news",
                "notifications",
                "notification_deliveries",
                "password_reset_tokens",
                "push_subscriptions",
                "schedule",
                "user_push_topics",
            )
        }
        _run_revision(migration, connection, "upgrade")
        assert expected_counts == {
            table: _count(connection, table) for table in expected_counts
        }
        assert _indexes(connection, "push_subscriptions") == {
            "ix_push_subscriptions_last_seen_at"
        }
        assert (
            _fk_delete_action(
                connection, "push_subscriptions", "push_subscriptions_user_id_fkey"
            )
            == "c"
        )
        assert (
            connection.execute(
                sa.text(
                    "SELECT user_id, created_at, last_seen_at "
                    "FROM push_subscriptions WHERE id = 1"
                )
            ).one()
            == expected_push
        )

        # Historical-only check: removed values cannot be reconstructed.
        _run_revision(migration, connection, "downgrade")
        restored_push_columns = _columns(connection, "push_subscriptions")
        assert {"active", "updated_at"} <= set(restored_push_columns)
        assert (
            _fk_delete_action(
                connection, "push_subscriptions", "push_subscriptions_user_id_fkey"
            )
            == "n"
        )
        assert "ix_push_subscriptions_active" in _indexes(
            connection, "push_subscriptions"
        )
        assert "ix_push_subscriptions_updated_at" in _indexes(
            connection, "push_subscriptions"
        )
        assert not _is_timezone_aware(connection, "push_subscriptions", "created_at")
        restored = connection.execute(
            sa.text(
                "SELECT user_id, created_at, active, updated_at "
                "FROM push_subscriptions WHERE id = 1"
            )
        ).one()
        assert restored.user_id == 1
        assert restored.created_at.isoformat() == "2025-10-12T07:00:00"
        assert restored.active is None and restored.updated_at is None
        assert "ux_users_lower_email" in _indexes(connection, "users")
        assert "ix_notifications_dedupe_key" not in _indexes(
            connection, "notifications"
        )
        assert {"status_code", "detail"}.isdisjoint(
            _columns(connection, "notification_deliveries")
        )


def test_trusted_devices_missing_users_failure_rolls_back_partial_ddl(
    postgres_engine: sa.Engine,
) -> None:
    migration = _load_migration(
        TRUSTED_DEVICES_PATH, "historic_trusted_devices_dependency"
    )
    with _isolated_schema(postgres_engine) as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE event_attendance (id integer PRIMARY KEY, "
                "registered_at timestamp without time zone)"
            )
        )
        connection.execute(
            sa.text(
                "CREATE TABLE push_subscriptions (id integer PRIMARY KEY, "
                "user_id integer, created_at timestamp without time zone NOT NULL, "
                "last_seen_at timestamp without time zone)"
            )
        )
        connection.execute(
            sa.text("INSERT INTO event_attendance VALUES (1, '2025-10-12 09:30:00')")
        )
        connection.execute(
            sa.text(
                "INSERT INTO push_subscriptions VALUES "
                "(1, 1, '2025-10-12 07:00:00', NULL)"
            )
        )

        try:
            with connection.begin_nested():
                _run_revision(migration, connection, "upgrade")
        except sa.exc.NoReferencedTableError:
            pass
        except sa.exc.DBAPIError as error:
            sqlstate = getattr(error.orig, "sqlstate", None) or getattr(
                error.orig, "pgcode", None
            )
            assert sqlstate == "42P01"
        else:
            pytest.fail("upgrade unexpectedly created a user foreign key without users")

        assert not _is_timezone_aware(connection, "event_attendance", "registered_at")
        assert not _is_timezone_aware(connection, "push_subscriptions", "created_at")
        assert "ix_push_subscriptions_last_seen_at" not in _indexes(
            connection, "push_subscriptions"
        )
        assert _columns(connection, "push_subscriptions")["user_id"]["nullable"]
        assert (
            connection.execute(
                sa.text("SELECT created_at FROM push_subscriptions WHERE id = 1")
            )
            .scalar_one()
            .isoformat()
            == "2025-10-12T07:00:00"
        )


def test_partitioning_gate_leaves_legacy_logs_alone_without_notifications(
    postgres_engine: sa.Engine,
) -> None:
    migration = _load_migration(PARTITIONING_PATH, "historic_partitioning_gate")
    with _isolated_schema(postgres_engine) as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE data_access_logs (id integer PRIMARY KEY, "
                "resource_type varchar(64) NOT NULL, action varchar(64) NOT NULL, "
                "created_at timestamptz NOT NULL)"
            )
        )
        connection.execute(
            sa.text("INSERT INTO data_access_logs VALUES (1, 'course', 'read', now())")
        )

        _run_revision(migration, connection, "upgrade")

        assert _relation_kind(connection, "data_access_logs") == "r"
        assert connection.execute(
            sa.text("SELECT resource_type, action FROM data_access_logs WHERE id = 1")
        ).one() == ("course", "read")


def _create_partitioning_legacy_schema(connection: sa.Connection) -> None:
    statements = (
        "CREATE TABLE users (id integer PRIMARY KEY)",
        "CREATE TABLE data_access_logs (id integer PRIMARY KEY, "
        "actor_user_id integer REFERENCES users(id) ON DELETE SET NULL, "
        "subject_user_id integer REFERENCES users(id) ON DELETE SET NULL, "
        "resource_type varchar(64) NOT NULL, resource_id varchar(128), "
        "action varchar(64) NOT NULL, context json, ip_address varchar(64), "
        "user_agent varchar(512), created_at timestamptz NOT NULL DEFAULT now(), "
        "signature varchar(512))",
        "CREATE TABLE notifications (id integer PRIMARY KEY, "
        "user_id integer NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
        "title varchar NOT NULL, title_en varchar, body text, body_en text, "
        "type varchar, url varchar, dedupe_key varchar(255), "
        "created_at timestamptz NOT NULL DEFAULT now(), read boolean DEFAULT false, "
        "read_at timestamptz)",
        "CREATE TABLE notification_deliveries (id integer PRIMARY KEY, "
        "notification_id integer NOT NULL "
        "REFERENCES notifications(id) ON DELETE CASCADE, "
        "channel varchar NOT NULL DEFAULT 'inapp', "
        "status varchar NOT NULL DEFAULT 'delivered', "
        "attempted_at timestamptz NOT NULL DEFAULT now(), delivered_at timestamptz, "
        "status_code integer, detail text)",
    )
    for statement in statements:
        connection.execute(sa.text(statement))
    connection.execute(sa.text("INSERT INTO users VALUES (7)"))
    connection.execute(
        sa.text(
            "INSERT INTO data_access_logs (id, actor_user_id, subject_user_id, "
            "resource_type, resource_id, action, context, ip_address, user_agent, "
            "created_at, signature) VALUES (51, 7, 7, 'course', 'CS101', 'read', "
            "'{\"source\":\"test\"}', '192.0.2.10', 'migration-test', "
            "'2025-10-12 08:00:00+00', 'sig-51')"
        )
    )
    connection.execute(
        sa.text(
            "INSERT INTO notifications (id, user_id, title, title_en, body, body_en, "
            "type, url, dedupe_key, created_at, read, read_at) VALUES "
            "(101, 7, 'Notice', 'Notice EN', 'Body', 'Body EN', 'event', '/events/1', "
            "'notice-101', '2025-10-12 09:00:00+00', true, '2025-10-12 09:30:00+00')"
        )
    )
    connection.execute(
        sa.text(
            "INSERT INTO notification_deliveries "
            "(id, notification_id, channel, status, "
            "attempted_at, delivered_at, status_code, detail) VALUES "
            "(201, 101, 'email', 'delivered', '2025-10-12 09:01:00+00', "
            "'2025-10-12 09:02:00+00', 202, 'accepted')"
        )
    )


def test_partitioning_missing_users_failure_rolls_back_renames(
    postgres_engine: sa.Engine,
) -> None:
    migration = _load_migration(PARTITIONING_PATH, "historic_partitioning_dependency")
    with _isolated_schema(postgres_engine) as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE notifications (id integer PRIMARY KEY, "
                "user_id integer NOT NULL, "
                "title varchar NOT NULL, created_at timestamptz NOT NULL DEFAULT now())"
            )
        )
        connection.execute(
            sa.text("INSERT INTO notifications VALUES (1, 1, 'orphan schema', now())")
        )

        try:
            with connection.begin_nested():
                _run_revision(migration, connection, "upgrade")
        except sa.exc.DBAPIError as error:
            sqlstate = getattr(error.orig, "sqlstate", None) or getattr(
                error.orig, "pgcode", None
            )
            assert sqlstate == "42P01"
        else:
            pytest.fail("partitioning unexpectedly created notifications without users")

        assert _relation_kind(connection, "notifications") == "r"
        assert connection.execute(
            sa.text("SELECT id, user_id, title FROM notifications")
        ).one() == (1, 1, "orphan schema")
        assert sa.inspect(connection).has_table("notifications_old") is False


def test_partitioning_copies_populated_rows_is_idempotent_and_historically_downgrades(
    postgres_engine: sa.Engine,
) -> None:
    migration = _load_migration(PARTITIONING_PATH, "historic_partitioning_data")
    with _isolated_schema(postgres_engine) as connection:
        _create_partitioning_legacy_schema(connection)

        _run_revision(migration, connection, "upgrade")

        for table in ("notifications", "notification_deliveries", "data_access_logs"):
            assert _relation_kind(connection, table) == "p"
            assert connection.execute(
                sa.text(
                    "SELECT EXISTS (SELECT 1 FROM pg_inherits "
                    "JOIN pg_class parent ON parent.oid = inhparent "
                    "JOIN pg_class child ON child.oid = inhrelid "
                    "WHERE parent.oid = to_regclass(:parent) AND child.relispartition)"
                ),
                {"parent": table},
            ).scalar_one()
        assert _count(connection, "notifications") == 1
        assert _count(connection, "notification_deliveries") == 1
        assert _count(connection, "data_access_logs") == 1
        assert sa.inspect(connection).has_table("notifications_old") is False
        assert sa.inspect(connection).has_table("notification_deliveries_old") is False
        delivery = connection.execute(
            sa.text(
                "SELECT notification_id, notification_created_at, channel, status, "
                "status_code, detail FROM notification_deliveries"
            )
        ).one()
        assert delivery.notification_id == 101
        assert (
            delivery.channel,
            delivery.status,
            delivery.status_code,
            delivery.detail,
        ) == ("email", "delivered", 202, "accepted")
        assert (
            delivery.notification_created_at.isoformat() == "2025-10-12T09:00:00+00:00"
        )
        copied_log = connection.execute(
            sa.text(
                "SELECT actor_user_id, resource_id, action, signature "
                "FROM data_access_logs"
            )
        ).one()
        assert copied_log == (7, "CS101", "read", "sig-51")

        _run_revision(migration, connection, "upgrade")
        assert _relation_kind(connection, "notifications") == "p"
        assert _count(connection, "notifications") == 1
        assert _count(connection, "notification_deliveries") == 1
        assert _count(connection, "data_access_logs") == 1

        # Historical-only check; release rollback below this barrier is unsupported.
        _run_revision(migration, connection, "downgrade")
        for table in ("notifications", "notification_deliveries", "data_access_logs"):
            assert _relation_kind(connection, table) == "r"
        assert _count(connection, "notifications") == 1
        assert _count(connection, "notification_deliveries") == 1
        assert _count(connection, "data_access_logs") == 1
        assert sa.inspect(connection).has_table("notifications_part") is False
        assert sa.inspect(connection).has_table("notification_deliveries_part") is False
        assert sa.inspect(connection).has_table("data_access_logs_part") is False
        notification = connection.execute(
            sa.text("SELECT id, user_id, title, dedupe_key, read FROM notifications")
        ).one()
        assert notification == (101, 7, "Notice", "notice-101", True)
        restored_delivery = connection.execute(
            sa.text(
                "SELECT id, notification_id, channel, status, status_code, detail "
                "FROM notification_deliveries"
            )
        ).one()
        assert restored_delivery == (201, 101, "email", "delivered", 202, "accepted")
        restored_log = connection.execute(
            sa.text(
                "SELECT id, actor_user_id, resource_type, resource_id, action "
                "FROM data_access_logs"
            )
        ).one()
        assert restored_log == (51, 7, "course", "CS101", "read")
