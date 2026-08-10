from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.mutmut_shard_budget import (
    FULL_POPULATION_PHASE_MULTIPLIER,
    METADATA_AND_STARTUP_RESERVE_SECONDS,
    MUTMUT_WALL_TIMEOUT_MULTIPLIER,
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

    # mutmut schedules ascending by estimate: 30s for fast, then two 60s
    # slow mutants. The watchdog-only bound is 90s; each of the three children
    # also consumes a parent control cycle for watchdog polling, fork/reap,
    # registration, and metadata persistence.
    assert budget.watchdog_execution_cap_seconds == 90
    assert budget.control_cycle_count == 3
    assert budget.control_cycle_reserve_seconds == 45
    assert budget.execution_cap_seconds == 135
    assert budget.full_test_population_seconds == 4
    assert budget.pre_mutation_reserve_seconds == (
        METADATA_AND_STARTUP_RESERVE_SECONDS + FULL_POPULATION_PHASE_MULTIPLIER * 4
    )
    assert budget.outer_timeout_seconds == (
        budget.pre_mutation_reserve_seconds
        + budget.execution_cap_seconds
        + TERMINATION_GRACE_SECONDS
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
    assert budget.watchdog_execution_cap_seconds == 90
    assert budget.control_cycle_count == 5
    assert budget.control_cycle_reserve_seconds == 75
    assert budget.execution_cap_seconds == 165


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
            # 1,022 seconds accepts the watchdog-only calculation.  It must
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
