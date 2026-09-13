"""Regression contracts for the PostgreSQL-safe 148642dd1207 migration."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic" / "versions" / "148642dd1207_fix_missing_tables.py"


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("migration_148642dd1207", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _render(direction: str) -> str:
    """Render one migration direction with PostgreSQL's offline dialect."""

    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql+asyncpg://migration@localhost:5432/test"
    result = subprocess.run(  # noqa: S603 - fixed local Alembic module invocation
        [
            sys.executable,
            "-m",
            "alembic",
            *direction.split(),
            "--sql",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.upper()


def test_upgrade_uses_validated_shadow_cutover_for_groups_and_sessions() -> None:
    sql = _render("upgrade f7aa476e968a:148642dd1207")

    assert "ALTER TABLE GROUPS ALTER COLUMN ID TYPE" not in sql
    # PostgreSQL receives the same physical NOT NULL invariant as the other
    # supported dialects, but only after the validated check-backed preflight.
    assert "ALTER TABLE ACTIVE_SESSIONS ALTER COLUMN SIGNING_KEY SET NOT NULL" in sql
    assert "ID__INTEGER INTEGER" in sql
    assert "CHECK (ID__INTEGER IS NOT NULL) NOT VALID" in sql
    assert "CHECK (ID IS NOT NULL) NOT VALID" in sql
    assert "VALIDATE CONSTRAINT CK_GROUPS_ID_SHADOW_NOT_NULL" in sql
    assert "VALIDATE CONSTRAINT CK_GROUPS_ID_NOT_NULL" in sql
    assert "VALIDATE CONSTRAINT CK_ACTIVE_SESSIONS_SIGNING_KEY_NOT_NULL" in sql
    assert sql.index(
        "VALIDATE CONSTRAINT CK_ACTIVE_SESSIONS_SIGNING_KEY_NOT_NULL"
    ) < sql.index("ALTER TABLE ACTIVE_SESSIONS ALTER COLUMN SIGNING_KEY SET NOT NULL")
    assert "PRIMARY KEY USING INDEX GROUPS_PKEY_IDX" in sql
    assert "RENAME COLUMN" not in sql


def test_downgrade_restores_legacy_shape_without_in_place_type_change() -> None:
    sql = _render("downgrade 148642dd1207:f7aa476e968a")

    assert "ALTER TABLE GROUPS ALTER COLUMN ID TYPE" not in sql
    assert "RENAME COLUMN" not in sql
    assert "ID__VARCHAR VARCHAR(20)" in sql
    assert "UPDATE GROUPS SET ID__VARCHAR" in sql
    assert "PRIMARY KEY USING INDEX GROUPS_PKEY_IDX" in sql
    assert "DROP CONSTRAINT IF EXISTS CK_ACTIVE_SESSIONS_SIGNING_KEY_NOT_NULL" in sql
    assert "ALTER TABLE ACTIVE_SESSIONS ALTER COLUMN SIGNING_KEY DROP NOT NULL" in sql


def test_fk_conversion_preflight_uses_a_short_circuit_numeric_cast() -> None:
    """Invalid child keys must fail before PostgreSQL can evaluate a cast."""

    source = MIGRATION.read_text(encoding="utf-8")

    assert "CASE WHEN CAST(%I AS text) ~ ''^[0-9]+$''" in source
    assert "THEN CAST(%I AS numeric) > 2147483647" in source
    assert "OR CAST(%I AS numeric) > 2147483647))" not in source
    assert 'target_type not in {"INTEGER", "VARCHAR(20)"}' in source
    # The following UUID migration owns the id -> legacy_id rename.  Keeping
    # that column in 148642dd1207 would make the later cutover fail with a
    # duplicate-column error.
    assert "legacy_id" not in source


def test_fk_capture_preserves_non_id_mapping_and_rejects_composites() -> None:
    """The groups swap must never retarget a non-id FK to the new primary key."""

    source = MIGRATION.read_text(encoding="utf-8")

    assert "HAVING bool_or(parent.attname = 'id')" in source
    assert "fk.parent_names[ordinal] <> 'id'" in source
    assert "_reject_composite_groups_foreign_keys()" in source
    # Parent columns are captured from pg_catalog and restored verbatim; the
    # old implementation rewrote every relation to ``groups(id)``.
    assert "parent_columns = ARRAY['id']" not in source


def test_existing_not_null_constraint_definition_is_normalized_exactly() -> None:
    migration = _load_migration()

    expected = migration._normalize_constraint_definition(
        "CHECK ((id__integer IS NOT NULL))"
    )
    assert expected == "CHECKID__INTEGERISNOTNULL"
    assert migration._normalize_constraint_definition("CHECK (id__integer > 0)") != (
        expected
    )


def test_existing_not_null_constraint_mismatch_fails_closed(
    monkeypatch,
) -> None:
    migration = _load_migration()

    class _Dialect:
        name = "postgresql"

    class _Result:
        def first(self):
            return ("c", True, "CHECK ((id__integer > 0))")

    class _Bind:
        dialect = _Dialect()

        def execute(self, *_args, **_kwargs):
            return _Result()

    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(migration.op, "get_bind", lambda: _Bind())

    with pytest.raises(RuntimeError, match="does not match"):
        migration._ensure_postgresql_not_null_check(
            "groups", "ck_groups_id_shadow_not_null", "id__integer"
        )


def test_existing_not_null_constraint_accepts_asyncpg_char_bytes(monkeypatch) -> None:
    migration = _load_migration()

    class _Dialect:
        name = "postgresql"

    class _Result:
        def first(self):
            return (b"c", True, "CHECK ((id__integer IS NOT NULL))")

    class _Bind:
        dialect = _Dialect()

        def execute(self, *_args, **_kwargs):
            return _Result()

    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(migration.op, "get_bind", lambda: _Bind())
    migration._ensure_postgresql_not_null_check(
        "groups", "ck_groups_id_shadow_not_null", "id__integer"
    )


def test_groups_shadow_cutover_is_bounded_and_rejects_stale_leftovers() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "SET LOCAL lock_timeout = '10s'" in source
    assert "pg_advisory_xact_lock" in source
    assert "id__integer IS DISTINCT FROM id::integer" in source
    assert "id__varchar IS DISTINCT FROM id::varchar(20)" in source
    assert "c.contype, c.convalidated, pg_get_constraintdef(c.oid)" in source
