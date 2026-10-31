"""Read literal Alembic graph metadata without executing migration code.

This pure API does not change the legacy single-parent reader or CLI, render SQL,
or admit a database. Callers own source collection and input-size limits. The
result describes literal declarations, not arbitrary Python execution semantics
or an approved migration execution plan.
"""

from __future__ import annotations

import ast

_METADATA_NAMES = frozenset(
    {"revision", "down_revision", "branch_labels", "depends_on"}
)


def _literal_identifier(value: ast.expr | None) -> str:
    if (
        not isinstance(value, ast.Constant)
        or not isinstance(value.value, str)
        or not value.value.strip()
    ):
        raise ValueError("revision identifiers must be nonempty string literals")
    return value.value


def _read_source(source: str) -> tuple[str, tuple[str, ...]]:
    module = ast.parse(source)
    declarations: dict[str, ast.expr] = {}
    allowed_stores: set[int] = set()
    for node in module.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.simple == 1:
            target, value = node.target, node.value
        else:
            continue
        if not isinstance(target, ast.Name) or target.id not in _METADATA_NAMES:
            continue
        if target.id in declarations or value is None:
            raise ValueError("metadata declarations must be unambiguous")
        declarations[target.id] = value
        allowed_stores.add(id(target))

    # Reject direct rebinding, including nested/chained/destructured assignments,
    # augmented assignment, deletion and named expressions. Never execute source.
    for node in ast.walk(module):
        if (
            isinstance(node, ast.Name)
            and node.id in _METADATA_NAMES
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and id(node) not in allowed_stores
        ):
            raise ValueError("metadata requires one top-level single-name assignment")
        if isinstance(node, ast.alias):
            binding = node.asname or node.name.split(".")[0]
            if binding in _METADATA_NAMES or node.name == "*":
                raise ValueError("imports cannot bind metadata names")
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.ExceptHandler,
                ast.MatchAs,
                ast.MatchStar,
            ),
        ):
            if node.name in _METADATA_NAMES:
                raise ValueError("metadata cannot be rebound")
        if isinstance(node, ast.MatchMapping) and node.rest in _METADATA_NAMES:
            raise ValueError("metadata cannot be rebound")

    if not {"revision", "down_revision"} <= declarations.keys():
        raise ValueError("revision and parent declarations are required")
    for name in ("branch_labels", "depends_on"):
        optional = declarations.get(name)
        if optional is not None and not (
            isinstance(optional, ast.Constant) and optional.value is None
        ):
            raise ValueError("branch labels and dependencies are not supported")

    revision = _literal_identifier(declarations["revision"])
    value = declarations["down_revision"]
    if isinstance(value, ast.Constant) and value.value is None:
        parents: tuple[str, ...] = ()
    elif isinstance(value, ast.Tuple):
        if len(value.elts) < 2:
            raise ValueError("merge declarations need at least two parents")
        parents = tuple(_literal_identifier(parent) for parent in value.elts)
    else:
        parents = (_literal_identifier(value),)
    if len(set(parents)) != len(parents):
        raise ValueError("duplicate parents are not allowed")
    return revision, parents


def read_revision_graph(
    sources: dict[str, str],
) -> dict[str, tuple[str, ...]] | None:
    """Return literal revision-to-parent edges, or None for an invalid graph."""
    if type(sources) is not dict or not sources:
        return None
    graph: dict[str, tuple[str, ...]] = {}
    try:
        for name, source in sources.items():
            if type(name) is not str or not name or type(source) is not str:
                return None
            revision, parents = _read_source(source)
            if revision in graph:
                return None
            graph[revision] = parents
    except (SyntaxError, TypeError, ValueError, RecursionError):
        return None

    if any(parent not in graph for parents in graph.values() for parent in parents):
        return None

    # Count dependency edges without recursion. This only checks for cycles; no
    # execution ordering or SQL adapter is returned to the caller.
    remaining = {revision: len(parents) for revision, parents in graph.items()}
    children: dict[str, list[str]] = {revision: [] for revision in graph}
    for revision, parents in graph.items():
        for parent in parents:
            children[parent].append(revision)
    ready = [revision for revision, count in remaining.items() if count == 0]
    visited = 0
    while ready:
        parent = ready.pop()
        visited += 1
        for child in children[parent]:
            remaining[child] -= 1
            if remaining[child] == 0:
                ready.append(child)
    return graph if visited == len(graph) else None
