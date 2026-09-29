"""Contracts for the remaining BE-02 timestamp and role defaults."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

import app.models  # noqa: F401 - register mapped metadata
from app.core.database import Base

TIMESTAMP_COLUMNS = (
    "attachments.created_at",
    "chats.created_at",
    "chats.updated_at",
    "dead_letter_jobs.created_at",
    "dead_letter_jobs.updated_at",
    "failed_outbox_events.failed_at",
    "grades.created_at",
    "grades.updated_at",
    "message_reactions.created_at",
    "messages.created_at",
    "stored_events.created_at",
)
MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic/versions/202609250001_phase_semantic_defaults.py"
)


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "be02_semantic_defaults", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_remaining_timestamp_candidates_are_dual_declared() -> None:
    for qualified in TIMESTAMP_COLUMNS:
        table, field = qualified.split(".", 1)
        column = Base.metadata.tables[table].c[field]
        assert column.default is not None, qualified
        assert column.server_default is not None, qualified


def test_user_role_default_is_dual_declared_and_sqlite_compatible() -> None:
    role = Base.metadata.tables["users"].c.role
    assert role.default is not None
    assert role.server_default is not None

    engine = sa.create_engine("sqlite://")
    probe = sa.Table(
        "role_default_probe",
        sa.MetaData(),
        sa.Column("role", role.type, server_default=role.server_default.arg),
    )
    probe.create(engine)
    with engine.begin() as connection:
        inserted = connection.execute(probe.insert().returning(probe.c.role))
        assert inserted.scalar_one() == "student"


def test_phase_four_migration_targets_only_reviewed_candidates() -> None:
    migration = _migration()
    assert migration.revision == "202609250001"
    assert migration.down_revision == "202609220001"
    assert {f"{spec.table}.{spec.column}" for spec in migration.DEFAULT_SPECS} == {
        *TIMESTAMP_COLUMNS,
        "users.role",
    }


def test_phase_four_policy_accounts_for_all_remaining_exceptions() -> None:
    policy = json.loads(
        (
            Path(__file__).resolve().parents[1] / "quality/model-default-policy.json"
        ).read_text(encoding="utf-8")
    )
    assert policy["expected"]["migration_head"] == "202609250001"
    assert policy["expected"]["effective_counts"] == {
        "both": 94,
        "python_only": 40,
        "server_only": 0,
    }
    assert len(policy["exceptions"]) == 40


def test_conflicting_timestamp_default_is_rejected() -> None:
    migration = _migration()
    spec = migration.DEFAULT_SPECS[0]
    state = migration.CatalogState(
        "timestamp with time zone",
        True,
        "clock_timestamp()",
        "timestamptz",
        "b",
        True,
        0,
    )
    with pytest.raises(RuntimeError, match="conflicting server default"):
        migration._validate_state(spec, state)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"data_type": "timestamp without time zone"}, "timestamptz"),
        ({"not_null": False}, "NOT NULL"),
        ({"null_count": 1}, "NULL rows"),
    ],
)
def test_timestamp_preflight_rejects_schema_or_data_drift(
    changes: dict[str, object], message: str
) -> None:
    migration = _migration()
    state = migration.CatalogState(
        "timestamp with time zone", True, None, "timestamptz", "b", True, 0
    )._replace(**changes)
    with pytest.raises(RuntimeError, match=message):
        migration._validate_state(migration.DEFAULT_SPECS[0], state)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"type_name": "text"}, "userrole"),
        ({"type_kind": "b"}, "enum"),
        ({"type_schema_matches": False}, "schema"),
        ({"default_sql": "'STUDENT'::userrole"}, "conflicting server default"),
        ({"default_sql": "'pen ding'::userrole"}, "conflicting server default"),
    ],
)
def test_role_preflight_rejects_wrong_enum_or_default(
    changes: dict[str, object], message: str
) -> None:
    migration = _migration()
    state = migration.CatalogState(
        "userrole", True, None, "userrole", "e", True, 0
    )._replace(**changes)
    with pytest.raises(RuntimeError, match=message):
        migration._validate_state(migration.DEFAULT_SPECS[-1], state)


def test_upgrade_preflights_every_column_before_any_ddl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _migration()
    specs = (migration.DEFAULT_SPECS[0], migration.DEFAULT_SPECS[-1])
    monkeypatch.setattr(migration, "DEFAULT_SPECS", specs)
    states = {
        specs[0]: migration.CatalogState(
            "timestamp with time zone", True, None, "timestamptz", "b", True, 0
        ),
        specs[1]: migration.CatalogState(
            "userrole", True, "'ADMIN'::userrole", "userrole", "e", True, 0
        ),
    }
    monkeypatch.setattr(
        migration,
        "_catalog_state",
        lambda _bind, spec, _schema: states[spec],
        raising=False,
    )
    alter = Mock()
    monkeypatch.setattr(migration, "_apply_default", alter, raising=False)
    monkeypatch.setattr(migration, "_lock_postgres", Mock(), raising=False)
    monkeypatch.setattr(migration, "_target_schema", lambda _bind: "public")
    lock_targets = Mock()
    monkeypatch.setattr(migration, "_lock_targets", lock_targets, raising=False)

    with pytest.raises(RuntimeError, match="conflicting server default"):
        migration._run_upgrade(object())

    alter.assert_not_called()
    lock_targets.assert_called_once()


def test_missing_catalog_column_aborts_phase() -> None:
    migration = _migration()
    bind = Mock()
    bind.execute.return_value.mappings.return_value.one_or_none.return_value = None

    with pytest.raises(RuntimeError, match=r"requires attachments\.created_at"):
        migration._catalog_state(bind, migration.DEFAULT_SPECS[0], "public")


def test_default_ddl_is_scoped_to_the_reviewed_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _migration()
    alter = Mock()
    monkeypatch.setattr(migration.op, "alter_column", alter)

    migration._apply_default(migration.DEFAULT_SPECS[-1], "public")

    alter.assert_called_once()
    args, kwargs = alter.call_args
    assert args == ("users", "role")
    assert str(kwargs["server_default"]) == "'student'::userrole"
    assert kwargs["existing_nullable"] is False
    assert kwargs["schema"] == "public"


def test_target_locks_are_schema_qualified_and_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _migration()
    monkeypatch.setattr(
        migration,
        "DEFAULT_SPECS",
        (
            migration.DefaultSpec("users", "role", "'student'::userrole", "role"),
            migration.DefaultSpec("chats", "updated_at", "now()", "timestamp"),
            migration.DefaultSpec("chats", "created_at", "now()", "timestamp"),
        ),
    )
    execute = Mock()
    bind = Mock()
    bind.dialect = postgresql.dialect()
    monkeypatch.setattr(migration.op, "execute", execute)

    migration._lock_targets(bind, "my_schema")

    assert [str(call.args[0]) for call in execute.call_args_list] == [
        'LOCK TABLE "my_schema"."chats" IN ACCESS EXCLUSIVE MODE',
        'LOCK TABLE "my_schema"."users" IN ACCESS EXCLUSIVE MODE',
    ]


def test_offline_upgrade_aborts_before_recording_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _migration()
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: True)
    execute = Mock()
    monkeypatch.setattr(migration.op, "execute", execute)

    migration.upgrade()

    execute.assert_called_once()
    assert "RAISE EXCEPTION" in str(execute.call_args.args[0])


def test_downgrade_preserves_default_and_fails_on_missing_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _migration()
    spec = migration.DEFAULT_SPECS[0]
    monkeypatch.setattr(migration, "DEFAULT_SPECS", (spec,))
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(
        migration.op,
        "get_bind",
        lambda: type("Bind", (), {"dialect": postgresql.dialect()})(),
    )
    monkeypatch.setattr(migration, "_lock_postgres", Mock(), raising=False)
    monkeypatch.setattr(migration, "_target_schema", lambda _bind: "public")
    monkeypatch.setattr(migration, "_lock_targets", Mock(), raising=False)
    alter = Mock()
    monkeypatch.setattr(migration.op, "alter_column", alter)
    state = migration.CatalogState(
        "timestamp with time zone", True, "now()", "timestamptz", "b", True, 0
    )
    monkeypatch.setattr(
        migration, "_catalog_state", lambda _bind, _spec, _schema: state
    )

    migration.downgrade()
    alter.assert_not_called()

    monkeypatch.setattr(
        migration,
        "_catalog_state",
        lambda _bind, _spec, _schema: state._replace(default_sql=None),
    )
    with pytest.raises(RuntimeError, match="missing server default"):
        migration.downgrade()
