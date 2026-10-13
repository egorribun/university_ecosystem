"""Semantic PostgreSQL coverage for two historical data migrations.

These schemas and revision calls are isolated compatibility tests. Historical
downgrade exercise here does not claim production recovery below ADR-036.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
import yaml
from alembic.migration import MigrationContext
from alembic.operations import Operations
from testcontainers.community.postgres import PostgresContainer

from tests.helpers.synthetic_credentials import make_test_url_password

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = PROJECT_ROOT / "alembic" / "versions"


def _postgres_image_from_test_compose() -> str:
    compose_path = PROJECT_ROOT / "docker-compose.test.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    try:
        image = compose["services"]["postgres"]["image"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(
            "docker-compose.test.yml must define services.postgres.image"
        ) from exc
    if (
        not isinstance(image, str)
        or re.fullmatch(r"pgvector/pgvector:pg17@sha256:[0-9a-f]{64}", image) is None
    ):
        raise RuntimeError(
            "docker-compose.test.yml services.postgres.image "
            "must be a digest-pinned PG17 image"
        )
    return image


_RUN_INTEGRATION_TESTS = os.getenv("RUN_INTEGRATION_TESTS") == "1"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _RUN_INTEGRATION_TESTS,
        reason="Set RUN_INTEGRATION_TESTS=1 to run owned PostgreSQL integration",
    ),
]


@pytest.fixture(scope="module")
def migration_engine() -> Iterator[sa.Engine]:
    """Use a digest-pinned, resource-bounded and owner-labelled PG17 container."""
    run_id = uuid4().hex
    image = _postgres_image_from_test_compose()
    with PostgresContainer(
        image,
        name=f"ue-historical-migrations-pg17-{run_id}",
        labels={
            "university-ecosystem.dev/test-owner": f"historical-migrations-{run_id}",
            "university-ecosystem.dev/test-purpose": "historical-data-migration-integration",
        },
        mem_limit=1024**3,
        memswap_limit=1024**3,
        nano_cpus=2_000_000_000,
    ) as postgres:
        engine = sa.create_engine(
            postgres.get_connection_url(driver="psycopg"),
            pool_size=2,
            max_overflow=0,
        )
        try:
            yield engine
        finally:
            engine.dispose()


@contextmanager
def _isolated_schema(
    engine: sa.Engine,
) -> Iterator[tuple[sa.Connection, str]]:
    """Run each revision in a committed, uniquely named, connection-local schema."""
    schema = f"historical_{uuid4().hex}"
    with engine.begin() as admin:
        admin.execute(sa.schema.CreateSchema(schema))

    schema_engine = sa.create_engine(
        engine.url,
        connect_args={"options": f"-csearch_path={schema}"},
        pool_size=1,
        max_overflow=0,
    )
    try:
        with schema_engine.connect() as connection, connection.begin():
            assert (
                connection.execute(sa.text("SELECT current_schema()")).scalar_one()
                == schema
            )
            # Ensure Alembic's unqualified inspector calls resolve this schema.
            assert sa.inspect(connection).default_schema_name == schema
            yield connection, schema
    finally:
        schema_engine.dispose()
        with engine.begin() as admin:
            admin.execute(sa.schema.DropSchema(schema, cascade=True))


def _load_migration(filename: str) -> ModuleType:
    path = MIGRATIONS / filename
    spec = importlib.util.spec_from_file_location(
        f"historical_migration_{path.stem}", path
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _bind_migration(
    migration: ModuleType,
    connection: sa.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        migration, "op", Operations(MigrationContext.configure(connection))
    )
    if hasattr(migration, "context"):
        monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)


def _attendance_digest(key: str, token: str) -> str:
    digest = hmac.new(key.encode(), token.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _column_type(
    connection: sa.Connection, schema: str, table: str, column: str
) -> str:
    return connection.execute(
        sa.text(
            """
            SELECT data_type
              FROM information_schema.columns
             WHERE table_schema = :schema
               AND table_name = :table
               AND column_name = :column
            """
        ),
        {"schema": schema, "table": table, "column": column},
    ).scalar_one()


def _constraint_catalog(
    connection: sa.Connection, schema: str, table: str
) -> dict[str, tuple[str, bool, str]]:
    rows = connection.execute(
        sa.text(
            """
            SELECT c.conname, c.contype, c.convalidated,
                   pg_get_constraintdef(c.oid) AS definition
              FROM pg_constraint AS c
              JOIN pg_class AS t ON t.oid = c.conrelid
              JOIN pg_namespace AS n ON n.oid = t.relnamespace
             WHERE n.nspname = :schema
               AND t.relname = :table
            """
        ),
        {"schema": schema, "table": table},
    ).mappings()
    return {
        row["conname"]: (row["contype"], row["convalidated"], row["definition"])
        for row in rows
    }


def _index_catalog(
    connection: sa.Connection, schema: str, table: str
) -> dict[str, tuple[bool, str]]:
    rows = connection.execute(
        sa.text(
            """
            SELECT idx.relname AS index_name, i.indisvalid,
                   pg_get_indexdef(i.indexrelid) AS definition
              FROM pg_index AS i
              JOIN pg_class AS t ON t.oid = i.indrelid
              JOIN pg_namespace AS n ON n.oid = t.relnamespace
              JOIN pg_class AS idx ON idx.oid = i.indexrelid
             WHERE n.nspname = :schema
               AND t.relname = :table
            """
        ),
        {"schema": schema, "table": table},
    ).mappings()
    return {row["index_name"]: (row["indisvalid"], row["definition"]) for row in rows}


def test_attendance_tokens_preserve_rows_and_support_historical_roundtrip(
    migration_engine: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    migration = _load_migration("202507310002_tokenize_event_attendance.py")
    key = "attendance-integration-key"
    legacy_qr = "legacy-qr-501"
    qr_secret_for_null_row = make_test_url_password(length=26)
    monkeypatch.setenv("ATTENDANCE_TOKEN_SECRET", key)
    monkeypatch.setattr(
        migration,
        "secrets",
        SimpleNamespace(token_urlsafe=lambda _length: qr_secret_for_null_row),
    )

    with _isolated_schema(migration_engine) as (connection, _schema):
        table = sa.Table(
            "event_attendance",
            sa.MetaData(),
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("qr_code", sa.String(), nullable=True),
        )
        table.create(connection)
        connection.execute(
            table.insert(),
            [
                {"id": 501, "qr_code": legacy_qr},
                {"id": 502, "qr_code": None},
            ],
        )
        _bind_migration(migration, connection, monkeypatch)

        migration.upgrade()
        columns = {
            column["name"]: column
            for column in sa.inspect(connection).get_columns("event_attendance")
        }
        assert "qr_code" not in columns
        assert columns["qr_secret"]["nullable"] is False
        assert columns["qr_hmac"]["nullable"] is False
        assert sa.inspect(connection).get_pk_constraint("event_attendance")[
            "constrained_columns"
        ] == ["id"]

        rows = (
            connection.execute(
                sa.text(
                    "SELECT id, qr_secret, qr_hmac FROM event_attendance ORDER BY id"
                )
            )
            .mappings()
            .all()
        )
        assert [(row["id"], row["qr_secret"]) for row in rows] == [
            (501, legacy_qr),
            (502, qr_secret_for_null_row),
        ]
        assert [row["qr_hmac"] for row in rows] == [
            _attendance_digest(key, legacy_qr),
            _attendance_digest(key, qr_secret_for_null_row),
        ]

        # A second upgrade sees the current catalog shape and is data-idempotent.
        migration.upgrade()
        repeated_rows = (
            connection.execute(
                sa.text(
                    "SELECT id, qr_secret, qr_hmac FROM event_attendance ORDER BY id"
                )
            )
            .mappings()
            .all()
        )
        assert [
            (row["id"], row["qr_secret"], row["qr_hmac"]) for row in repeated_rows
        ] == [(row["id"], row["qr_secret"], row["qr_hmac"]) for row in rows]

        # Historical-only downgrade check on this isolated schema.
        migration.downgrade()
        downgraded_columns = {
            column["name"]
            for column in sa.inspect(connection).get_columns("event_attendance")
        }
        assert downgraded_columns == {"id", "qr_code"}
        assert connection.execute(
            sa.text("SELECT id, qr_code FROM event_attendance ORDER BY id")
        ).all() == [
            (501, legacy_qr),
            (502, qr_secret_for_null_row),
        ]
        assert sa.inspect(connection).get_pk_constraint("event_attendance")[
            "constrained_columns"
        ] == ["id"]


def test_attendance_upgrade_keeps_existing_secret_and_recomputes_digest(
    migration_engine: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    migration = _load_migration("202507310002_tokenize_event_attendance.py")
    key = "attendance-partial-catalog-key"
    monkeypatch.setenv("ATTENDANCE_TOKEN_SECRET", key)

    with _isolated_schema(migration_engine) as (connection, _schema):
        table = sa.Table(
            "event_attendance",
            sa.MetaData(),
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("qr_code", sa.String(), nullable=True),
            sa.Column("qr_secret", sa.String(), nullable=True),
            sa.Column("qr_hmac", sa.String(), nullable=True),
        )
        table.create(connection)
        connection.execute(
            table.insert().values(
                id=703,
                qr_code="different-legacy-value",
                qr_secret="already-issued-secret",
                qr_hmac="stale-digest",
            )
        )
        _bind_migration(migration, connection, monkeypatch)

        migration.upgrade()
        assert connection.execute(
            sa.text("SELECT id, qr_secret, qr_hmac FROM event_attendance")
        ).one() == (
            703,
            "already-issued-secret",
            _attendance_digest(key, "already-issued-secret"),
        )
        assert "qr_code" not in {
            column["name"]
            for column in sa.inspect(connection).get_columns("event_attendance")
        }


def test_attendance_revision_is_a_noop_when_table_is_absent(
    migration_engine: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    migration = _load_migration("202507310002_tokenize_event_attendance.py")
    monkeypatch.setenv("ATTENDANCE_TOKEN_SECRET", "attendance-noop-key")

    with _isolated_schema(migration_engine) as (connection, _schema):
        _bind_migration(migration, connection, monkeypatch)

        migration.upgrade()
        migration.downgrade()
        assert sa.inspect(connection).get_table_names() == []


def test_sender_id_upgrade_and_historical_downgrade_preserve_catalog(
    migration_engine: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    migration = _load_migration("fix_sender_id_type.py")

    with _isolated_schema(migration_engine) as (connection, schema):
        connection.execute(sa.text("CREATE TABLE chats (id INTEGER PRIMARY KEY)"))
        connection.execute(sa.text("INSERT INTO chats (id) VALUES (91)"))
        connection.execute(
            sa.text(
                """
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    sender_id VARCHAR(20) NOT NULL,
                    CONSTRAINT fk_messages_chat
                        FOREIGN KEY (chat_id) REFERENCES chats(id)
                )
                """
            )
        )
        connection.execute(
            sa.text(
                """
                CREATE TABLE chat_participants (
                    id INTEGER PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    user_id VARCHAR(20) NOT NULL,
                    CONSTRAINT fk_participants_chat
                        FOREIGN KEY (chat_id) REFERENCES chats(id)
                )
                """
            )
        )
        connection.execute(
            sa.text("CREATE INDEX ix_messages_sender_id ON messages (sender_id)")
        )
        connection.execute(
            sa.text(
                "CREATE INDEX ix_chat_participants_user_id "
                "ON chat_participants (user_id)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO messages (id, chat_id, sender_id) VALUES (901, 91, '7')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO chat_participants (id, chat_id, user_id) "
                "VALUES (902, 91, '7')"
            )
        )
        _bind_migration(migration, connection, monkeypatch)

        migration.upgrade()
        assert _column_type(connection, schema, "messages", "sender_id") == "integer"
        assert (
            _column_type(connection, schema, "chat_participants", "user_id")
            == "integer"
        )
        assert connection.execute(
            sa.text("SELECT id, chat_id, sender_id FROM messages")
        ).one() == (901, 91, 7)
        assert connection.execute(
            sa.text("SELECT id, chat_id, user_id FROM chat_participants")
        ).one() == (902, 91, 7)

        for table, expected_fk, expected_index, indexed_column in (
            ("messages", "fk_messages_chat", "ix_messages_sender_id", "sender_id"),
            (
                "chat_participants",
                "fk_participants_chat",
                "ix_chat_participants_user_id",
                "user_id",
            ),
        ):
            constraints = _constraint_catalog(connection, schema, table)
            assert constraints[expected_fk][0:2] == ("f", True)
            assert "FOREIGN KEY (chat_id)" in constraints[expected_fk][2]
            indexes = _index_catalog(connection, schema, table)
            assert indexes[expected_index][0] is True
            assert indexed_column in indexes[expected_index][1]

        # A second upgrade sees the current types and is data-idempotent.
        migration.upgrade()
        assert connection.execute(
            sa.text("SELECT id, sender_id FROM messages")
        ).one() == (901, 7)
        assert connection.execute(
            sa.text("SELECT id, user_id FROM chat_participants")
        ).one() == (902, 7)

        # This only exercises the historical revision on synthetic isolated
        # state; it does not authorize production recovery below ADR-036.
        migration.downgrade()
        assert _column_type(connection, schema, "messages", "sender_id") == (
            "character varying"
        )
        assert _column_type(connection, schema, "chat_participants", "user_id") == (
            "character varying"
        )
        assert connection.execute(
            sa.text("SELECT id, sender_id FROM messages")
        ).one() == (901, "7")
        assert connection.execute(
            sa.text("SELECT id, user_id FROM chat_participants")
        ).one() == (902, "7")
        assert _constraint_catalog(connection, schema, "messages")["fk_messages_chat"][
            0:2
        ] == ("f", True)
        assert (
            _index_catalog(connection, schema, "messages")["ix_messages_sender_id"][0]
            is True
        )

        migration.downgrade()
        assert _column_type(connection, schema, "messages", "sender_id") == (
            "character varying"
        )


def test_sender_id_upgrade_rolls_back_both_tables_on_invalid_numeric_value(
    migration_engine: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    migration = _load_migration("fix_sender_id_type.py")

    with _isolated_schema(migration_engine) as (connection, schema):
        connection.execute(
            sa.text(
                "CREATE TABLE messages "
                "(id INTEGER PRIMARY KEY, sender_id VARCHAR(20) NOT NULL)"
            )
        )
        connection.execute(
            sa.text(
                "CREATE TABLE chat_participants "
                "(id INTEGER PRIMARY KEY, user_id VARCHAR(20) NOT NULL)"
            )
        )
        connection.execute(
            sa.text("INSERT INTO messages (id, sender_id) VALUES (1001, '17')")
        )
        connection.execute(
            sa.text(
                "INSERT INTO chat_participants (id, user_id) "
                "VALUES (1002, 'not-an-integer')"
            )
        )
        _bind_migration(migration, connection, monkeypatch)

        with pytest.raises(sa.exc.DBAPIError) as failure:
            with connection.begin_nested():
                migration.upgrade()
        assert getattr(failure.value.orig, "sqlstate", None) == "22P02"

        # PostgreSQL rolls the earlier messages ALTER back with the failed
        # chat_participants cast; row identities and raw values remain intact.
        assert _column_type(connection, schema, "messages", "sender_id") == (
            "character varying"
        )
        assert _column_type(connection, schema, "chat_participants", "user_id") == (
            "character varying"
        )
        assert connection.execute(
            sa.text("SELECT id, sender_id FROM messages")
        ).one() == (1001, "17")
        assert connection.execute(
            sa.text("SELECT id, user_id FROM chat_participants")
        ).one() == (1002, "not-an-integer")


def test_sender_id_revision_is_noop_for_absent_tables_and_columns(
    migration_engine: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    migration = _load_migration("fix_sender_id_type.py")

    with _isolated_schema(migration_engine) as (connection, schema):
        _bind_migration(migration, connection, monkeypatch)
        migration.upgrade()
        migration.downgrade()
        assert sa.inspect(connection).get_table_names() == []

        connection.execute(
            sa.text("CREATE TABLE messages (id INTEGER PRIMARY KEY, body TEXT)")
        )
        connection.execute(
            sa.text(
                "CREATE TABLE chat_participants (id INTEGER PRIMARY KEY, role TEXT)"
            )
        )
        migration.upgrade()
        migration.downgrade()
        assert _column_type(connection, schema, "messages", "body") == "text"
        assert _column_type(connection, schema, "chat_participants", "role") == "text"
