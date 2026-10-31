"""Characterize historical migration 148 without declaring it safe to deploy.

These checks record source-bound SQL and catalog-dependent orchestration. They
do not replace PostgreSQL execution against a representative database.
"""

from __future__ import annotations

import ast
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
import sqlalchemy.inspection as sa_inspection
from alembic.config import Config
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from alembic import command
from tests import test_migration_148642dd1207_backfill as backfill
from tests import test_migration_148642dd1207_orchestrator as orchestrator

ROOT = Path(__file__).resolve().parents[1]
INITIAL_REVISION = ROOT / "alembic/versions/933372f5da9a_init_schema.py"


def _initial_role_labels() -> tuple[str, ...]:
    tree = ast.parse(INITIAL_REVISION.read_text(encoding="utf-8"))
    role_enums = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Enum"
        and any(
            keyword.arg == "name"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == "userrole"
            for keyword in node.keywords
        )
    ]
    assert len(role_enums) == 1
    labels = tuple(ast.literal_eval(arg) for arg in role_enums[0].args)
    assert all(isinstance(label, str) for label in labels)
    return labels


def _render_upgrade(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://migration_test@127.0.0.1:5432/migration_test",
    )
    output = io.StringIO()
    config = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    command.upgrade(config, "f7aa476e968a:148642dd1207", sql=True)
    return output.getvalue()


def test_aud327_role_update_uses_new_enum_values_before_transaction_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # This is evidence of the historical hazard, not a PostgreSQL runtime test.
    assert _initial_role_labels() == ("STUDENT", "TEACHER", "ADMIN", "SUPERUSER")
    sql = _render_upgrade(monkeypatch)
    begin = sql.index("BEGIN;")
    add_student = sql.index("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'student'")
    update = sql.index("SET role = LOWER(role::text)::userrole")
    commit = sql.index("COMMIT;", update)
    assert begin < add_student < update < commit
    assert "COMMIT;" not in sql[add_student:update]


def test_aud433_missing_notifications_produces_partitioned_parent_without_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, ops, inspector = orchestrator._install(
        monkeypatch,
        dialect="postgresql",
        groups_id_integer=True,
    )
    existing = inspector.has_table
    monkeypatch.setattr(
        inspector,
        "has_table",
        lambda table: table != "notifications" and existing(table),
    )

    migration.upgrade()

    notifications = [
        (args, kwargs)
        for kind, name, args, kwargs in ops.events
        if kind == "op" and name == "create_table" and args[0] == "notifications"
    ]
    assert len(notifications) == 1
    args, kwargs = notifications[0]
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.Integer(), primary_key=True))
    parent = sa.Table(args[0], metadata, *args[1:], **kwargs)
    ddl = str(CreateTable(parent).compile(dialect=postgresql.dialect())).upper()
    assert "PARTITION BY RANGE (CREATED_AT)" in ddl
    assert "PRIMARY KEY (ID, CREATED_AT)" in ddl
    emitted = orchestrator._executed_sql(ops)
    assert "PARTITION OF NOTIFICATIONS" not in emitted


def test_aud348_backfill_is_called_after_target_creation_before_legacy_drops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, ops, inspector = orchestrator._install(
        monkeypatch,
        dialect="postgresql",
        groups_id_integer=True,
        all_user_columns=True,
    )
    existing = inspector.has_table
    monkeypatch.setattr(
        inspector,
        "has_table",
        lambda table: table != "spotify_integrations" and existing(table),
    )

    def record_backfill() -> None:
        ops.events.append(("evidence", "spotify_backfill", (), {}))

    monkeypatch.setattr(migration, "_backfill_spotify_integrations", record_backfill)
    migration.upgrade()

    creation = next(
        index
        for index, (kind, name, args, _kwargs) in enumerate(ops.events)
        if kind == "op" and name == "create_table" and args[0] == "spotify_integrations"
    )
    backfill = next(
        index
        for index, (kind, name, _args, _kwargs) in enumerate(ops.events)
        if kind == "evidence" and name == "spotify_backfill"
    )
    drops: dict[str, int] = {
        str(args[1]): index
        for index, (kind, name, args, _kwargs) in enumerate(ops.events)
        if kind == "batch"
        and name == "drop_column"
        and args[0] == "users"
        and str(args[1]).startswith("spotify_")
    }
    assert {"spotify_access_token", "spotify_refresh_token"} <= drops.keys()
    assert creation < backfill < min(drops.values())


def test_aud348_existing_empty_destination_excludes_legacy_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = backfill._load_migration()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    users, integrations = backfill._tables(engine)
    assert users is not None and integrations is not None
    with engine.begin() as connection:
        connection.execute(
            users.insert(),
            {
                "id": 41,
                "spotify_access_token": "opaque-legacy-a",
                "spotify_refresh_token": "opaque-legacy-b",
            },
        )
        connection.execute(
            integrations.insert(),
            {"user_id": 41, "is_connected": False, "is_playing": False},
        )
        backfill._install(
            monkeypatch,
            migration,
            SimpleNamespace(is_offline_mode=lambda: False),
            backfill._Ops(connection),
        )

        migration._backfill_spotify_integrations()

        row = connection.execute(sa.select(integrations)).mappings().one()
        assert row["access_token"] is None
        assert row["refresh_token"] is None
        assert connection.execute(
            sa.select(users.c.spotify_access_token, users.c.spotify_refresh_token)
        ).one() == ("opaque-legacy-a", "opaque-legacy-b")
    engine.dispose()


def test_aud348_postgresql_insert_excludes_every_existing_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = backfill._load_migration()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    backfill._tables(engine, user_fields=("spotify_access_token",))
    with engine.begin() as connection:
        proxy = backfill._DialectProxy(connection, "postgresql")
        inspect = sa_inspection.inspect

        def inspect_proxy(subject: object, *args: object, **kwargs: object) -> object:
            return inspect(connection if subject is proxy else subject, *args, **kwargs)

        monkeypatch.setattr(sa_inspection, "inspect", inspect_proxy)
        monkeypatch.setattr(migration.sa, "inspect", inspect_proxy)
        backfill._install(
            monkeypatch,
            migration,
            SimpleNamespace(is_offline_mode=lambda: False),
            backfill._Ops(proxy),
        )
        migration._backfill_spotify_integrations()
        assert len(proxy.statements) == 1
        sql = str(proxy.statements[0].compile(dialect=postgresql.dialect())).upper()
        assert "NOT (EXISTS" in sql
        assert "SPOTIFY_INTEGRATIONS.USER_ID = USERS.ID" in sql
        assert "ON CONFLICT (USER_ID) DO NOTHING" in sql
    engine.dispose()
