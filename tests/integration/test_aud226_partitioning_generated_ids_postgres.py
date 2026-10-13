"""PostgreSQL regression checks for generated IDs after legacy partition conversion."""

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
PARTITIONING_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "6a898bba5589_implement_partitioning.py"
)
_RUN = os.environ.get("RUN_INTEGRATION_TESTS") == "1"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "aud226_partitioning_generated_ids", PARTITIONING_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _pinned_postgres_image() -> str:
    """Read the shared immutable PG17 test image pin from Compose."""
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
    """Use the existing digest-pinned PG17 image and bounded resource profile."""
    run_id = uuid4().hex
    with PostgresContainer(
        _pinned_postgres_image(),
        name=f"ue-aud226-partition-sequences-pg17-{run_id}",
        labels={
            "university-ecosystem.dev/test-owner": f"aud226-sequences-{run_id}",
            "university-ecosystem.dev/test-purpose": "partition-sequence-preservation",
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
    """Run the migration in a private schema and roll back all fixture state."""
    schema = f"aud226_{uuid4().hex}"
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


def _run_upgrade(migration, connection: sa.Connection) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()


def _create_legacy_schema(
    connection: sa.Connection,
    *,
    populated: bool,
    nonpositive_ids: bool = False,
) -> None:
    statements = (
        "CREATE TABLE users (id integer PRIMARY KEY)",
        "CREATE TABLE notifications ("
        "id serial PRIMARY KEY, user_id integer NOT NULL "
        "REFERENCES users(id) ON DELETE CASCADE, title varchar NOT NULL, "
        "title_en varchar, body text, body_en text, type varchar, url varchar, "
        "dedupe_key varchar(255), created_at timestamptz NOT NULL DEFAULT now(), "
        "read boolean DEFAULT false, read_at timestamptz)",
        "CREATE TABLE notification_deliveries ("
        "id serial PRIMARY KEY, notification_id integer NOT NULL "
        "REFERENCES notifications(id) ON DELETE CASCADE, "
        "channel varchar NOT NULL DEFAULT 'inapp', "
        "status varchar NOT NULL DEFAULT 'delivered', "
        "attempted_at timestamptz NOT NULL DEFAULT now(), delivered_at timestamptz, "
        "status_code integer, detail text)",
        "CREATE TABLE data_access_logs ("
        "id serial PRIMARY KEY, actor_user_id integer REFERENCES users(id) "
        "ON DELETE SET NULL, subject_user_id integer REFERENCES users(id) "
        "ON DELETE SET NULL, resource_type varchar(64) NOT NULL, "
        "resource_id varchar(128), action varchar(64) NOT NULL, context json, "
        "ip_address varchar(64), user_agent varchar(512), "
        "created_at timestamptz NOT NULL DEFAULT now(), signature varchar(512))",
    )
    for statement in statements:
        connection.execute(sa.text(statement))
    connection.execute(sa.text("INSERT INTO users (id) VALUES (1)"))

    if nonpositive_ids:
        connection.execute(
            sa.text(
                "INSERT INTO notifications (id, user_id, title, created_at) "
                "VALUES (0, 1, 'zero id notice', '2025-10-12 09:00:00+00')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO notification_deliveries "
                "(id, notification_id, channel, status, attempted_at) "
                "VALUES (-1, 0, 'email', 'delivered', "
                "'2025-10-12 09:01:00+00')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO data_access_logs "
                "(id, actor_user_id, subject_user_id, resource_type, action, "
                "created_at) VALUES (0, 1, 1, 'course', 'read', "
                "'2025-10-12 08:00:00+00')"
            )
        )
        return

    if not populated:
        return

    connection.execute(
        sa.text(
            "INSERT INTO notifications "
            "(id, user_id, title, created_at) "
            "VALUES (900, 1, 'seed notice', '2025-10-12 09:00:00+00')"
        )
    )
    connection.execute(
        sa.text(
            "INSERT INTO notification_deliveries "
            "(id, notification_id, channel, status, attempted_at) "
            "VALUES (700, 900, 'email', 'delivered', '2025-10-12 09:01:00+00')"
        )
    )
    connection.execute(
        sa.text(
            "INSERT INTO data_access_logs "
            "(id, actor_user_id, subject_user_id, resource_type, action, created_at) "
            "VALUES (600, 1, 1, 'course', 'read', '2025-10-12 08:00:00+00')"
        )
    )
    for table_name, last_id in (
        ("notifications", 900),
        ("notification_deliveries", 700),
        ("data_access_logs", 600),
    ):
        connection.execute(
            sa.text(
                "SELECT setval(pg_get_serial_sequence(:table_name, 'id'), "
                ":last_id, true)"
            ),
            {"table_name": table_name, "last_id": last_id},
        )


def _insert_one_of_each(connection: sa.Connection, *, timestamp: str) -> dict[str, int]:
    notification_id = connection.execute(
        sa.text(
            "INSERT INTO notifications (user_id, title, created_at) "
            "VALUES (1, 'generated notice', :created_at) RETURNING id"
        ),
        {"created_at": timestamp},
    ).scalar_one()
    delivery_id = connection.execute(
        sa.text(
            "INSERT INTO notification_deliveries "
            "(notification_id, notification_created_at, channel, status, "
            "attempted_at) "
            "VALUES (:notification_id, :created_at, 'email', 'delivered', "
            ":attempted_at) "
            "RETURNING id"
        ),
        {
            "notification_id": notification_id,
            "created_at": timestamp,
            "attempted_at": timestamp,
        },
    ).scalar_one()
    access_log_id = connection.execute(
        sa.text(
            "INSERT INTO data_access_logs "
            "(actor_user_id, subject_user_id, resource_type, action, created_at) "
            "VALUES (1, 1, 'course', 'read', :created_at) RETURNING id"
        ),
        {"created_at": timestamp},
    ).scalar_one()
    return {
        "notifications": int(notification_id),
        "notification_deliveries": int(delivery_id),
        "data_access_logs": int(access_log_id),
    }


def test_partitioning_advances_each_serial_sequence_past_copied_ids(
    postgres_engine: sa.Engine,
) -> None:
    migration = _load_migration()
    with _isolated_schema(postgres_engine) as connection:
        _create_legacy_schema(connection, populated=True)

        _run_upgrade(migration, connection)

        generated = _insert_one_of_each(connection, timestamp="2026-10-12 10:00:00+00")
        assert generated == {
            "notifications": 901,
            "notification_deliveries": 701,
            "data_access_logs": 601,
        }

        _run_upgrade(migration, connection)

        repeated = _insert_one_of_each(connection, timestamp="2026-10-12 11:00:00+00")
        assert repeated == {
            "notifications": 902,
            "notification_deliveries": 702,
            "data_access_logs": 602,
        }


def test_partitioning_empty_legacy_tables_start_generated_ids_at_one(
    postgres_engine: sa.Engine,
) -> None:
    migration = _load_migration()
    with _isolated_schema(postgres_engine) as connection:
        _create_legacy_schema(connection, populated=False)

        _run_upgrade(migration, connection)

        generated = _insert_one_of_each(connection, timestamp="2026-10-12 10:00:00+00")
        assert generated == {
            "notifications": 1,
            "notification_deliveries": 1,
            "data_access_logs": 1,
        }


def test_partitioning_nonpositive_legacy_ids_reset_sequences_to_one(
    postgres_engine: sa.Engine,
) -> None:
    migration = _load_migration()
    with _isolated_schema(postgres_engine) as connection:
        _create_legacy_schema(
            connection,
            populated=False,
            nonpositive_ids=True,
        )

        _run_upgrade(migration, connection)

        assert connection.execute(
            sa.text("SELECT id, title FROM notifications")
        ).one() == (0, "zero id notice")
        assert connection.execute(
            sa.text("SELECT id, notification_id FROM notification_deliveries")
        ).one() == (-1, 0)
        assert connection.execute(
            sa.text("SELECT id, action FROM data_access_logs")
        ).one() == (0, "read")

        generated = _insert_one_of_each(connection, timestamp="2026-10-12 10:00:00+00")
        assert generated == {
            "notifications": 1,
            "notification_deliveries": 1,
            "data_access_logs": 1,
        }
