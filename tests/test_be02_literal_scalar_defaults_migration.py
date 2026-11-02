"""BE-02 scalar defaults on the fresh-only, irreversible MVP baseline.

ADR-051 retires the historical populated-database preflight and backfill.
The retained lazy loaders below are still imported by the separately pending
PostgreSQL integration retarget; unit contracts do not call them.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa
import yaml

import app.models  # noqa: F401  # register all mapped metadata
from app.core.database import Base
from app.core.db.retained_table_metadata import build_migration_metadata
from tests.fixtures.baseline_defaults import (
    SCALAR_DEFAULTS,
    ScalarDefault,
    assert_default_columns,
    replace_column,
)
from tests.fixtures.baseline_migration import capture_baseline

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "alembic" / "versions"
MIGRATION = VERSIONS / "202609220001_phase_literal_scalar_defaults.py"


# Revision 202610010001 retired these runtime models; the historical phase still lists
# their columns, which no longer exist on the models.
RETIRED_RUNTIME_TABLES = frozenset({"user_stats", "vector_chunks"})


def _live_specs() -> list:
    return [
        spec
        for spec in _load_migration().DEFAULT_SPECS
        if spec.table not in RETIRED_RUNTIME_TABLES
    ]


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("be02_literal_scalars", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _runtime_specs() -> tuple[ScalarDefault, ...]:
    return tuple(
        spec
        for spec in SCALAR_DEFAULTS
        if spec.qualified.split(".", 1)[0] not in RETIRED_RUNTIME_TABLES
    )


def test_literal_scalar_phase_is_dual_declared() -> None:
    """The seventeen live scalar defaults still support both writer paths."""
    specs = _runtime_specs()
    assert len(specs) == 17
    for spec in specs:
        table, field = spec.qualified.split(".", 1)
        column = Base.metadata.tables[table].c[field]
        assert column.default is not None, spec.qualified
        assert column.server_default is not None, spec.qualified


def test_declared_literals_match_the_python_defaults() -> None:
    """Do not derive expected values from either model or baseline metadata."""
    for spec in _runtime_specs():
        table, field = spec.qualified.split(".", 1)
        column = Base.metadata.tables[table].c[field]
        assert column.default is not None, spec.qualified
        assert column.server_default is not None, spec.qualified
        value = column.default.arg
        assert not callable(value), spec.qualified
        assert type(value) is type(spec.value), spec.qualified
        assert value == spec.value, spec.qualified
        expected = (
            str(spec.value).lower() if spec.family == "boolean" else str(spec.value)
        )
        assert str(column.server_default.arg) == expected, spec.qualified


def test_every_spec_targets_a_reviewed_type_family() -> None:
    metadata = build_migration_metadata(Base.metadata, dialect_name="postgresql")
    types = {
        "boolean": sa.Boolean,
        "integer": sa.Integer,
        "float": sa.Float,
        "text": sa.String,
    }
    assert len(SCALAR_DEFAULTS) == 29
    assert len({spec.qualified for spec in SCALAR_DEFAULTS}) == 29
    assert Counter(spec.family for spec in SCALAR_DEFAULTS) == {
        "boolean": 7,
        "integer": 11,
        "float": 5,
        "text": 6,
    }
    for spec in SCALAR_DEFAULTS:
        table, field = spec.qualified.split(".", 1)
        column = metadata.tables[table].c[field]
        assert isinstance(column.type, types[spec.family]), spec.qualified
        assert column.nullable is False, spec.qualified
        assert column.server_default is not None, spec.qualified
        expected = (
            str(spec.value).lower() if spec.family == "boolean" else str(spec.value)
        )
        assert str(column.server_default.arg) == expected, spec.qualified
    assert RETIRED_RUNTIME_TABLES.isdisjoint(Base.metadata.tables)
    assert (
        sum(
            spec.qualified.split(".", 1)[0] in RETIRED_RUNTIME_TABLES
            for spec in SCALAR_DEFAULTS
        )
        == 12
    )


def test_baseline_scalar_defaults_use_bounded_fresh_schema_ddl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, operations = capture_baseline(monkeypatch)
    assert_default_columns(
        operations.statements,
        {spec.qualified: spec.declaration for spec in SCALAR_DEFAULTS},
    )
    assert operations.statements[:2] == [
        "SET LOCAL lock_timeout = '10s'",
        "SET LOCAL statement_timeout = '60s'",
    ]


def test_migration_revision_is_the_single_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, _ = capture_baseline(monkeypatch)
    assert migration.revision == "202611020000"
    assert migration.down_revision is None
    assert sorted(path.name for path in VERSIONS.glob("*.py")) == [
        "202611020000_mvp_baseline.py"
    ]


def test_postgresql_regressions_are_collected_by_the_enabled_integration_lane() -> None:
    integration_test = ROOT / "tests/integration/test_be02_literal_defaults_postgres.py"
    assert integration_test.is_file()
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/reusable-backend-tests.yml").read_text(
            encoding="utf-8"
        )
    )
    triggers = workflow.get("on", workflow.get(True))
    pattern = triggers["workflow_call"]["inputs"]["integration-test-pattern"]["default"]
    assert integration_test.is_relative_to(ROOT / pattern)
    job = workflow["jobs"]["integration-tests"]
    assert job["env"]["RUN_INTEGRATION_TESTS"] == "1"
    assert job["env"]["DATABASE_URL"].startswith("postgresql+asyncpg://")
    step = next(
        step for step in job["steps"] if step.get("name") == "Run integration tests"
    )
    assert (
        step["env"]["INTEGRATION_TEST_PATTERN"]
        == "${{ inputs.integration-test-pattern }}"
    )
    assert "$env:INTEGRATION_TEST_PATTERN" in step["run"]


@pytest.mark.parametrize(
    "default_sql",
    [
        "'PENDING'::character varying",
        "'pen ding'::character varying",
        "' pending'::text",
        "'pending '::text",
        "'pen\tding'::text",
        "'pen\"ding'::text",
        "'pen''ding'::text",
        "(('pending')::character varying(3))",
        "'pending'::citext",
        "lower('PENDING'::text)",
        "pending",
        "('pending'",
        "'pending')",
        "true",
        "'pending' || ''",
    ],
)
def test_conflicting_text_default_is_rejected(
    default_sql: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    expected = {
        "dead_letter_jobs.status": (
            "status character varying(20) DEFAULT 'pending'::character varying NOT NULL"
        )
    }
    changed = replace_column(
        operations.statements,
        "dead_letter_jobs",
        expected["dead_letter_jobs.status"],
        f"status character varying(20) DEFAULT {default_sql} NOT NULL",
    )
    with pytest.raises(AssertionError):
        assert_default_columns(changed, expected)


@pytest.mark.parametrize("spec", SCALAR_DEFAULTS, ids=lambda spec: spec.qualified)
def test_baseline_scalar_defaults_match_reviewed_physical_columns(
    spec: ScalarDefault, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    assert_default_columns(operations.statements, {spec.qualified: spec.declaration})


@pytest.mark.parametrize("default_sql", ["'0'::text", "'0.00'::text"])
def test_numeric_text_literals_are_not_numeric_defaults(
    default_sql: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    expected = {
        "user_stats.attendance_percent": (
            "attendance_percent double precision DEFAULT '0'::double precision NOT NULL"
        )
    }
    changed = replace_column(
        operations.statements,
        "user_stats",
        expected["user_stats.attendance_percent"],
        f"attendance_percent text DEFAULT {default_sql} NOT NULL",
    )
    with pytest.raises(AssertionError):
        assert_default_columns(changed, expected)


@pytest.mark.parametrize(
    ("qualified", "before", "after"),
    [
        (
            "events.is_active",
            "is_active boolean DEFAULT true NOT NULL",
            "is_active boolean DEFAULT false NOT NULL",
        ),
        (
            "dead_letter_jobs.max_retries",
            "max_retries integer DEFAULT 3 NOT NULL",
            "max_retries integer DEFAULT 4 NOT NULL",
        ),
        (
            "user_stats.grades_average",
            "grades_average double precision DEFAULT '0'::double precision NOT NULL",
            "grades_average double precision DEFAULT '1'::double precision NOT NULL",
        ),
        (
            "vector_chunks.is_active",
            "is_active boolean DEFAULT true NOT NULL",
            "is_active boolean DEFAULT true",
        ),
        (
            "stored_events.version",
            "version integer DEFAULT 1 NOT NULL",
            "version integer NOT NULL",
        ),
    ],
    ids=(
        "boolean-value",
        "counter-value",
        "retained-float",
        "retained-nullability",
        "missing-default",
    ),
)
def test_baseline_scalar_contract_rejects_changed_values_or_nullability(
    qualified: str, before: str, after: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    changed = replace_column(
        operations.statements, qualified.split(".", 1)[0], before, after
    )
    with pytest.raises(AssertionError):
        assert_default_columns(changed, {qualified: before})


@pytest.mark.parametrize(
    "extra",
    [
        "ALTER TABLE public.dead_letter_jobs ALTER COLUMN status SET DEFAULT 'PENDING'",
        "ALTER TABLE dead_letter_jobs ALTER COLUMN status DROP DEFAULT",
        'alter table "public"."dead_letter_jobs" alter column "status" drop not null',
        "ALTER TABLE public.user_stats ALTER COLUMN attendance_percent SET DEFAULT 1",
        "ALTER TABLE public.vector_chunks ALTER COLUMN is_active DROP DEFAULT",
        "ALTER TABLE public.vector_chunks RENAME TO retired_chunks",
        "ALTER TABLE public.dead_letter_jobs SET SCHEMA archive",
    ],
)
def test_baseline_scalar_contract_rejects_later_overrides(
    extra: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    expected = {spec.qualified: spec.declaration for spec in SCALAR_DEFAULTS}
    with pytest.raises(AssertionError):
        assert_default_columns([*operations.statements, extra], expected)


@pytest.mark.parametrize(
    "defect", ["missing-column", "duplicate-column", "missing-table", "duplicate-table"]
)
def test_baseline_scalar_contract_rejects_missing_or_duplicate_objects(
    defect: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    expected = {"vector_chunks.chunk_index": "chunk_index integer DEFAULT 0 NOT NULL"}
    declaration = expected["vector_chunks.chunk_index"]
    if defect == "missing-column":
        changed = replace_column(
            operations.statements, "vector_chunks", declaration + ",\n", ""
        )
    elif defect == "duplicate-column":
        changed = replace_column(
            operations.statements,
            "vector_chunks",
            declaration,
            declaration + ",\n    " + declaration,
        )
    else:
        changed = list(operations.statements)
        create = next(
            sql
            for sql in changed
            if sql.startswith("CREATE TABLE public.vector_chunks (")
        )
        if defect == "missing-table":
            changed.remove(create)
        else:
            changed.append(create)
    with pytest.raises(AssertionError):
        assert_default_columns(changed, expected)


@pytest.mark.parametrize(
    "wrapper",
    [
        "/*\n{declaration}\n*/",
        "decoy text DEFAULT '\n{declaration}\n'",
        "decoy text DEFAULT $payload$\n{declaration}\n$payload$",
        '"\n{declaration}\n" integer',
        "decoy text DEFAULT E'\\'\n{declaration}\n\\''",
    ],
    ids=(
        "block-comment",
        "multiline-string",
        "dollar-quoted-string",
        "multiline-identifier",
        "escaped-multiline-string",
    ),
)
def test_baseline_scalar_contract_rejects_hidden_column_payloads(
    wrapper: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    declaration = "chunk_index integer DEFAULT 0 NOT NULL"
    changed = replace_column(
        operations.statements,
        "vector_chunks",
        declaration,
        wrapper.format(declaration=declaration),
    )
    with pytest.raises(AssertionError):
        assert_default_columns(changed, {"vector_chunks.chunk_index": declaration})


@pytest.mark.parametrize("table", ["notifications", "notification_deliveries"])
def test_baseline_scalar_contract_accepts_partitioned_parent_with_children(
    table: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    children = [
        sql
        for sql in operations.statements
        if sql.startswith(f"CREATE TABLE public.{table}_")
        and f"PARTITION OF public.{table}" in sql
    ]
    assert children, f"The positive control must contain {table} partition children"
    expected = {
        spec.qualified: spec.declaration
        for spec in SCALAR_DEFAULTS
        if spec.qualified.split(".", 1)[0] == table
    }
    assert_default_columns(operations.statements, expected)


@pytest.mark.parametrize("table", ["notifications", "notification_deliveries"])
def test_baseline_scalar_contract_rejects_duplicate_partitioned_parent(
    table: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    create = next(
        sql
        for sql in operations.statements
        if sql.startswith(f"CREATE TABLE public.{table} (")
    )
    expected = {
        spec.qualified: spec.declaration
        for spec in SCALAR_DEFAULTS
        if spec.qualified.split(".", 1)[0] == table
    }
    with pytest.raises(AssertionError):
        assert_default_columns([*operations.statements, create], expected)


@pytest.mark.parametrize(
    "extra",
    [
        r'ALTER TABLE public.events ALTER COLUMN U&"is_\0061ctive" '
        "SET DEFAULT false",
        r'ALTER TABLE public.U&"\0065vents" ALTER COLUMN is_active '
        "SET DEFAULT false",
        'ALTER TABLE public.U&"ev!0065nts" '
        "UESCAPE '!' ALTER COLUMN is_active SET DEFAULT false",
    ],
    ids=("encoded-column", "encoded-table", "explicit-escape-character"),
)
def test_baseline_scalar_contract_rejects_encoded_identifier_overrides(
    extra: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    expected = {"events.is_active": "is_active boolean DEFAULT true NOT NULL"}
    with pytest.raises(AssertionError):
        assert_default_columns([*operations.statements, extra], expected)
