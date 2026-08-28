from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from mutmut.mutation.file_mutation import mutate_file_contents

from scripts.plan_mutmut_shards import (
    MutantEstimate,
    _mutant_line_ranges,
    _parse_args,
    estimate_mutant_times,
    normalize_source_path,
    parse_unified_diff_line_ranges,
    plan_mutant_shards,
    write_shard_plan_bundle,
)


def test_normalize_source_path_matches_git_manifest_format() -> None:
    assert normalize_source_path(r".\app\auth\security.py") == "app/auth/security.py"


def test_parse_unified_diff_line_ranges_uses_new_file_lines() -> None:
    diff = """\
diff --git a/app/core/lifespan.py b/app/core/lifespan.py
--- a/app/core/lifespan.py
+++ b/app/core/lifespan.py
@@ -408,0 +409,4 @@ async def lifespan(app):
+one
+two
+three
+four
@@ -500,2 +504,1 @@ async def shutdown(app):
-old
+new
"""

    assert parse_unified_diff_line_ranges(diff) == {
        "app/core/lifespan.py": [(409, 412), (504, 504)]
    }


def test_mutant_line_ranges_match_mutmut_names_for_class_methods(
    tmp_path: Path,
) -> None:
    # mutmut runs clean tests from its already-trampolined ``mutants/`` copy.
    # Keep this fixture outside that tree so this regression test never asks
    # mutmut to instrument its own generated class-method names a second time.
    path = tmp_path / "class_method_fixture.py"
    source = """\
class FixtureClass:
    def method(self) -> bool:
        return True
"""
    path.write_text(source, encoding="utf-8")
    mutated_source = mutate_file_contents(str(path), source)
    bare_mutant_names = mutated_source.mutant_names
    cli = SimpleNamespace(get_mutant_name=lambda _path, name: f"fixture.module.{name}")

    assert set(bare_mutant_names) == {"xǁFixtureClassǁmethod__mutmut_1"}
    assert set(_mutant_line_ranges(cli, path)) == {
        f"fixture.module.{name}" for name in bare_mutant_names
    }


def test_estimate_mutant_times_uses_associated_test_durations() -> None:
    estimates = estimate_mutant_times(
        ["app.auth.security.x_login__mutmut_2", "app.auth.security.x_login__mutmut_1"],
        {"app.auth.security.x_login": ["test/fast.py::test_login", "missing"]},
        {"test/fast.py::test_login": 1.25, "missing": 0.75},
    )

    assert estimates == [
        MutantEstimate("app.auth.security.x_login__mutmut_1", 2.0),
        MutantEstimate("app.auth.security.x_login__mutmut_2", 2.0),
    ]


def test_estimate_mutant_times_rejects_mutants_without_mapped_tests() -> None:
    with pytest.raises(ValueError, match="no mapped tests"):
        estimate_mutant_times(
            ["app.core.lifespan.x_shutdown__mutmut_1"],
            {},
            {},
        )


def test_estimate_mutant_times_rejects_missing_test_durations() -> None:
    with pytest.raises(ValueError, match="missing durations"):
        estimate_mutant_times(
            ["app.core.lifespan.x_shutdown__mutmut_1"],
            {"app.core.lifespan.x_shutdown": ["tests/test_lifespan.py::test"]},
            {},
        )


@pytest.mark.parametrize("duration", [True, -0.1, float("nan"), float("inf")])
def test_estimate_mutant_times_rejects_unsafe_test_durations(
    duration: bool | float,
) -> None:
    with pytest.raises(ValueError, match="finite non-negative"):
        estimate_mutant_times(
            ["app.core.lifespan.x_shutdown__mutmut_1"],
            {"app.core.lifespan.x_shutdown": ["tests/test_lifespan.py::test"]},
            {"tests/test_lifespan.py::test": duration},
        )


def test_plan_mutant_shards_balances_duration_and_preserves_all_mutants() -> None:
    estimates = [
        MutantEstimate("long", 10.0),
        MutantEstimate("medium", 9.0),
        MutantEstimate("next", 8.0),
        MutantEstimate("short", 7.0),
    ]

    shards = plan_mutant_shards(estimates, num_shards=2)

    assert {name for shard in shards for name in shard} == {
        "long",
        "medium",
        "next",
        "short",
    }
    assert [
        sum(item.estimated_seconds for item in estimates if item.name in shard)
        for shard in shards
    ] == [17.0, 17.0]


def test_plan_mutant_shards_balances_zero_duration_by_count() -> None:
    estimates = [MutantEstimate(name, 0.0) for name in ("a", "b", "c", "d", "e")]

    shards = plan_mutant_shards(estimates, num_shards=3)

    assert [len(shard) for shard in shards] == [2, 2, 1]


def test_plan_mutant_shards_rejects_invalid_shard_count() -> None:
    with pytest.raises(ValueError, match="num_shards"):
        plan_mutant_shards([], num_shards=0)


def test_write_shard_plan_bundle_persists_exact_audited_population(
    tmp_path: Path,
) -> None:
    estimates = [
        MutantEstimate("app.a.x_f__mutmut_1", 2.5),
        MutantEstimate("app.a.x_f__mutmut_2", 1.5),
        MutantEstimate("app.b.x_g__mutmut_1", 1.0),
    ]
    shards = [
        ["app.a.x_f__mutmut_1"],
        ["app.a.x_f__mutmut_2", "app.b.x_g__mutmut_1"],
    ]

    manifest = write_shard_plan_bundle(tmp_path, shards, estimates)

    assert (tmp_path / "shard-01.txt").read_text(encoding="utf-8") == (
        "app.a.x_f__mutmut_1\n"
    )
    assert (tmp_path / "shard-02.txt").read_text(encoding="utf-8") == (
        "app.a.x_f__mutmut_2\napp.b.x_g__mutmut_1\n"
    )
    persisted = json.loads(
        (tmp_path / "plan-manifest.json").read_text(encoding="utf-8")
    )
    assert persisted == manifest
    assert manifest["schema_version"] == 1
    assert manifest["num_shards"] == 2
    assert manifest["universe_count"] == 3
    assert len(manifest["universe_sha256"]) == 64
    assert manifest["shards"] == [
        {
            "estimated_load_seconds": 2.5,
            "path": "shard-01.txt",
            "selected_count": 1,
            "selection_sha256": manifest["shards"][0]["selection_sha256"],
            "shard_id": 1,
        },
        {
            "estimated_load_seconds": 2.5,
            "path": "shard-02.txt",
            "selected_count": 2,
            "selection_sha256": manifest["shards"][1]["selection_sha256"],
            "shard_id": 2,
        },
    ]
    assert all(len(item["selection_sha256"]) == 64 for item in manifest["shards"])


@pytest.mark.parametrize(
    ("shards", "estimates", "message"),
    [
        ([[]], [], "must not be empty"),
        (
            [["app.a.x_f__mutmut_1"], ["app.a.x_f__mutmut_1"]],
            [MutantEstimate("app.a.x_f__mutmut_1", 1.0)],
            "duplicate",
        ),
        (
            [["app.a.x_f__mutmut_1"]],
            [
                MutantEstimate("app.a.x_f__mutmut_1", 1.0),
                MutantEstimate("app.a.x_f__mutmut_2", 1.0),
            ],
            "does not match",
        ),
    ],
)
def test_write_shard_plan_bundle_rejects_incomplete_or_ambiguous_plans(
    tmp_path: Path,
    shards: list[list[str]],
    estimates: list[MutantEstimate],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        write_shard_plan_bundle(tmp_path, shards, estimates)


def test_plan_cli_accepts_all_shard_bundle_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_directory = tmp_path / "plan"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "plan_mutmut_shards.py",
            "--changed-files",
            str(tmp_path / "changed.txt"),
            "--num-shards",
            "16",
            "--max-children",
            "8",
            "--output-directory",
            str(output_directory),
        ],
    )

    args = _parse_args()

    assert args.output_directory == output_directory
    assert args.output is None
    assert args.shard_id is None


def test_plan_cli_rejects_a_shard_id_with_bundle_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "plan_mutmut_shards.py",
            "--changed-files",
            str(tmp_path / "changed.txt"),
            "--shard-id",
            "1",
            "--num-shards",
            "2",
            "--output-directory",
            str(tmp_path / "plan"),
        ],
    )

    with pytest.raises(SystemExit, match="2"):
        _parse_args()
