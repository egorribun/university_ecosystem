from __future__ import annotations

import pytest

from scripts.plan_mutmut_shards import (
    MutantEstimate,
    estimate_mutant_times,
    normalize_source_path,
    plan_mutant_shards,
)


def test_normalize_source_path_matches_git_manifest_format() -> None:
    assert normalize_source_path(r".\app\auth\security.py") == "app/auth/security.py"


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
