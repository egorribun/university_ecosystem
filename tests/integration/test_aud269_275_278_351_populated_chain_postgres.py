"""PostgreSQL populated-chain proofs for AUD-269, AUD-270, AUD-275, AUD-278 and AUD-351.

Each scenario creates a private database, stops at the revision before the one
under test, seeds rows with the columns that exist there, then runs the real
revision. Assertions read the PostgreSQL catalog after the upgrade, so they test
what a deployment would keep rather than the SQL text the revision generates.
"""

from __future__ import annotations

import importlib.util
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
import sqlalchemy as sa
import yaml
from alembic.config import Config
from psycopg import sql
from sqlalchemy.engine import make_url
from testcontainers.community.postgres import PostgresContainer

from alembic import command

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_RUN = bool(os.getenv("RUN_INTEGRATION_TESTS"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]

# Reconciled hot-path indexes that revisions 202603060001 through 202603170001
# create and that no later revision replaces (AUD-269).
_HOT_PATH_INDEXES = (
    "ix_chat_participants_chat_id_user_id",
    "ix_chat_participants_user_id_chat_id",
    "ix_messages_unread_chat_sender",
    "ix_stored_events_pending_aggregate_created",
    "ix_stored_events_pending_created",
    "ix_stored_events_processed_at",
    "ix_stored_events_aggregate_uuid",
    "idx_news_comment_cursor",
    "idx_messages_chat_pagination_covering",
)


def _pinned_postgres_image() -> str:
    """Read the test database's immutable image pin from the Compose source."""
    compose = yaml.safe_load(
        (PROJECT_ROOT / "docker-compose.test.yml").read_text(encoding="utf-8")
    )
    image = compose["services"]["postgres"]["image"]
    if not isinstance(image, str) or not re.fullmatch(
        r"pgvector/pgvector:pg17@sha256:[0-9a-f]{64}", image
    ):
        raise ValueError("docker-compose.test.yml must pin pgvector/pg17 by SHA-256")
    return image


@pytest.fixture(scope="module")
def postgres_server():
    with PostgresContainer(_pinned_postgres_image()) as postgres:
        yield postgres


@dataclass(frozen=True)
class _Scenario:
    alembic_url: str
    sync_url: str
    config: Config


def _alembic_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture
def scenario(postgres_server, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Scenario]:
    """Give each populated-chain test a fresh database on the shared server."""
    base_url = make_url(postgres_server.get_connection_url())
    database_name = f"mig3a_{uuid4().hex}"
    admin_conninfo = base_url.set(
        database="postgres", drivername="postgresql"
    ).render_as_string(hide_password=False)
    identifier = sql.Identifier(database_name)
    created = False
    try:
        with psycopg.connect(admin_conninfo, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(identifier))
            created = True
            admin.execute(
                sql.SQL("ALTER DATABASE {} SET timezone TO 'UTC'").format(identifier)
            )
        scenario_url = base_url.set(
            database=database_name, drivername="postgresql+psycopg"
        )
        alembic_url = scenario_url.render_as_string(hide_password=False)
        monkeypatch.setenv("DATABASE_URL", alembic_url)
        yield _Scenario(
            alembic_url=alembic_url,
            sync_url=scenario_url.set(drivername="postgresql").render_as_string(
                hide_password=False
            ),
            config=_alembic_config(alembic_url),
        )
    finally:
        if created:
            with psycopg.connect(admin_conninfo, autocommit=True) as admin:
                admin.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                        identifier
                    )
                )


def _upgrade(scenario: _Scenario, revision: str) -> None:
    command.upgrade(scenario.config, revision)


# AUD-351: integer notification record ids are kept, dead-lettered and rekeyed.


def test_integer_record_ids_are_dead_lettered_and_kept_by_reconcile(
    scenario: _Scenario,
) -> None:
    _upgrade(scenario, "7ad848733a4b")
    legacy_id = uuid4()
    other_id = uuid4()
    already_dead_id = uuid4()
    with psycopg.connect(scenario.sync_url) as connection:
        connection.execute(
            "INSERT INTO notification_queue_jobs "
            "(id, kind, record_id, attempts) VALUES (%s, 'event', 7, 0), "
            "(%s, 'news', 8, 2)",
            (legacy_id, other_id),
        )
        connection.execute(
            "INSERT INTO notification_queue_jobs "
            "(id, kind, record_id, dead_lettered, last_error) "
            "VALUES (%s, 'news', 9, true, 'earlier failure')",
            (already_dead_id,),
        )
        connection.commit()

    _upgrade(scenario, "202603280001")

    with psycopg.connect(scenario.sync_url) as connection:
        column_type = connection.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'notification_queue_jobs' "
            "AND column_name = 'record_id'"
        ).fetchone()
        assert column_type == ("uuid",)
        rows = {
            row[0]: row[1:]
            for row in connection.execute(
                "SELECT id, record_id, dead_lettered, last_error "
                "FROM notification_queue_jobs"
            ).fetchall()
        }

    # Every job survives, and each integer id becomes its own UUID key.
    assert set(rows) == {legacy_id, other_id, already_dead_id}
    for job_id in (legacy_id, other_id):
        record_id, dead_lettered, last_error = rows[job_id]
        assert record_id == job_id
        assert dead_lettered is True
        assert "AUD-351" in last_error
    # Rows already dead-lettered keep their original error text unchanged.
    assert rows[already_dead_id] == (already_dead_id, True, "earlier failure")


# AUD-269: the hot-path indexes from the later revisions survive the reconcile.


def _all_index_names(connection: psycopg.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
    ).fetchall()
    return {row[0] for row in rows}


def test_hot_path_indexes_survive_reconcile_with_seeded_rows(
    scenario: _Scenario,
) -> None:
    _upgrade(scenario, "7ad848733a4b")
    seeded_title = "Populated reconcile"
    with psycopg.connect(scenario.sync_url) as connection:
        assert set(_HOT_PATH_INDEXES) <= _all_index_names(connection)
        connection.execute(
            "INSERT INTO events (id, title, starts_at, ends_at, is_active) "
            "VALUES (%s, %s, now(), now() + interval '1 hour', true)",
            (uuid4(), seeded_title),
        )
        connection.commit()

    _upgrade(scenario, "202603280001")

    with psycopg.connect(scenario.sync_url) as connection:
        assert sorted(set(_HOT_PATH_INDEXES) - _all_index_names(connection)) == []
        titles = connection.execute("SELECT title FROM events").fetchall()
    assert titles == [(seeded_title,)]


# AUD-278: the event full-text index is present on fresh and populated upgrades.


def test_event_search_gin_index_is_restored_on_populated_upgrade(
    scenario: _Scenario,
) -> None:
    _upgrade(scenario, "7ad848733a4b")
    seeded_id = uuid4()
    with psycopg.connect(scenario.sync_url) as connection:
        connection.execute(
            "INSERT INTO events (id, title, starts_at, ends_at, is_active) "
            "VALUES (%s, 'Quartzcanyon seminar', now(), now() + interval '1 hour', true)",
            (seeded_id,),
        )
        connection.commit()

    _upgrade(scenario, "202603280001")

    with psycopg.connect(scenario.sync_url) as connection:
        definition = connection.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = "
            "'ix_events_search_vector'"
        ).fetchone()
        assert definition is not None
        assert "USING gin (search_vector)" in definition[0]
        valid = connection.execute(
            "SELECT i.indisvalid FROM pg_index i "
            "WHERE i.indexrelid = to_regclass('ix_events_search_vector')"
        ).fetchone()
        assert valid == (True,)
        matches = connection.execute(
            "SELECT id FROM events WHERE search_vector @@ "
            "to_tsquery('simple', 'quartzcanyon')"
        ).fetchall()
        assert matches == [(seeded_id,)]


def test_fresh_chain_head_has_event_search_gin_index(scenario: _Scenario) -> None:
    _upgrade(scenario, "head")

    with psycopg.connect(scenario.sync_url) as connection:
        definition = connection.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = "
            "'ix_events_search_vector'"
        ).fetchone()

    assert definition is not None
    assert "USING gin (search_vector)" in definition[0]


# AUD-275: the reply index is repaired after an interrupted concurrent build.


def _commit_reply_column_without_index(connection: psycopg.Connection) -> None:
    connection.execute(
        "ALTER TABLE messages ADD COLUMN reply_to_message_id uuid "
        "REFERENCES messages(id) ON DELETE SET NULL"
    )
    connection.execute(
        "CREATE INDEX ix_messages_reply_to_message_id ON messages (reply_to_message_id)"
    )


def test_fresh_upgrade_builds_reply_index_valid(scenario: _Scenario) -> None:
    _upgrade(scenario, "202605300004")

    with psycopg.connect(scenario.sync_url) as connection:
        valid = connection.execute(
            "SELECT i.indisvalid FROM pg_index i "
            "WHERE i.indexrelid = to_regclass('ix_messages_reply_to_message_id')"
        ).fetchone()
    assert valid == (True,)


def test_interrupted_reply_index_build_is_rebuilt_on_rerun(
    scenario: _Scenario,
) -> None:
    _upgrade(scenario, "202605300003")
    with psycopg.connect(scenario.sync_url) as connection:
        _commit_reply_column_without_index(connection)
        # Leave the catalog in the state a failed CONCURRENTLY build leaves behind.
        connection.execute(
            "UPDATE pg_index SET indisvalid = false WHERE indexrelid = "
            "to_regclass('ix_messages_reply_to_message_id')"
        )
        connection.commit()

    _upgrade(scenario, "202605300004")

    with psycopg.connect(scenario.sync_url) as connection:
        valid = connection.execute(
            "SELECT i.indisvalid FROM pg_index i "
            "WHERE i.indexrelid = to_regclass('ix_messages_reply_to_message_id')"
        ).fetchone()
        columns = connection.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'messages' AND column_name = 'reply_to_message_id'"
        ).fetchone()
    assert valid == (True,)
    assert columns == (1,)


def test_committed_reply_column_without_index_gets_its_index(
    scenario: _Scenario,
) -> None:
    _upgrade(scenario, "202605300003")
    with psycopg.connect(scenario.sync_url) as connection:
        connection.execute(
            "ALTER TABLE messages ADD COLUMN reply_to_message_id uuid "
            "REFERENCES messages(id) ON DELETE SET NULL"
        )
        connection.commit()

    _upgrade(scenario, "202605300004")

    with psycopg.connect(scenario.sync_url) as connection:
        valid = connection.execute(
            "SELECT i.indisvalid FROM pg_index i "
            "WHERE i.indexrelid = to_regclass('ix_messages_reply_to_message_id')"
        ).fetchone()
    assert valid == (True,)


# AUD-270: the cutover guard refuses to truncate a populated child (guard-level proof).


def _load_cutover_module():
    path = PROJECT_ROOT / "alembic" / "versions" / "202602010003_final_cutover_swap.py"
    spec = importlib.util.spec_from_file_location("mig3a_final_cutover", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cutover_guard_refuses_populated_child_and_keeps_every_row(
    scenario: _Scenario,
) -> None:
    with psycopg.connect(scenario.sync_url) as connection:
        connection.execute("CREATE TABLE mig3a_ref (id uuid PRIMARY KEY)")
        connection.execute("CREATE TABLE mig3a_child (id integer PRIMARY KEY)")
        connection.execute("CREATE TABLE mig3a_empty (id integer PRIMARY KEY)")
        connection.execute("INSERT INTO mig3a_child VALUES (1), (2)")
        connection.commit()
    module = _load_cutover_module()
    engine = sa.create_engine(scenario.alembic_url)
    try:
        with engine.begin() as connection:
            # A populated child cannot be mapped once its parent is migrated.
            with pytest.raises(RuntimeError, match="refusing to map or truncate"):
                module._refuse_unmappable_child(connection, "mig3a_child", "mig3a_ref")
            # An empty child needs no mapping and must not raise.
            module._refuse_unmappable_child(connection, "mig3a_empty", "mig3a_ref")
    finally:
        engine.dispose()

    with psycopg.connect(scenario.sync_url) as connection:
        rows = connection.execute("SELECT id FROM mig3a_child ORDER BY id").fetchall()
    assert rows == [(1,), (2,)]


_RECONCILE_PARENT = "7ad848733a4b"
_RECONCILE_REVISION = "202603280001"
_RECONCILE_GIN_CREATE = (
    "CREATE INDEX CONCURRENTLY ix_events_search_vector "
    "ON events USING gin (search_vector)"
)
_RECONCILE_GIN_DROP = "DROP INDEX CONCURRENTLY IF EXISTS ix_events_search_vector"
_RECONCILE_NAIVE_UTC = datetime(2026, 7, 1, 12, 34, 56, 123456)


class _InjectedGinBuildFailure(RuntimeError):
    pass


def _run_reconcile_probe(
    scenario: _Scenario, *, fail_gin_create: bool = False
) -> list[str]:
    """Run the real revision, optionally failing only its exact GIN CREATE."""
    observed: list[str] = []

    def observe_statement(
        _connection: sa.Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        normalized = " ".join(statement.split()).rstrip(";")
        if normalized == _RECONCILE_GIN_DROP:
            observed.append("drop")
        elif normalized == _RECONCILE_GIN_CREATE:
            observed.append("create")
            if fail_gin_create:
                raise _InjectedGinBuildFailure("injected GIN build failure")

    # Startup options set the session zone without autobegin before Alembic
    # configures ownership of the real transaction. This engine is test-owned.
    engine = sa.create_engine(
        scenario.alembic_url,
        connect_args={
            "connect_timeout": 10,
            "options": "-c timezone=America/Los_Angeles",
        },
    )
    try:
        with engine.connect() as connection:
            assert not connection.in_transaction()
            assert "connection" not in scenario.config.attributes
            sa.event.listen(connection, "before_cursor_execute", observe_statement)
            scenario.config.attributes["connection"] = connection
            try:
                if fail_gin_create:
                    with pytest.raises(
                        _InjectedGinBuildFailure, match="injected GIN build failure"
                    ):
                        command.upgrade(scenario.config, _RECONCILE_REVISION)
                    assert observed.count("create") == 1
                else:
                    command.upgrade(scenario.config, _RECONCILE_REVISION)
            finally:
                sa.event.remove(connection, "before_cursor_execute", observe_statement)
                removed = scenario.config.attributes.pop("connection")
                assert removed is connection
                assert not sa.event.contains(
                    connection, "before_cursor_execute", observe_statement
                )
            assert connection.execute(sa.text("SHOW TIME ZONE")).scalar_one() == (
                "America/Los_Angeles"
            )
            connection.rollback()
    finally:
        engine.dispose()
    return observed


def _event_search_index_catalog(connection: psycopg.Connection) -> tuple | None:
    return connection.execute(
        "SELECT index_class.oid, pg_get_indexdef(index_class.oid), "
        "index_state.indisvalid, index_state.indisready, access_method.amname, "
        "index_state.indisunique, index_state.indnkeyatts, index_state.indnatts, "
        "pg_get_expr(index_state.indpred, index_state.indrelid) "
        "FROM pg_index AS index_state "
        "JOIN pg_class AS index_class ON index_class.oid = index_state.indexrelid "
        "JOIN pg_am AS access_method ON access_method.oid = index_class.relam "
        "WHERE index_state.indexrelid = to_regclass('public.ix_events_search_vector') "
        "AND index_state.indrelid = to_regclass('public.events')"
    ).fetchone()


def test_reconcile_preserves_an_existing_valid_event_search_index(
    scenario: _Scenario,
) -> None:
    _upgrade(scenario, _RECONCILE_PARENT)
    event_id = uuid4()
    with psycopg.connect(scenario.sync_url) as connection:
        connection.execute(
            "INSERT INTO events (id, title, starts_at, ends_at, is_active) "
            "VALUES (%s, 'Quartzcanyon preservation', now(), "
            "now() + interval '1 hour', true)",
            (event_id,),
        )
        if _event_search_index_catalog(connection) is None:
            connection.execute(
                "CREATE INDEX ix_events_search_vector "
                "ON events USING gin (search_vector)"
            )
        before = _event_search_index_catalog(connection)
        assert before is not None
        assert isinstance(before[0], int) and before[0] > 0
        assert before[1] == (
            "CREATE INDEX ix_events_search_vector ON public.events "
            "USING gin (search_vector)"
        )
        assert before[2:] == (True, True, "gin", False, 1, 1, None)
        matches_before = connection.execute(
            "SELECT id FROM events WHERE search_vector @@ "
            "to_tsquery('simple', 'quartzcanyon')"
        ).fetchall()
        assert matches_before == [(event_id,)]
        connection.commit()

    observed = _run_reconcile_probe(scenario)

    with psycopg.connect(scenario.sync_url) as connection:
        after = _event_search_index_catalog(connection)
        matches_after = connection.execute(
            "SELECT id FROM events WHERE search_vector @@ "
            "to_tsquery('simple', 'quartzcanyon')"
        ).fetchall()
    # Equality includes the physical OID, not merely a recreated index name.
    assert after == before
    assert matches_after == matches_before
    assert observed == []


def _seed_reconcile_timestamp(scenario: _Scenario):
    _upgrade(scenario, _RECONCILE_PARENT)
    row_id = uuid4()
    with psycopg.connect(scenario.sync_url) as connection:
        column_type = connection.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'stored_events' "
            "AND column_name = 'created_at'"
        ).fetchone()
        assert column_type == ("timestamp without time zone",)
        connection.execute(
            "INSERT INTO stored_events "
            "(id, event_type, aggregate_type, aggregate_id, payload, "
            "version, created_at) "
            "VALUES (%s, 'gin-regression', 'fixture', 'gin-row', %s::json, 1, %s)",
            (row_id, '{"marker": "gin-retry"}', _RECONCILE_NAIVE_UTC),
        )
        connection.commit()
    return row_id


def _reconcile_timestamp_snapshot(scenario: _Scenario) -> tuple:
    with psycopg.connect(scenario.sync_url) as connection:
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchall()
        rows = connection.execute(
            "SELECT id, event_type, aggregate_type, aggregate_id, payload, "
            "version, created_at, pg_typeof(created_at)::text "
            "FROM stored_events ORDER BY id"
        ).fetchall()
    return revision, rows


def test_failed_event_search_build_does_not_commit_earlier_reconcile_changes(
    scenario: _Scenario,
) -> None:
    row_id = _seed_reconcile_timestamp(scenario)
    before = _reconcile_timestamp_snapshot(scenario)
    assert before == (
        [(_RECONCILE_PARENT,)],
        [
            (
                row_id,
                "gin-regression",
                "fixture",
                "gin-row",
                {"marker": "gin-retry"},
                1,
                _RECONCILE_NAIVE_UTC,
                "timestamp without time zone",
            )
        ],
    )

    _run_reconcile_probe(scenario, fail_gin_create=True)

    # A failed revision must not retain a predecessor stamp over converted data.
    assert _reconcile_timestamp_snapshot(scenario) == before


def test_retry_after_failed_event_search_build_preserves_utc_instant(
    scenario: _Scenario,
) -> None:
    row_id = _seed_reconcile_timestamp(scenario)
    _run_reconcile_probe(scenario, fail_gin_create=True)
    failed_revision, failed_rows = _reconcile_timestamp_snapshot(scenario)
    assert failed_revision == [(_RECONCILE_PARENT,)]
    assert len(failed_rows) == 1
    assert failed_rows[0][:6] == (
        row_id,
        "gin-regression",
        "fixture",
        "gin-row",
        {"marker": "gin-retry"},
        1,
    )

    _run_reconcile_probe(scenario)

    revision, rows = _reconcile_timestamp_snapshot(scenario)
    assert revision == [(_RECONCILE_REVISION,)]
    assert rows == [
        (
            row_id,
            "gin-regression",
            "fixture",
            "gin-row",
            {"marker": "gin-retry"},
            1,
            _RECONCILE_NAIVE_UTC.replace(tzinfo=UTC),
            "timestamp with time zone",
        )
    ]
    with psycopg.connect(scenario.sync_url) as connection:
        index = _event_search_index_catalog(connection)
        assert index is not None
        assert index[2:5] == (True, True, "gin")
