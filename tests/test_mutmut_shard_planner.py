from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from mutmut.file_mutation import mutate_file_contents

from scripts.plan_mutmut_shards import (
    MutantEstimate,
    _mutant_line_ranges,
    estimate_mutant_times,
    normalize_source_path,
    parse_unified_diff_line_ranges,
    plan_mutant_shards,
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
    _mutated_source, bare_mutant_names = mutate_file_contents(str(path), source)
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
