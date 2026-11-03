"""AUD-434: `alembic check` must compare server defaults in the online context.

`alembic -c alembic.ini check` runs the online configuration in
`_configure_context`. The test statically inspects the single `context.configure`
call there, without importing env.py, which runs migrations at import time.
"""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

import app.models as models
from app.core.db.retained_table_metadata import build_migration_metadata

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "alembic" / "env.py"
BASELINE_FILE = ROOT / "alembic" / "versions" / "202611020000_mvp_baseline.py"


def _online_configure_keywords() -> dict[str, ast.expr]:
    tree = ast.parse(ENV_FILE.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_configure_context"
    )
    calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "configure"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "context"
    ]
    assert len(calls) == 1
    return {keyword.arg: keyword.value for keyword in calls[0].keywords if keyword.arg}


def _is_constant(value: ast.expr | None, expected: object) -> bool:
    return isinstance(value, ast.Constant) and value.value is expected


def test_online_context_compares_server_defaults_for_alembic_check() -> None:
    keywords = _online_configure_keywords()
    assert _is_constant(keywords.get("compare_server_default"), True)


def test_online_context_keeps_its_existing_comparison_options() -> None:
    keywords = _online_configure_keywords()
    for name in (
        "compare_type",
        "render_as_batch",
        "transactional_ddl",
        "transaction_per_migration",
    ):
        assert _is_constant(keywords.get(name), True), name
    assert {"include_object", "process_revision_directives"} <= keywords.keys()


class _PostgresBind:
    class dialect:
        name = "postgresql"

    def execute(self, _statement: Any) -> Any:
        return SimpleNamespace(fetchone=lambda: None)


class _RecordingOp:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def get_bind(self) -> _PostgresBind:
        return _PostgresBind()

    def execute(self, statement: Any) -> None:
        self.statements.append(str(statement))


def _baseline_create_table(table: str) -> str:
    spec = importlib.util.spec_from_file_location(
        "baseline_default_probe", BASELINE_FILE
    )
    assert spec is not None and spec.loader is not None
    module: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    recorder = _RecordingOp()
    module.op = recorder
    module.upgrade()
    prefix = f"CREATE TABLE public.{table} ("
    created = [
        statement for statement in recorder.statements if statement.startswith(prefix)
    ]
    assert len(created) == 1, table
    return created[0]


def _topics_default(create_table: str) -> str:
    lines = [line.strip() for line in create_table.splitlines()]
    topics = [line for line in lines if line.startswith("topics ")]
    assert len(topics) == 1, create_table
    match = re.search(r"DEFAULT (.+) NOT NULL", topics[0], re.IGNORECASE)
    assert match is not None, topics[0]
    return match.group(1)


def test_push_subscription_topics_default_agrees_between_model_and_baseline() -> None:
    """AUD-434: the model and the baseline spell one PostgreSQL default for topics."""
    metadata = build_migration_metadata(models.Base.metadata, dialect_name="postgresql")
    model_table = metadata.tables["push_subscriptions"]
    model_ddl = str(CreateTable(model_table).compile(dialect=postgresql.dialect()))

    model_default = _topics_default(model_ddl)
    baseline_default = _topics_default(_baseline_create_table("push_subscriptions"))

    assert model_default == baseline_default == "'[]'::json"
