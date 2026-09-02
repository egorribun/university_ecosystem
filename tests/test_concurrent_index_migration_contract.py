from __future__ import annotations

import ast
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _inside_autocommit(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    current = parents.get(node)
    while current is not None:
        if isinstance(current, ast.With):
            for item in current.items:
                expression = item.context_expr
                if (
                    isinstance(expression, ast.Call)
                    and isinstance(expression.func, ast.Attribute)
                    and expression.func.attr == "autocommit_block"
                ):
                    return True
        current = parents.get(current)
    return False


def test_every_concurrent_index_operation_uses_alembic_autocommit_block() -> None:
    findings: list[str] = []
    for path in VERSIONS.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            raw_concurrent = (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and (
                    "CREATE INDEX CONCURRENTLY" in node.value
                    or "DROP INDEX CONCURRENTLY" in node.value
                )
            )
            kw_concurrent = (
                isinstance(node, ast.keyword)
                and node.arg == "postgresql_concurrently"
                and not (
                    isinstance(node.value, ast.Constant) and node.value.value is False
                )
            )
            if (raw_concurrent or kw_concurrent) and not _inside_autocommit(
                node, parents
            ):
                findings.append(f"{path.name}:{getattr(node, 'lineno', 0)}")
    assert findings == []
