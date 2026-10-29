"""Tests-first metadata graph prerequisite; no SQL or database admission proof."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from scripts.quality import read_alembic_graph as graph_reader
from scripts.quality import read_alembic_revision as legacy_reader

ROOT = Path(__file__).resolve().parents[1]


def _source(
    revision: str, parents: str | tuple[str, ...] | None, *, annotated: bool = False
) -> str:
    revision_annotation = ": str" if annotated else ""
    parent_annotation = ": str | tuple[str, ...] | None" if annotated else ""
    return (
        f"revision{revision_annotation} = {revision!r}\n"
        f"down_revision{parent_annotation} = {parents!r}\n"
        "branch_labels = None\n"
        "depends_on = None\n"
    )


def _example(
    parent_count: int = 2, *, annotated: bool = False
) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    parents = ("left", "right", "third")[:parent_count]
    expected = {"root": (), **{parent: ("root",) for parent in parents}}
    expected["head"] = parents
    sources = {
        f"{revision}.py": _source(
            revision,
            None if not links else links[0] if len(links) == 1 else links,
            annotated=annotated,
        )
        for revision, links in expected.items()
    }
    return sources, expected


def _valid_control() -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    sources, expected = _example()
    matched = graph_reader.read_revision_graph(sources) == expected
    assert matched, "the literal graph positive control did not match"
    return sources, expected


@pytest.mark.parametrize("parent_count", [2, 3])
@pytest.mark.parametrize("annotated", [False, True])
def test_literal_roots_linear_edges_and_merges_are_read_without_execution(
    parent_count: int, annotated: bool
) -> None:
    sources, expected = _example(parent_count, annotated=annotated)
    # Valid Python with deliberately impossible imports and an execution trap.
    # A metadata reader must parse, never import or execute, migration modules.
    sources["head.py"] += (
        "import nonexistent_graph_metadata_probe_module\n"
        "raise AssertionError('migration source must not execute')\n"
    )
    before = dict(sources)
    assert graph_reader.read_revision_graph(sources) == expected
    assert sources == before


def test_source_mapping_order_does_not_change_parent_order_or_graph() -> None:
    sources, expected = _valid_control()
    sources = dict(reversed(list(sources.items())))
    sources["head.py"] = _source("head", ("right", "left"))
    expected["head"] = ("right", "left")
    assert graph_reader.read_revision_graph(sources) == expected


@pytest.mark.parametrize(
    "metadata",
    [
        "down_revision = 'left'\n",
        "revision = 'head'\n",
        "revision = 'head'\nrevision = 'other'\ndown_revision = 'left'\n",
        "revision = 'head'\ndown_revision = 'left'\ndown_revision = 'right'\n",
        "revision = make_revision()\ndown_revision = 'left'\n",
        "revision = 'head'\ndown_revision = make_parent()\n",
        "revision = 'head'\ndown_revision = ('left', make_parent())\n",
        "revision = 'head'\ndown_revision = ['left', 'right']\n",
        "revision = 'head'\ndown_revision = ()\n",
        "revision = 'head'\ndown_revision = ('left',)\n",
        "revision = ''\ndown_revision = 'left'\n",
        "revision = 'head'\ndown_revision = ''\n",
        "revision = 'head'\ndown_revision = ('left', '')\n",
        "revision = True\ndown_revision = 'left'\n",
        "revision = 'head'\ndown_revision = 7\n",
        "revision = 'head'\ndown_revision = ('left', None)\n",
        "if enabled:\n    revision = 'head'\ndown_revision = 'left'\n",
        "def metadata():\n    revision = 'head'\ndown_revision = 'left'\n",
        "revision = alias = 'head'\ndown_revision = 'left'\n",
        "revision = 'head'\ndown_revision = 'left'\nrevision += '_changed'\n",
        "revision = 'head'\ndown_revision = 'left'\ndel revision\n",
        "revision = 'head'\ndown_revision = 'left'\n(revision := 'other')\n",
        "revision = 'head'\ndown_revision = (*parents, 'right')\n",
        "revision = 'head'\ndown_revision = 'left'\ndepends_on = 'right'\n",
        "revision = 'head'\ndown_revision = 'left'\nbranch_labels = 'alias'\n",
        "revision = 'head'\ndown_revision = 'left'\nif\n",
    ],
    ids=[
        "missing-revision",
        "missing-parent",
        "duplicate-revision-assignment",
        "duplicate-parent-assignment",
        "dynamic-revision",
        "dynamic-parent",
        "dynamic-tuple-item",
        "list-parent",
        "empty-tuple",
        "singleton-tuple",
        "empty-revision",
        "empty-parent",
        "empty-tuple-item",
        "boolean-revision",
        "numeric-parent",
        "null-tuple-item",
        "conditional-assignment",
        "nested-assignment",
        "chained-assignment",
        "augmented-assignment",
        "deleted-metadata",
        "named-expression",
        "starred-tuple",
        "unsupported-dependency",
        "unsupported-alias",
        "syntax-error",
    ],
)
def test_ambiguous_or_dynamic_metadata_cannot_form_a_graph(metadata: str) -> None:
    sources, _ = _valid_control()
    sources["head.py"] = metadata
    assert graph_reader.read_revision_graph(sources) is None


@pytest.mark.parametrize(
    "defect",
    [
        "duplicate-revision",
        "duplicate-parent",
        "missing-parent",
        "self-cycle",
        "two-node-cycle",
        "merge-cycle",
        "empty-inventory",
    ],
)
def test_incomplete_duplicate_or_cyclic_graphs_fail_closed(defect: str) -> None:
    sources, _ = _valid_control()
    if defect == "duplicate-revision":
        sources["duplicate.py"] = _source("head", "left")
    elif defect == "duplicate-parent":
        sources["head.py"] = _source("head", ("left", "left"))
    elif defect == "missing-parent":
        del sources["right.py"]
    elif defect == "self-cycle":
        sources["left.py"] = _source("left", "left")
    elif defect == "two-node-cycle":
        sources["left.py"] = _source("left", "right")
        sources["right.py"] = _source("right", "left")
    elif defect == "merge-cycle":
        sources["left.py"] = _source("left", "head")
    else:
        sources.clear()
    assert graph_reader.read_revision_graph(sources) is None


def test_all_current_migrations_are_retained_in_the_metadata_graph() -> None:
    _valid_control()
    paths = sorted((ROOT / "alembic/versions").glob("*.py"))
    paths = [path for path in paths if path.name != "__init__.py"]
    assert len(paths) == 142
    sources = {path.name: path.read_text(encoding="utf-8") for path in paths}
    expected: dict[str, tuple[str, ...]] = {}
    for name, source in sources.items():
        # Independent fixture oracle: evaluate only the two literal AST values,
        # never compile/import the migration or call its upgrade/downgrade.
        values: dict[str, object] = {}
        for node in ast.parse(source, filename=name).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target, value = node.targets[0], node.value
            elif isinstance(node, ast.AnnAssign):
                target, value = node.target, node.value
            else:
                continue
            if isinstance(target, ast.Name) and target.id in {
                "revision",
                "down_revision",
            }:
                assert target.id not in values
                assert value is not None
                values[target.id] = ast.literal_eval(value)
        revision, parents = values["revision"], values["down_revision"]
        assert isinstance(revision, str) and revision not in expected
        if parents is None:
            expected[revision] = ()
        elif isinstance(parents, str):
            expected[revision] = (parents,)
        else:
            assert isinstance(parents, tuple)
            assert all(isinstance(parent, str) for parent in parents)
            expected[revision] = parents
    assert len(expected) == 142
    assert sum(not parents for parents in expected.values()) == 1
    assert sum(len(parents) == 2 for parents in expected.values()) == 9
    assert sum(len(parents) == 3 for parents in expected.values()) == 1
    parent_ids = {parent for parents in expected.values() for parent in parents}
    assert parent_ids <= expected.keys()
    assert len(expected.keys() - parent_ids) == 1
    assert graph_reader.read_revision_graph(sources) == expected


@pytest.mark.parametrize("parents", [None, "parent", ("left", "right")])
def test_legacy_single_parent_cli_contract_remains_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], parents: object
) -> None:
    path = tmp_path / "migration.py"
    path.write_text(
        f"revision = 'child'\ndown_revision = {parents!r}\n", encoding="utf-8"
    )
    code = legacy_reader.main([str(path)])
    captured = capsys.readouterr()
    if isinstance(parents, tuple):
        assert code == 2
        assert captured.out == ""
        assert "down_revision must be a string literal or None" in captured.err
    else:
        assert code == 0
        assert captured.out == f"child {parents or 'base'}\n"
        assert captured.err == ""


def test_graph_reader_has_no_execution_or_admission_entrypoint() -> None:
    source = inspect.getsource(graph_reader)
    module = ast.parse(source)
    imports = set()
    calls = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.add(node.func.id)
    assert not imports.intersection(
        {"os", "pathlib", "subprocess", "socket", "sqlalchemy", "alembic", "runpy"}
    )
    assert not calls.intersection({"exec", "eval", "compile", "open", "__import__"})
    assert '__name__ == "__main__"' not in source
