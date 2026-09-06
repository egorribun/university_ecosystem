from __future__ import annotations

import hashlib
import json
import runpy
import sys
from pathlib import Path

import pytest

from scripts.mutmut_shard_matrix import (
    PlanValidationError,
    _seconds_to_micros,
    build_execution_groups,
    build_execution_groups_matrix,
    build_execution_matrix,
    resolve_execution_group,
    validate_execution_group_descriptor,
    validate_matrix_entry,
)


def test_seconds_to_micros_rejects_unrepresentable_integer() -> None:
    """Huge JSON integers must fail with the plan-domain error."""

    with pytest.raises(PlanValidationError, match="estimated load is invalid"):
        _seconds_to_micros(10**400, label="estimated load")


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


def test_execution_groups_coalesce_logical_shards_without_changing_selection(
    tmp_path: Path,
) -> None:
    plan = _write_plan(
        tmp_path,
        {
            1: ["app.a.one__mutmut_1"],
            2: ["app.a.one__mutmut_2"],
            3: ["app.b.two__mutmut_1", "app.b.two__mutmut_2"],
            4: ["app.c.three__mutmut_1"],
        },
    )

    groups = build_execution_groups(plan, expected_shards=4, target_groups=2)

    assert groups == {
        "group_count": 2,
        "target_groups": 2,
        "schema_version": 1,
        "expected_shards": 4,
        "universe_count": 5,
        "universe_sha256": _digest(
            [
                "app.a.one__mutmut_1",
                "app.a.one__mutmut_2",
                "app.b.two__mutmut_1",
                "app.b.two__mutmut_2",
                "app.c.three__mutmut_1",
            ]
        ),
        "groups": [
            {
                "group_id": 1,
                "logical_shards": [1, 2],
                "selection_files": ["shard-01.txt", "shard-02.txt"],
                "selected_count": 2,
                "selection_sha256": _digest(
                    ["app.a.one__mutmut_1", "app.a.one__mutmut_2"]
                ),
                "group_sha256": groups["groups"][0]["group_sha256"],
                "estimated_load_micros": 2_000_000,
            },
            {
                "group_id": 2,
                "logical_shards": [3, 4],
                "selection_files": ["shard-03.txt", "shard-04.txt"],
                "selected_count": 3,
                "selection_sha256": _digest(
                    [
                        "app.b.two__mutmut_1",
                        "app.b.two__mutmut_2",
                        "app.c.three__mutmut_1",
                    ]
                ),
                "group_sha256": groups["groups"][1]["group_sha256"],
                "estimated_load_micros": 3_000_000,
            },
        ],
    }
    first_group = groups["groups"][0]
    assert isinstance(first_group, dict)
    assert resolve_execution_group(plan, expected_shards=4, group=first_group) == (
        "app.a.one__mutmut_1",
        "app.a.one__mutmut_2",
    )


def test_execution_groups_matrix_carries_complete_group_metadata(
    tmp_path: Path,
) -> None:
    plan = _write_plan(
        tmp_path,
        {1: ["app.a.one__mutmut_1"], 3: ["app.b.two__mutmut_1"]},
    )

    matrix = build_execution_groups_matrix(plan, expected_shards=4, target_groups=1)
    topology = build_execution_groups(plan, expected_shards=4, target_groups=1)
    assert matrix == {
        "include": [
            {
                **topology["groups"][0],
                "has_python": "true",
                "has_mutants": "true",
            }
        ]
    }


def test_validate_group_uses_exact_integer_load_transport(
    tmp_path: Path,
) -> None:
    plan = _write_plan(
        tmp_path,
        {
            1: ["app.a.one__mutmut_1"],
            2: ["app.a.one__mutmut_2"],
        },
    )
    manifest_path = plan / "plan-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # The source plan keeps a floating-point seconds estimate, but the matrix
    # carries an integer microsecond total.  The integer is stable across
    # GitHub expression interpolation and shell environment transport.
    manifest["shards"][0]["estimated_load_seconds"] = 1211.4625996820007
    manifest["shards"][1]["estimated_load_seconds"] = 1211.4625996820007
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    group = build_execution_groups(plan, expected_shards=4, target_groups=1)["groups"][
        0
    ]
    assert isinstance(group, dict)
    transported_load = group["estimated_load_micros"]

    assert validate_execution_group_descriptor(
        plan,
        expected_shards=4,
        target_groups=1,
        group_id=group["group_id"],
        logical_shards=",".join(str(shard_id) for shard_id in group["logical_shards"]),
        selected_count=group["selected_count"],
        selection_sha256=group["selection_sha256"],
        group_sha256=group["group_sha256"],
        estimated_load_micros=transported_load,
    ) == ("app.a.one__mutmut_1", "app.a.one__mutmut_2")


def test_execution_groups_matrix_emits_safe_empty_sentinel(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, {})

    assert build_execution_groups_matrix(plan, expected_shards=4, target_groups=2) == {
        "include": [
            {
                "group_id": 0,
                "logical_shards": [],
                "selection_files": [],
                "selected_count": 0,
                "selection_sha256": "",
                "group_sha256": "",
                "estimated_load_micros": 0,
                "has_python": "true",
                "has_mutants": "false",
            }
        ]
    }


@pytest.mark.parametrize("logical_shards", ["", "1,,2", "one", "1,1"])
def test_execution_group_descriptor_rejects_invalid_logical_shard_text(
    tmp_path: Path, logical_shards: str
) -> None:
    plan = _write_plan(
        tmp_path,
        {1: ["app.a.one__mutmut_1"], 2: ["app.a.one__mutmut_2"]},
    )
    group = build_execution_groups(plan, expected_shards=4, target_groups=1)["groups"][
        0
    ]
    assert isinstance(group, dict)

    with pytest.raises(PlanValidationError, match="logical shards"):
        validate_execution_group_descriptor(
            plan,
            expected_shards=4,
            target_groups=1,
            group_id=group["group_id"],
            logical_shards=logical_shards,
            selected_count=group["selected_count"],
            selection_sha256=group["selection_sha256"],
            group_sha256=group["group_sha256"],
            estimated_load_micros=group["estimated_load_micros"],
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("group_id", 2, "membership or digest"),
        ("selected_count", 99, "membership or digest"),
        ("selection_sha256", "0" * 64, "membership or digest"),
        ("group_sha256", "0" * 64, "membership or digest"),
        ("estimated_load_micros", 99, "membership or digest"),
    ],
)
def test_execution_group_descriptor_rejects_tampered_metadata(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    plan = _write_plan(tmp_path, {1: ["app.a.one__mutmut_1"]})
    group = build_execution_groups(plan, expected_shards=4, target_groups=1)["groups"][
        0
    ]
    assert isinstance(group, dict)
    descriptor = dict(group)
    descriptor[field] = value

    with pytest.raises(PlanValidationError, match=message):
        validate_execution_group_descriptor(
            plan,
            expected_shards=4,
            target_groups=1,
            group_id=descriptor["group_id"],
            logical_shards=",".join(str(item) for item in descriptor["logical_shards"]),
            selected_count=descriptor["selected_count"],
            selection_sha256=descriptor["selection_sha256"],
            group_sha256=descriptor["group_sha256"],
            estimated_load_micros=descriptor["estimated_load_micros"],
        )


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


def test_command_line_groups_entrypoint_emits_physical_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _write_plan(tmp_path, {1: ["app.a.one__mutmut_1"]})
    script = Path(__file__).parents[1] / "scripts" / "mutmut_shard_matrix.py"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(script),
            "groups",
            "--plan-directory",
            str(plan),
            "--expected-shards",
            "4",
            "--target-groups",
            "2",
        ],
    )

    runpy.run_path(str(script), run_name="__main__")

    matrix = json.loads(capsys.readouterr().out)
    assert len(matrix["include"]) == 1
    descriptor = matrix["include"][0]
    assert descriptor["group_id"] == 1
    assert descriptor["logical_shards"] == [1]
    assert descriptor["has_python"] == "true"
    assert descriptor["has_mutants"] == "true"


def test_command_line_validate_group_entrypoint_requires_exact_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _write_plan(tmp_path, {1: ["app.a.one__mutmut_1"]})
    topology = build_execution_groups(plan, expected_shards=4, target_groups=2)
    group = topology["groups"][0]
    assert isinstance(group, dict)
    script = Path(__file__).parents[1] / "scripts" / "mutmut_shard_matrix.py"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(script),
            "validate-group",
            "--plan-directory",
            str(plan),
            "--expected-shards",
            "4",
            "--target-groups",
            "2",
            "--group-id",
            str(group["group_id"]),
            "--logical-shards",
            ",".join(str(shard_id) for shard_id in group["logical_shards"]),
            "--selected-count",
            str(group["selected_count"]),
            "--selection-sha256",
            group["selection_sha256"],
            "--group-sha256",
            group["group_sha256"],
            "--estimated-load-micros",
            str(group["estimated_load_micros"]),
        ],
    )

    runpy.run_path(str(script), run_name="__main__")


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
