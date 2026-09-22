"""Regression contracts for the third BE-02 dual-default migration phase.

Phase one (``202609150001``) converged the authentication booleans and is
guarded by ``tests/test_be02_auth_defaults_migration.py``.  This phase takes
ADR-036's next class -- literal, non-secret scalar defaults -- and needs the
same two guarantees: the migration and the mapped columns agree on every
literal, and the phased safety structure the ADR mandates is actually present
in the migration body.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from sqlalchemy.dialects import postgresql

import app.models  # noqa: F401  # register all mapped metadata
from app.core.database import Base

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "alembic" / "versions"
MIGRATION = VERSIONS / "202609220001_phase_literal_scalar_defaults.py"


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("be02_literal_scalars", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_literal_scalar_phase_is_dual_declared() -> None:
    """Every column this phase touches carries both defaults on the model.

    A migration that installs a catalog default the model does not declare is
    worse than no migration at all: autogenerate then reports drift on every
    run and proposes dropping the default the phase just installed.
    """

    for spec in _load_migration().DEFAULT_SPECS:
        column = Base.metadata.tables[spec.table].c[spec.column]
        qualified = f"{spec.table}.{spec.column}"
        assert column.default is not None, qualified
        assert column.server_default is not None, qualified


def test_declared_literals_match_the_python_defaults() -> None:
    """The transcribed literal is the scalar the ORM already applies."""

    for spec in _load_migration().DEFAULT_SPECS:
        column = Base.metadata.tables[spec.table].c[spec.column]
        qualified = f"{spec.table}.{spec.column}"
        python_default = column.default.arg
        assert not callable(python_default), qualified

        # The migration writes PostgreSQL syntax ('pending', true, 0.0); the
        # model carries the plain literal.  Compare them after stripping the
        # SQL quoting the two spellings differ by.
        migration_literal = spec.server_default.strip("'")
        model_literal = str(column.server_default.arg)
        assert model_literal == migration_literal, qualified

        if spec.family == "boolean":
            assert migration_literal == str(bool(python_default)).lower(), qualified
        else:
            assert migration_literal == str(python_default), qualified


def test_every_spec_targets_a_reviewed_type_family() -> None:
    migration = _load_migration()
    families = {spec.family for spec in migration.DEFAULT_SPECS}

    assert families <= set(migration._TYPE_FAMILIES)
    assert len(migration.DEFAULT_SPECS) == len(
        {(spec.table, spec.column) for spec in migration.DEFAULT_SPECS}
    )


def test_migration_keeps_the_phased_safety_contract() -> None:
    source = MIGRATION.read_text(encoding="utf-8").lower()
    for required in (
        "pg_get_expr",
        "pg_attribute",
        "statement_timeout",
        "lock_timeout",
        "not valid",
        "validate constraint",
        "set not null",
        "backfill",
        "requires online postgresql catalog preflight",
    ):
        assert required in source, required


def test_migration_revision_is_the_single_head() -> None:
    migration = _load_migration()

    assert migration.revision == "202609220001"
    assert migration.down_revision == "202609150001"

    # Nothing may be stacked on top of this revision without revisiting the
    # phase: the inventory policy pins ``migration_head`` to it.
    pattern = re.compile(r'^down_revision[^=]*=\s*"202609220001"', re.MULTILINE)
    successors = [
        path.name
        for path in VERSIONS.glob("*.py")
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert successors == []


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
def test_conflicting_text_default_is_rejected(default_sql: str) -> None:
    migration = _load_migration()
    spec = migration.DefaultSpec("dead_letter_jobs", "status", "'pending'", "text")
    state = migration.CatalogState("character varying(20)", True, default_sql)

    with pytest.raises(RuntimeError, match="conflicting server default"):
        migration._validate_existing_default(spec, state)


@pytest.mark.parametrize(
    ("family", "literal", "default_sql"),
    [
        ("text", "'pending'", "'pending'::character varying"),
        ("text", "'pending'", " (( 'pending' ) :: CHARACTER VARYING) "),
        ("text", "'pending'", "(('pending'::text)::character varying)"),
        ("text", "'pending'", "((('pending')))"),
        ("text", "'Pending now'", "('Pending now'::text)"),
        ("text", "'pen''ding'", "('pen''ding'::text)"),
        ("text", "'0.0'", "'0.0'::text"),
        ("boolean", "true", "(TRUE::boolean)"),
        ("boolean", "false", "false"),
        ("integer", "3", "('3'::integer)"),
        ("float", "0.0", "'0'::double precision"),
        ("float", "0.0", "((0.0)::numeric)"),
    ],
)
def test_equivalent_scalar_default_is_preserved(
    family: str, literal: str, default_sql: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    migration = _load_migration()
    spec = migration.DefaultSpec("example", "value", literal, family)
    state = migration.CatalogState("text", True, default_sql)
    ddl = Mock()
    monkeypatch.setattr(migration, "_execute_ddl", ddl)

    migration._validate_existing_default(spec, state)
    migration._set_server_default(None, spec, state)

    ddl.assert_not_called()


@pytest.mark.parametrize("default_sql", ["'0'::text", "'0.00'::text"])
def test_numeric_text_literals_are_not_numeric_defaults(default_sql: str) -> None:
    migration = _load_migration()
    spec = migration.DefaultSpec("example", "value", "'0.0'", "text")
    state = migration.CatalogState("text", True, default_sql)

    with pytest.raises(RuntimeError, match="conflicting server default"):
        migration._validate_existing_default(spec, state)


@pytest.mark.parametrize("operation", ["upgrade", "downgrade"])
@pytest.mark.parametrize("default_sql", ["'PENDING'::text", "'pen ding'::text"])
def test_preflight_rejects_conflict_without_mutation(
    operation: str, default_sql: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    migration = _load_migration()
    safe = migration.DefaultSpec("example", "count", "0", "integer")
    conflicting = migration.DefaultSpec(
        "dead_letter_jobs", "status", "'pending'", "text"
    )
    monkeypatch.setattr(migration, "DEFAULT_SPECS", (safe, conflicting))
    monkeypatch.setattr(
        migration,
        "_catalog_state",
        lambda _bind, spec: migration.CatalogState(
            "text", True, None if spec == safe else default_sql
        ),
    )
    bind = SimpleNamespace(dialect=postgresql.dialect())
    monkeypatch.setattr(migration.op, "get_bind", lambda: bind)
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(migration, "_lock_postgresql", lambda: None)
    monkeypatch.setattr(migration, "_constraint_rows", lambda *_args: [])
    backfill = Mock()
    ddl = Mock()
    monkeypatch.setattr(migration, "_backfill_nulls", backfill)
    monkeypatch.setattr(migration, "_execute_ddl", ddl)

    with pytest.raises(RuntimeError, match="conflicting server default"):
        getattr(migration, operation)()

    backfill.assert_not_called()
    ddl.assert_not_called()
