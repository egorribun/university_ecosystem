from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.mutmut_shard_matrix import build_execution_groups_matrix
from scripts.validate_mutmut_group_budgets import (
    GroupBudgetValidationError,
    validate_group_budgets,
)


def _digest(names: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(names)).encode("utf-8")).hexdigest()


def _write_plan(
    root: Path,
    assignments: dict[int, list[str]],
    *,
    expected_shards: int = 4,
) -> Path:
    plan = root / "mutmut-incremental-plan"
    plan.mkdir()
    descriptors: list[dict[str, object]] = []
    all_names: list[str] = []
    for shard_id in range(1, expected_shards + 1):
        names = assignments.get(shard_id, [])
        filename = f"shard-{shard_id:02d}.txt"
        (plan / filename).write_text(
            "".join(f"{name}\n" for name in names), encoding="utf-8", newline="\n"
        )
        descriptors.append(
            {
                "shard_id": shard_id,
                "path": filename,
                "selected_count": len(names),
                "selection_sha256": _digest(names),
                "estimated_load_seconds": float(len(names)),
            }
        )
        all_names.extend(names)
    (plan / "plan-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "num_shards": expected_shards,
                "universe_count": len(all_names),
                "universe_sha256": _digest(all_names),
                "shards": descriptors,
            }
        ),
        encoding="utf-8",
    )
    return plan


def _write_stats(root: Path, functions: list[str], *, duration: float = 1.0) -> Path:
    stats = root / "mutmut-stats.json"
    stats.write_text(
        json.dumps(
            {
                "tests_by_mangled_function_name": {
                    function: [f"tests/test_{index}.py::test_case"]
                    for index, function in enumerate(functions, start=1)
                },
                "duration_by_test": {
                    f"tests/test_{index}.py::test_case": duration
                    for index, _function in enumerate(functions, start=1)
                },
            }
        ),
        encoding="utf-8",
    )
    return stats


def test_group_budget_validation_preserves_logical_inventory_and_materializes_cap(
    tmp_path: Path,
) -> None:
    assignments = {
        1: ["app.alpha.one__mutmut_1"],
        2: ["app.beta.two__mutmut_1"],
        3: ["app.gamma.three__mutmut_1"],
    }
    plan = _write_plan(tmp_path, assignments)
    mutant_names = [
        mutant_name
        for shard_names in assignments.values()
        for mutant_name in shard_names
    ]
    stats = _write_stats(tmp_path, [name.split("__")[0] for name in mutant_names])
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            build_execution_groups_matrix(plan, expected_shards=4, target_groups=2)
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "group-budgets.json"

    summary = validate_group_budgets(
        matrix_path=matrix_path,
        plan_directory=plan,
        stats_path=stats,
        output_manifest=manifest_path,
        expected_shards=4,
        target_groups=2,
        max_children=3,
        control_cycle_reserve_seconds=5,
        metadata_startup_reserve_seconds=120,
        max_timeout_seconds=20_880,
    )

    assert summary == {"group_count": 2, "logical_nonempty_count": 3}
    report = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert report["group_count"] == 2
    assert report["logical_nonempty_count"] == 3
    assert sum(len(group["logical_budgets"]) for group in report["groups"]) == 3
    assert all(group["outer_timeout_seconds"] <= 20_880 for group in report["groups"])


def test_group_budget_validation_rejects_matrix_topology_drift(tmp_path: Path) -> None:
    assignments = {1: ["app.alpha.one__mutmut_1"]}
    plan = _write_plan(tmp_path, assignments)
    stats = _write_stats(tmp_path, ["app.alpha.one"])
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text('{"include": []}', encoding="utf-8")

    with pytest.raises(GroupBudgetValidationError, match="does not match"):
        validate_group_budgets(
            matrix_path=matrix_path,
            plan_directory=plan,
            stats_path=stats,
            output_manifest=tmp_path / "group-budgets.json",
            expected_shards=4,
            target_groups=2,
            max_children=3,
            control_cycle_reserve_seconds=5,
            metadata_startup_reserve_seconds=120,
            max_timeout_seconds=20_880,
        )


def test_group_budget_validation_rejects_physical_timeout_over_cap(
    tmp_path: Path,
) -> None:
    plan = _write_plan(
        tmp_path,
        {
            1: ["app.alpha.one__mutmut_1"],
            2: ["app.beta.two__mutmut_1"],
        },
    )
    stats = _write_stats(tmp_path, ["app.alpha.one", "app.beta.two"])
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            build_execution_groups_matrix(plan, expected_shards=4, target_groups=1)
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        GroupBudgetValidationError, match="physical group budget exceeds"
    ):
        validate_group_budgets(
            matrix_path=matrix_path,
            plan_directory=plan,
            stats_path=stats,
            output_manifest=tmp_path / "group-budgets.json",
            expected_shards=4,
            target_groups=1,
            max_children=3,
            control_cycle_reserve_seconds=5,
            metadata_startup_reserve_seconds=120,
            max_timeout_seconds=235,
        )


def test_empty_plan_uses_sentinel_without_reading_stats(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, {})
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            build_execution_groups_matrix(plan, expected_shards=4, target_groups=2)
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "group-budgets.json"

    assert validate_group_budgets(
        matrix_path=matrix_path,
        plan_directory=plan,
        stats_path=tmp_path / "missing-stats.json",
        output_manifest=manifest_path,
        expected_shards=4,
        target_groups=2,
        max_children=3,
        control_cycle_reserve_seconds=5,
        metadata_startup_reserve_seconds=120,
        max_timeout_seconds=20_880,
    ) == {"group_count": 0, "logical_nonempty_count": 0}
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["groups"] == []
