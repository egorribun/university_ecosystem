"""AUD-434: `alembic check` must compare server defaults in the online context.

`alembic -c alembic.ini check` runs the online configuration in
`_configure_context`. The test statically inspects the single `context.configure`
call there, without importing env.py, which runs migrations at import time.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "alembic" / "env.py"


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
