"""Regression contracts for the PostgreSQL-safe 148642dd1207 migration."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic" / "versions" / "148642dd1207_fix_missing_tables.py"


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
    assert (
        "ALTER TABLE ACTIVE_SESSIONS ALTER COLUMN SIGNING_KEY SET NOT NULL" not in sql
    )
    assert "ID__INTEGER INTEGER" in sql
    assert "CHECK (ID__INTEGER IS NOT NULL) NOT VALID" in sql
    assert "CHECK (ID IS NOT NULL) NOT VALID" in sql
    assert "VALIDATE CONSTRAINT CK_GROUPS_ID_SHADOW_NOT_NULL" in sql
    assert "VALIDATE CONSTRAINT CK_GROUPS_ID_NOT_NULL" in sql
    assert "VALIDATE CONSTRAINT CK_ACTIVE_SESSIONS_SIGNING_KEY_NOT_NULL" in sql
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
