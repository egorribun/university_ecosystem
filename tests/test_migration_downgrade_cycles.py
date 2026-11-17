from __future__ import annotations

from pathlib import Path

import pytest

from scripts.quality.migration_downgrade_policy import (
    PolicyError,
    build_downgrade_plan,
)


def _write_graph(
    directory: Path, parents: dict[str, str | tuple[str, ...] | None]
) -> None:
    for revision, parent in parents.items():
        (directory / f"{revision}.py").write_text(
            f"revision = {revision!r}\ndown_revision = {parent!r}\n"
            "\ndef upgrade():\n    pass\n\ndef downgrade():\n    pass\n",
            encoding="utf-8",
        )


@pytest.mark.parametrize(
    "parents",
    [
        {"head": "a", "a": "a"},
        {"head": "a", "a": "b", "b": "a"},
        {"head": ("base1", "a"), "base1": None, "a": "b", "b": "a"},
    ],
)
def test_reachable_cycle_cannot_produce_a_safe_downgrade_target(
    tmp_path: Path, parents: dict[str, str | tuple[str, ...] | None]
) -> None:
    _write_graph(tmp_path, parents)

    with pytest.raises(PolicyError, match="cycle"):
        build_downgrade_plan(tmp_path)


def test_shared_ancestor_is_not_a_cycle(tmp_path: Path) -> None:
    _write_graph(
        tmp_path,
        {
            "base1": None,
            "left": "base1",
            "right": "base1",
            "head": ("left", "right"),
        },
    )

    plan = build_downgrade_plan(tmp_path)

    assert plan.head_revision == "head"
    assert plan.safe_target == "base"
    assert plan.boundary_revision is None
