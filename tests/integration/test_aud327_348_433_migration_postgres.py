"""Synthetic PostgreSQL evidence for historical 148; never runs its upgrade.

The coordinator must supply an exclusive, initially empty, disposable database
on a separately verified, owned container. This module starts no containers and
does not create or drop databases or delete source data.
"""

from __future__ import annotations

import ast
import os
import re
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import docker
import pytest
import sqlalchemy as sa
from docker.errors import DockerException

from tests import test_migration_148642dd1207_backfill as backfill
from tests.integration.owned_postgres import _LoopbackMigrationPostgres
from tests.integration.test_historical_migration_semantics_postgres import (
    _pinned_postgres_image,
)
from tests.test_aud327_348_433_migration_evidence import _initial_role_labels

ROOT = Path(__file__).resolve().parents[2]
REVISION = ROOT / "alembic/versions/148642dd1207_fix_missing_tables.py"
IMAGE = _pinned_postgres_image()
pytestmark = pytest.mark.integration


@pytest.fixture(scope="session", autouse=True)
def prepare_database() -> None:
    """Keep the shared app fixture from initializing or resetting the probe DB."""


@pytest.fixture(autouse=True)
def clean_database() -> None:
    """Leave all synthetic probe data untouched until the owned server is removed."""


def _upgrade_ast() -> ast.FunctionDef:
    module = ast.parse(REVISION.read_text(encoding="utf-8"))
    return next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
    )


def _role_sql() -> tuple[str, str]:
    upgrade = _upgrade_ast()
    additions = [
        node
        for node in ast.walk(upgrade)
        if isinstance(node, ast.JoinedStr)
        and any(
            isinstance(part, ast.Constant)
            and isinstance(part.value, str)
            and "ALTER TYPE userrole ADD VALUE IF NOT EXISTS" in part.value
            for part in node.values
        )
    ]
    assert len(additions) == 1
    template_parts: list[str] = []
    variables = 0
    for part in additions[0].values:
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            template_parts.append(part.value)
        else:
            assert isinstance(part, ast.FormattedValue)
            assert isinstance(part.value, ast.Name) and part.value.id == "role"
            assert part.format_spec is None and part.conversion == -1
            variables += 1
            template_parts.append("{role}")
    assert variables == 1
    add_student = "".join(template_parts).format(role="student")
    updates = [
        node.value.strip()
        for node in ast.walk(upgrade)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "SET role = LOWER(role::text)::userrole" in node.value
    ]
    assert len(updates) == 1
    return add_student, updates[0]


def _notifications_ddl() -> str:
    candidates = [
        node
        for node in ast.walk(_upgrade_ast())
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ensure_partitioned"
        and len(node.args) == 3
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "notifications"
    ]
    assert len(candidates) == 1
    create_sql, partition_key = candidates[0].args[1:]
    assert isinstance(create_sql, ast.Constant) and isinstance(create_sql.value, str)
    assert (
        isinstance(partition_key, ast.Constant) and partition_key.value == "created_at"
    )
    return create_sql.value.strip()


def _verify_owned_container(container_id: str, owner: str, url: str) -> None:
    if re.fullmatch(r"[0-9a-f]{64}", container_id) is None or not owner:
        raise RuntimeError("An exact owned container ID and owner label are required.")
    try:
        client = docker.from_env()
        try:
            metadata = client.api.inspect_container(container_id)
        finally:
            client.close()
        identity = metadata["Id"]
        image = metadata["Config"]["Image"]
        running = metadata["State"]["Running"]
        actual_owner = metadata["Config"]["Labels"][
            "university-ecosystem.dev/test-owner"
        ]
        ports = metadata["NetworkSettings"]["Ports"]["5432/tcp"]
    except (DockerException, KeyError, TypeError):
        raise RuntimeError("Could not verify the owned PostgreSQL container.") from None
    parsed = sa.engine.make_url(url)
    if (
        identity != container_id
        or image != IMAGE
        or running is not True
        or actual_owner != owner
        or not isinstance(ports, list)
        or len(ports) != 1
        or ports[0].get("HostIp") != parsed.host
        or ports[0].get("HostPort") != str(parsed.port)
    ):
        raise RuntimeError("PostgreSQL container ownership, image or port mismatch.")


def _assert_initially_empty(connection: sa.Connection) -> None:
    queries = (
        "SELECT EXISTS (SELECT 1 FROM pg_namespace "
        "WHERE nspname NOT IN ('public', 'information_schema') "
        "AND nspname !~ '^pg_')",
        "SELECT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n "
        "ON n.oid = c.relnamespace WHERE n.nspname = 'public')",
        "SELECT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n "
        "ON n.oid = p.pronamespace WHERE n.nspname = 'public')",
        "SELECT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n "
        "ON n.oid = t.typnamespace WHERE n.nspname = 'public')",
    )
    if any(connection.exec_driver_sql(query).scalar_one() for query in queries):
        raise RuntimeError("PostgreSQL evidence database is not initially empty.")


@pytest.fixture(scope="module")
def ephemeral_postgres() -> Iterator[sa.Engine]:
    if os.environ.get("AUD148_POSTGRES_ENABLED") != "1":
        pytest.skip("Explicitly enabled owned PostgreSQL evidence slot required")
    url = os.environ.get("MIGRATION_ROUNDTRIP_DATABASE_URL", "")
    container_id = os.environ.get("AUD148_POSTGRES_CONTAINER_ID", "")
    owner = os.environ.get("AUD148_POSTGRES_OWNER", "")
    operator = _LoopbackMigrationPostgres(url)
    _verify_owned_container(container_id, owner, url)
    engine = sa.create_engine(operator.get_connection_url(driver="psycopg"))
    try:
        with engine.connect() as connection:
            if (
                connection.exec_driver_sql("SHOW server_version_num").scalar_one()[:2]
                != "17"
            ):
                raise RuntimeError("The evidence database must be PostgreSQL 17.")
            _assert_initially_empty(connection)
        yield engine
    finally:
        engine.dispose()


def _search_path(connection: sa.Connection, schema: str) -> None:
    assert schema in {"aud327", "aud348", "aud433"}
    connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')


def _bind_revision(monkeypatch: pytest.MonkeyPatch, connection: sa.Connection) -> Any:
    migration = backfill._load_migration()
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: connection))
    monkeypatch.setattr(
        migration, "context", SimpleNamespace(is_offline_mode=lambda: False)
    )
    return migration


def test_aud327_new_lowercase_enum_cannot_be_used_before_commit(
    ephemeral_postgres: sa.Engine,
) -> None:
    assert _initial_role_labels() == ("STUDENT", "TEACHER", "ADMIN", "SUPERUSER")
    add_student, update = _role_sql()
    with ephemeral_postgres.begin() as connection:
        connection.exec_driver_sql('CREATE SCHEMA "aud327"')
        _search_path(connection, "aud327")
        connection.exec_driver_sql(
            "CREATE TYPE userrole AS ENUM ('STUDENT', 'TEACHER', 'ADMIN', 'SUPERUSER')"
        )
        connection.exec_driver_sql(
            "CREATE TABLE users (id integer PRIMARY KEY, role userrole)"
        )
        connection.exec_driver_sql("INSERT INTO users VALUES (1, 'STUDENT')")

    with ephemeral_postgres.connect() as connection:
        transaction = connection.begin()
        try:
            _search_path(connection, "aud327")
            connection.exec_driver_sql(add_student)
            with pytest.raises(sa.exc.DBAPIError) as error:
                connection.exec_driver_sql(update)
            assert getattr(error.value.orig, "sqlstate", None) == "55P04"
        finally:
            transaction.rollback()

    with ephemeral_postgres.begin() as connection:
        _search_path(connection, "aud327")
        assert (
            connection.exec_driver_sql("SELECT role::text FROM users").scalar_one()
            == "STUDENT"
        )
        labels = connection.exec_driver_sql(
            "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
            "JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = 'aud327' AND t.typname = 'userrole'"
        ).scalars()
        assert "student" not in labels
        connection.exec_driver_sql(add_student)

    with ephemeral_postgres.begin() as connection:
        _search_path(connection, "aud327")
        connection.exec_driver_sql(add_student)
        connection.exec_driver_sql(update)
        assert (
            connection.exec_driver_sql("SELECT role::text FROM users").scalar_one()
            == "student"
        )


def test_aud348_postgresql_backfill_preserves_existing_empty_destination(
    ephemeral_postgres: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with ephemeral_postgres.begin() as connection:
        connection.exec_driver_sql('CREATE SCHEMA "aud348"')
        _search_path(connection, "aud348")
        users, integrations = backfill._tables(connection)
        assert users is not None and integrations is not None
        source_rows = []
        for user_id in (1, 2):
            values = dict.fromkeys(users.c.keys())
            values.update(
                id=user_id,
                spotify_access_token="sample_a",
                spotify_refresh_token="sample_b",
            )
            source_rows.append(values)
        connection.execute(users.insert(), source_rows)
        connection.execute(
            integrations.insert(),
            {"user_id": 2, "is_connected": False, "is_playing": False},
        )

        _bind_revision(monkeypatch, connection)._backfill_spotify_integrations()

        rows = {
            row.user_id: (row.access_token, row.refresh_token)
            for row in connection.execute(
                sa.select(
                    integrations.c.user_id,
                    integrations.c.access_token,
                    integrations.c.refresh_token,
                )
            )
        }
        assert rows == {1: ("sample_a", "sample_b"), 2: (None, None)}
        assert (
            connection.execute(
                sa.select(sa.func.count()).select_from(users)
            ).scalar_one()
            == 2
        )
        columns = {
            column["name"] for column in sa.inspect(connection).get_columns("users")
        }
        assert {"spotify_access_token", "spotify_refresh_token"} <= columns


def test_aud433_postgresql_parent_without_child_rejects_inserts(
    ephemeral_postgres: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with ephemeral_postgres.begin() as connection:
        connection.exec_driver_sql('CREATE SCHEMA "aud433"')
        _search_path(connection, "aud433")
        connection.exec_driver_sql("CREATE TABLE users (id integer PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO users VALUES (1)")
        create_sql = _notifications_ddl()
        _bind_revision(monkeypatch, connection).ensure_partitioned(
            "notifications", create_sql, "created_at"
        )
        assert not sa.inspect(connection).has_table("notifications")
        connection.exec_driver_sql(create_sql)
        children = connection.exec_driver_sql(
            "SELECT count(*) FROM pg_inherits WHERE inhparent = 'notifications'::regclass"
        ).scalar_one()
        assert children == 0

        with pytest.raises(sa.exc.IntegrityError) as error:
            with connection.begin_nested():
                connection.exec_driver_sql(
                    "INSERT INTO notifications (user_id, title) VALUES (1, 'example')"
                )
        assert getattr(error.value.orig, "sqlstate", None) == "23514"
        connection.exec_driver_sql(
            "CREATE TABLE notifications_default PARTITION OF notifications DEFAULT"
        )
        connection.exec_driver_sql(
            "INSERT INTO notifications (user_id, title) VALUES (1, 'example')"
        )
        assert (
            connection.exec_driver_sql(
                "SELECT count(*) FROM notifications"
            ).scalar_one()
            == 1
        )
