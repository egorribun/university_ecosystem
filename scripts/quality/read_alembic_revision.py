"""Read literal Alembic revision metadata without importing migration code."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_METADATA_NAMES = ("revision", "down_revision")


class RevisionMetadataError(ValueError):
    """Raised when migration metadata cannot be resolved unambiguously."""


def _stored_names(target: ast.expr) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.List, ast.Tuple)):
        return {name for element in target.elts for name in _stored_names(element)}
    return set()


def _assignment_details(
    node: ast.Assign | ast.AnnAssign,
) -> tuple[set[str], bool, ast.expr | None]:
    if isinstance(node, ast.AnnAssign):
        names = _stored_names(node.target)
        return names, isinstance(node.target, ast.Name) and node.simple == 1, node.value

    names = {name for target in node.targets for name in _stored_names(target)}
    is_single_name = len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
    return names, is_single_name, node.value


def _read_literal(
    name: str,
    assignments: list[tuple[bool, bool, ast.expr | None]],
) -> str:
    if len(assignments) != 1:
        raise RevisionMetadataError(f"{name} must be assigned exactly once")

    is_top_level, is_single_name, value = assignments[0]
    if not is_top_level:
        raise RevisionMetadataError(f"{name} must be a top-level assignment")
    if not is_single_name:
        raise RevisionMetadataError(f"{name} must use a single-name assignment")

    if (
        name == "down_revision"
        and isinstance(value, ast.Constant)
        and value.value is None
    ):
        return "base"
    if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
        suffix = " or None" if name == "down_revision" else ""
        raise RevisionMetadataError(f"{name} must be a string literal{suffix}")
    if not value.value.strip():
        raise RevisionMetadataError(f"{name} must not be empty")
    return value.value


def read_revision_metadata(path: Path) -> tuple[str, str]:
    """Return ``(revision, down_revision)`` from a migration source file."""

    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RevisionMetadataError(f"cannot read {path}: {exc}") from exc

    try:
        module = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise RevisionMetadataError(
            f"invalid Python syntax in {path}: {exc.msg}"
        ) from exc

    top_level_ids = {id(node) for node in module.body}
    assignments: dict[str, list[tuple[bool, bool, ast.expr | None]]] = {
        name: [] for name in _METADATA_NAMES
    }
    for node in ast.walk(module):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        names, is_single_name, value = _assignment_details(node)
        for name in names.intersection(_METADATA_NAMES):
            assignments[name].append((id(node) in top_level_ids, is_single_name, value))

    revision = _read_literal("revision", assignments["revision"])
    down_revision = _read_literal("down_revision", assignments["down_revision"])
    return revision, down_revision


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print("usage: read_alembic_revision.py MIGRATION", file=sys.stderr)
        return 2

    try:
        revision, down_revision = read_revision_metadata(Path(arguments[0]))
    except RevisionMetadataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(revision, down_revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
