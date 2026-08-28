from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.mutmut_shard_budget import (
    METADATA_AND_STARTUP_RESERVE_SECONDS,
    MUTMUT_WALL_TIMEOUT_GRACE_SECONDS,
    MUTMUT_WALL_TIMEOUT_MULTIPLIER,
    SELECTED_TEST_PHASE_MULTIPLIER,
    TERMINATION_GRACE_SECONDS,
    calculate_shard_budget,
    main,
)


def test_calculate_shard_budget_models_mutmut_watchdog_and_parallel_workers() -> None:
    budget = calculate_shard_budget(
        [
            "app.module.x_fast__mutmut_1",
            "app.module.x_slow__mutmut_1",
            "app.module.x_slow__mutmut_2",
        ],
        {
            "app.module.x_fast": ["tests/test_fast.py::test_fast"],
            "app.module.x_slow": ["tests/test_slow.py::test_slow"],
        },
        {
            "tests/test_fast.py::test_fast": 1.0,
            "tests/test_slow.py::test_slow": 3.0,
        },
        max_children=2,
    )

    # mutmut schedules ascending by estimate: 105s for fast, then two 135s
    # slow mutants. The watchdog-only bound is 240s; each of the three children
    # also consumes a parent control cycle for watchdog polling, fork/reap,
    # registration, and metadata persistence.
    assert budget.watchdog_execution_cap_seconds == 240
    assert budget.control_cycle_count == 3
    assert budget.control_cycle_reserve_seconds == 45
    assert budget.execution_cap_seconds == 285
    assert budget.selected_test_union_seconds == 4
    assert budget.pre_mutation_reserve_seconds == (
        METADATA_AND_STARTUP_RESERVE_SECONDS + SELECTED_TEST_PHASE_MULTIPLIER * 4
    )
    assert budget.outer_timeout_seconds == (
        budget.pre_mutation_reserve_seconds + budget.execution_cap_seconds
    )
    assert budget.total_wall_cap_seconds == (
        budget.outer_timeout_seconds + TERMINATION_GRACE_SECONDS
    )


def test_calculate_shard_budget_scopes_clean_and_forced_fail_to_selected_test_union() -> (
    None
):
    """Unrelated tests cannot inflate a selected shard's pre-mutation budget."""

    budget = calculate_shard_budget(
        [
            "app.module.x_alpha__mutmut_1",
            "app.module.x_beta__mutmut_1",
        ],
        {
            "app.module.x_alpha": [
                "tests/test_alpha.py::test_alpha",
                "tests/test_shared.py::test_shared",
            ],
            "app.module.x_beta": [
                "tests/test_beta.py::test_beta",
                "tests/test_shared.py::test_shared",
            ],
        },
        {
            "tests/test_alpha.py::test_alpha": 1.0,
            "tests/test_beta.py::test_beta": 3.0,
            "tests/test_shared.py::test_shared": 2.0,
            "tests/test_unrelated.py::test_very_slow": 10_000.0,
        },
        max_children=2,
    )

    # The selected exact union is alpha + beta + shared (1 + 3 + 2), not the
    # complete population and not the duplicate sum from two mutant mappings.
    assert budget.selected_test_union_seconds == 6
    assert budget.pre_mutation_reserve_seconds == (
        METADATA_AND_STARTUP_RESERVE_SECONDS + 2 * 6
    )
    # GNU timeout receives this value and adds its separate kill-after grace.
    assert budget.outer_timeout_seconds == (
        budget.pre_mutation_reserve_seconds + budget.execution_cap_seconds
    )
    assert budget.total_wall_cap_seconds == (
        budget.outer_timeout_seconds + TERMINATION_GRACE_SECONDS
    )


def test_calculate_shard_budget_reserves_each_selected_child_control_cycle() -> None:
    budget = calculate_shard_budget(
        [
            "app.module.x__mutmut_1",
            "app.module.x__mutmut_2",
            "app.module.x__mutmut_3",
            "app.module.x__mutmut_4",
            "app.module.x__mutmut_5",
        ],
        {"app.module.x": ["tests/test_x.py::test_x"]},
        {"tests/test_x.py::test_x": 1.0},
        max_children=2,
    )

    # Five equal mutants use three concurrent scheduling waves, but each child
    # independently incurs parent polling, fork/reap, registration, and
    # metadata persistence. Reserving only three wave-level cycles would
    # undercount two child completions.
    assert budget.watchdog_execution_cap_seconds == 315
    assert budget.control_cycle_count == 5
    assert budget.control_cycle_reserve_seconds == 75
    assert budget.execution_cap_seconds == 390


def test_calculate_shard_budget_supports_an_explicit_fail_closed_control_reserve() -> (
    None
):
    budget = calculate_shard_budget(
        [
            "app.module.x__mutmut_1",
            "app.module.x__mutmut_2",
            "app.module.x__mutmut_3",
        ],
        {"app.module.x": ["tests/test_x.py::test_x"]},
        {"tests/test_x.py::test_x": 0.25},
        max_children=2,
        control_cycle_reserve_seconds=1,
    )

    assert budget.control_cycle_count == 3
    assert budget.control_cycle_reserve_seconds == 3
    assert budget.execution_cap_seconds == (budget.watchdog_execution_cap_seconds + 3)
    assert (
        budget.as_json(max_timeout_seconds=18_000)[
            "control_cycle_reserve_per_child_seconds"
        ]
        == 1
    )


def test_calculate_shard_budget_rounds_a_positive_sub_ulp_duration_up_in_both_paths() -> (
    None
):
    """A positive fractional test duration cannot disappear before either cap."""

    whole_test = "tests/test_z_integer.py::test_integer"
    fractional_test = "tests/test_a_fraction.py::test_fraction"
    budget = calculate_shard_budget(
        ["app.module.x__mutmut_1"],
        {"app.module.x": [whole_test, fractional_test]},
        {
            whole_test: 1.0,
            fractional_test: 2.0**-54,
        },
        max_children=1,
    )

    # The exact valid duration is 1 + 2**-54. It is strictly above one even
    # though its nearest binary float rounds to 1.0. Both the selected union
    # reserve and mutmut's 15x watchdog therefore need their next full second.
    assert budget.selected_test_union_seconds == 2
    assert budget.watchdog_execution_cap_seconds == 106
    assert budget.pre_mutation_reserve_seconds == 904
    assert budget.outer_timeout_seconds == 1025
    assert budget.total_wall_cap_seconds == 1055


def test_calculate_shard_budget_matches_the_observed_pr_lifecycle_shape() -> None:
    """The observed shard fits the PR's pre-KILL cap and separate grace."""

    test_name = "tests/test_lifecycle.py::test_observed_duration"
    budget = calculate_shard_budget(
        ["app.module.lifecycle__mutmut_1"],
        {"app.module.lifecycle": [test_name]},
        {test_name: 258.839754},
        max_children=1,
    )

    assert budget.selected_test_union_seconds == 259
    assert budget.pre_mutation_reserve_seconds == 1418
    assert budget.watchdog_execution_cap_seconds == 3973
    assert budget.control_cycle_reserve_seconds == 15
    assert budget.execution_cap_seconds == 3988
    assert budget.outer_timeout_seconds == 5406
    assert budget.total_wall_cap_seconds == 5436
    assert budget.outer_timeout_seconds < 6600
    assert budget.total_wall_cap_seconds == (
        budget.outer_timeout_seconds + TERMINATION_GRACE_SECONDS
    )


def test_budget_cli_fails_closed_when_multi_wave_reserve_exceeds_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_file = tmp_path / "selected-mutants.txt"
    selected_file.write_text(
        "\n".join(f"app.module.x__mutmut_{index}" for index in range(1, 6)) + "\n",
        encoding="utf-8",
    )
    stats_file = tmp_path / "mutmut-stats.json"
    stats_file.write_text(
        json.dumps(
            {
                "tests_by_mangled_function_name": {
                    "app.module.x": ["tests/test_x.py::test_x"]
                },
                "duration_by_test": {"tests/test_x.py::test_x": 1.0},
            }
        ),
        encoding="utf-8",
    )
    output_file = tmp_path / "budget.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mutmut_shard_budget.py",
            "--selected-file",
            str(selected_file),
            "--stats",
            str(stats_file),
            "--max-children",
            "2",
            # 1,022 seconds is below the new fail-closed calculation. It must
            # reject the shard once all three scheduling-wave reserves count.
            "--max-timeout-seconds",
            "1022",
            "--output",
            str(output_file),
        ],
    )

    with pytest.raises(SystemExit, match="exceeds the configured maximum"):
        main()

    assert not output_file.exists()


def test_calculate_shard_budget_rejects_selected_mutants_without_mapped_tests() -> None:
    with pytest.raises(ValueError, match="no mapped tests"):
        calculate_shard_budget(
            ["app.module.x_missing__mutmut_1"],
            {},
            {"tests/test_any.py::test_any": 1.0},
            max_children=2,
        )


def test_calculate_shard_budget_rejects_missing_test_durations() -> None:
    with pytest.raises(ValueError, match="missing durations"):
        calculate_shard_budget(
            ["app.module.x_missing__mutmut_1"],
            {"app.module.x_missing": ["tests/test_missing.py::test_missing"]},
            {},
            max_children=2,
        )


def test_calculate_shard_budget_rejects_boolean_test_durations() -> None:
    with pytest.raises(ValueError, match="invalid duration"):
        calculate_shard_budget(
            ["app.module.x_invalid__mutmut_1"],
            {"app.module.x_invalid": ["tests/test_invalid.py::test_invalid"]},
            {"tests/test_invalid.py::test_invalid": True},
            max_children=1,
        )


def test_calculate_shard_budget_rejects_invalid_worker_count() -> None:
    with pytest.raises(ValueError, match="max_children"):
        calculate_shard_budget(
            ["app.module.x_fast__mutmut_1"],
            {"app.module.x_fast": ["tests/test_fast.py::test_fast"]},
            {"tests/test_fast.py::test_fast": 1.0},
            max_children=0,
        )


def test_watchdog_multiplier_remains_the_mutmut_37_wall_timeout_contract() -> None:
    assert MUTMUT_WALL_TIMEOUT_MULTIPLIER == 15
    assert MUTMUT_WALL_TIMEOUT_GRACE_SECONDS == 6
