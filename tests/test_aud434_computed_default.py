"""AUD-434: Alembic compares the model against the baseline search expression."""

from __future__ import annotations

import ast
import warnings
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic.autogenerate.api import AutogenContext
from alembic.autogenerate.compare.server_defaults import _compare_computed_default
from alembic.migration import MigrationContext
from alembic.operations.ops import AlterColumnOp
from sqlalchemy.dialects import postgresql

import app.models as models
from app.core.db.retained_table_metadata import build_migration_metadata

_BASELINE = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "202611020000_mvp_baseline.py"
)


def _baseline_search_expression() -> str:
    tree = ast.parse(_BASELINE.read_text(encoding="utf-8"))
    tables_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "_TABLES"
    )
    tables = ast.literal_eval(tables_node.value)
    events = next(
        sql for sql in tables if sql.startswith("CREATE TABLE public.events (")
    )
    column = next(
        line.strip()
        for line in events.splitlines()
        if line.strip().startswith("search_vector ")
    )
    prefix = "search_vector tsvector GENERATED ALWAYS AS ("
    suffix = ") STORED,"
    assert column.startswith(prefix) and column.endswith(suffix)
    return column[len(prefix) : -len(suffix)]


def _computed_comparison_warnings(model_column: sa.Column[Any]) -> list[str]:
    metadata = build_migration_metadata(models.Base.metadata, dialect_name="postgresql")
    context = MigrationContext.configure(dialect=postgresql.dialect())
    autogen = AutogenContext(context, metadata=metadata)
    baseline_column = sa.Column(
        "search_vector",
        postgresql.TSVECTOR(),
        sa.Computed(_baseline_search_expression(), persisted=True),
    )
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        _compare_computed_default(
            autogen,
            AlterColumnOp("events", "search_vector"),
            None,
            "events",
            "search_vector",
            baseline_column,
            model_column,
        )
    return [str(item.message) for item in recorded]


def test_event_search_computed_default_matches_baseline_in_alembic() -> None:
    metadata = build_migration_metadata(models.Base.metadata, dialect_name="postgresql")
    assert (
        _computed_comparison_warnings(metadata.tables["events"].c.search_vector) == []
    )


def test_computed_comparator_reports_changed_search_input() -> None:
    metadata = build_migration_metadata(models.Base.metadata, dialect_name="postgresql")
    original = metadata.tables["events"].c.search_vector.computed
    assert original is not None
    expression = str(original.sqltext)
    changed = expression.replace("coalesce(about_en,", "coalesce(about,")
    assert changed != expression
    model_column = sa.Column(
        "search_vector", postgresql.TSVECTOR(), sa.Computed(changed, persisted=True)
    )
    assert _computed_comparison_warnings(model_column) == [
        "Computed default on events.search_vector cannot be modified"
    ]
