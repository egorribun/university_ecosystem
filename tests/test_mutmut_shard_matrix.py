from __future__ import annotations

import hashlib
import json
import runpy
import sys
from pathlib import Path

import pytest

from scripts.mutmut_shard_matrix import (
    PlanValidationError,
    build_execution_matrix,
    validate_matrix_entry,
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


def test_matrix_contains_only_nonempty_validated_plan_shards(tmp_path: Path) -> None:
    plan = _write_plan(
        tmp_path,
        {
            1: ["app.a.one__mutmut_1"],
            3: ["app.b.two__mutmut_1", "app.b.two__mutmut_2"],
        },
    )

    assert build_execution_matrix(plan, expected_shards=4) == {
        "include": [
            {"shard": 1, "has_python": "true", "has_mutants": "true"},
            {"shard": 3, "has_python": "true", "has_mutants": "true"},
        ]
    }


def test_matrix_emits_one_explicit_sentinel_when_plan_has_no_mutants(
    tmp_path: Path,
) -> None:
    plan = _write_plan(tmp_path, {})

    assert build_execution_matrix(plan, expected_shards=4) == {
        "include": [{"shard": 0, "has_python": "true", "has_mutants": "false"}]
    }
    validate_matrix_entry(
        plan,
        expected_shards=4,
        shard_id=0,
        has_python=True,
        has_mutants=False,
    )


@pytest.mark.parametrize(
    ("assignments", "mutate_manifest", "error"),
    [
        (
            {1: ["app.a.one__mutmut_1"]},
            lambda manifest: manifest["shards"][0].__setitem__("selected_count", 2),
            "selected count",
        ),
        (
            {1: ["app.a.one__mutmut_1"]},
            lambda manifest: manifest.__setitem__("universe_sha256", "0" * 64),
            "universe digest",
        ),
        (
            {1: ["app.a.one__mutmut_1"], 2: ["app.a.one__mutmut_1"]},
            lambda manifest: None,
            "duplicate mutant",
        ),
    ],
)
def test_matrix_fails_closed_for_tampered_or_incomplete_plan(
    tmp_path: Path,
    assignments: dict[int, list[str]],
    mutate_manifest: object,
    error: str,
) -> None:
    plan = _write_plan(tmp_path, assignments)
    manifest_path = plan / "plan-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert callable(mutate_manifest)
    mutate_manifest(manifest)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(PlanValidationError, match=error):
        build_execution_matrix(plan, expected_shards=4)


def test_matrix_entry_rejects_unselected_or_mislabelled_assignment(
    tmp_path: Path,
) -> None:
    plan = _write_plan(tmp_path, {2: ["app.b.two__mutmut_1"]})

    with pytest.raises(PlanValidationError, match="not selected"):
        validate_matrix_entry(
            plan,
            expected_shards=4,
            shard_id=1,
            has_python=True,
            has_mutants=True,
        )
    with pytest.raises(PlanValidationError, match="does not match"):
        validate_matrix_entry(
            plan,
            expected_shards=4,
            shard_id=2,
            has_python=True,
            has_mutants=False,
        )


def test_command_line_entrypoint_emits_a_validated_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _write_plan(tmp_path, {4: ["app.d.four__mutmut_1"]})
    script = Path(__file__).parents[1] / "scripts" / "mutmut_shard_matrix.py"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(script),
            "matrix",
            "--plan-directory",
            str(plan),
            "--expected-shards",
            "4",
        ],
    )

    runpy.run_path(str(script), run_name="__main__")

    assert json.loads(capsys.readouterr().out) == {
        "include": [{"shard": 4, "has_python": "true", "has_mutants": "true"}]
    }


def test_command_line_entrypoint_fails_closed_for_invalid_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _write_plan(tmp_path, {1: ["app.a.one__mutmut_1"]})
    (plan / "shard-01.txt").write_text("", encoding="utf-8")
    script = Path(__file__).parents[1] / "scripts" / "mutmut_shard_matrix.py"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(script),
            "matrix",
            "--plan-directory",
            str(plan),
            "--expected-shards",
            "4",
        ],
    )

    with pytest.raises(SystemExit, match="mutmut execution matrix validation failed"):
        runpy.run_path(str(script), run_name="__main__")
