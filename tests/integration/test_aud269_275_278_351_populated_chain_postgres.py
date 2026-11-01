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
