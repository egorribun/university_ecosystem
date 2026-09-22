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
from types import ModuleType

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
