from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.mutmut_shard_budget import (
    DEFAULT_MAX_TIMEOUT_SECONDS,
    METADATA_AND_STARTUP_RESERVE_SECONDS,
    MUTMUT_JOB_DEADLINE_SECONDS,
    MUTMUT_MINIMUM_EXECUTION_MULTIPLIER,
    MUTMUT_POST_RUN_UPLOAD_RESERVE_SECONDS,
    MUTMUT_TIMEOUT_KILL_GRACE_SECONDS,
    MUTMUT_WALL_TIMEOUT_GRACE_SECONDS,
    MUTMUT_WALL_TIMEOUT_MULTIPLIER,
    TERMINATION_GRACE_SECONDS,
    calculate_shard_budget,
    main,
    resolve_execution_multiplier,
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
    assert budget.forced_fail_test_seconds == 3
    assert budget.pre_mutation_reserve_seconds == (
        METADATA_AND_STARTUP_RESERVE_SECONDS + 4 + 3
    )
    assert budget.outer_timeout_seconds == (
        budget.pre_mutation_reserve_seconds + budget.execution_cap_seconds
    )
    assert budget.total_wall_cap_seconds == (
        budget.outer_timeout_seconds + TERMINATION_GRACE_SECONDS
    )
    serialized = budget.as_json(max_timeout_seconds=10_000)
    assert serialized["schema_version"] == 3
    assert serialized["forced_fail_test_seconds"] == 3
    assert serialized["execution_multiplier"] == MUTMUT_WALL_TIMEOUT_MULTIPLIER
    assert serialized["mutmut_watchdog_multiplier"] == MUTMUT_WALL_TIMEOUT_MULTIPLIER


def test_calculate_shard_budget_scopes_clean_and_forced_fail_to_selected_test_union() -> (
    None
):
    """Unrelated tests cannot inflate either selected pre-mutation phase."""

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

    # The selected exact clean union is alpha + beta + shared (1 + 3 + 2), not
    # the complete population and not the duplicate sum from two mappings. The
    # forced-fail phase stops at the first ``pytest -x`` failure, so it is
    # charged only the slowest mapped test (3), not another full union.
    assert budget.selected_test_union_seconds == 6
    assert budget.forced_fail_test_seconds == 3
    assert budget.pre_mutation_reserve_seconds == (
        METADATA_AND_STARTUP_RESERVE_SECONDS + 6 + 3
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


def test_calculate_shard_budget_records_reused_universe_startup_reserve() -> None:
    """Reusable-universe callers can prove a smaller setup envelope explicitly."""

    budget = calculate_shard_budget(
        ["app.module.x__mutmut_1"],
        {"app.module.x": ["tests/test_x.py::test_x"]},
        {"tests/test_x.py::test_x": 1.0},
        max_children=1,
        metadata_and_startup_reserve_seconds=240,
    )

    assert budget.metadata_and_startup_reserve_seconds == 240
    assert budget.forced_fail_test_seconds == 1
    assert budget.pre_mutation_reserve_seconds == 242
    assert (
        budget.as_json(max_timeout_seconds=20_970)[
            "metadata_and_startup_reserve_seconds"
        ]
        == 240
    )


def test_calculate_shard_budget_rejects_negative_startup_reserve() -> None:
    with pytest.raises(ValueError, match="metadata_and_startup_reserve_seconds"):
        calculate_shard_budget(
            ["app.module.x__mutmut_1"],
            {"app.module.x": ["tests/test_x.py::test_x"]},
            {"tests/test_x.py::test_x": 1.0},
            max_children=1,
            metadata_and_startup_reserve_seconds=-1,
        )


def test_budget_cli_rejects_negative_startup_reserve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_file = tmp_path / "selected-mutants.txt"
    stats_file = tmp_path / "mutmut-stats.json"
    output_file = tmp_path / "budget.json"
    selected_file.write_text("app.module.x__mutmut_1\n", encoding="utf-8")
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
            "1",
            "--metadata-startup-reserve-seconds",
            "-1",
            "--max-timeout-seconds",
            "20970",
            "--output",
            str(output_file),
        ],
    )

    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert not output_file.exists()


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
    assert budget.forced_fail_test_seconds == 1
    assert budget.watchdog_execution_cap_seconds == 106
    assert budget.pre_mutation_reserve_seconds == 903
    assert budget.outer_timeout_seconds == 1024
    assert budget.total_wall_cap_seconds == 1054


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


def test_default_timeout_cap_is_derived_from_the_six_hour_job_envelope() -> None:
    """The hard cap leaves explicit post-run and termination headroom."""

    assert DEFAULT_MAX_TIMEOUT_SECONDS == (
        MUTMUT_JOB_DEADLINE_SECONDS
        - MUTMUT_POST_RUN_UPLOAD_RESERVE_SECONDS
        - MUTMUT_TIMEOUT_KILL_GRACE_SECONDS
    )
    assert DEFAULT_MAX_TIMEOUT_SECONDS == 20_970


# ---------------------------------------------------------------------------
# Full-map survivor confirmation: degrading the watchdog multiplier
# ---------------------------------------------------------------------------

_CONFIRMATION_KWARGS = {
    "max_children": 3,
    "control_cycle_reserve_seconds": 5,
    "metadata_and_startup_reserve_seconds": 120,
}


def _hub_stats(
    *, fast_tests: int, fast_seconds: float, slow_seconds: float
) -> tuple[list[str], dict[str, list[str]], dict[str, float]]:
    """Build one mutant whose function maps to a wide, slow test union."""

    names = [f"tests/test_hub.py::test_{index}" for index in range(fast_tests)]
    durations = {name: fast_seconds for name in names}
    slow_name = "tests/test_hub.py::test_slow"
    durations[slow_name] = slow_seconds
    return (
        ["app.core.logging.x__redact_pii__mutmut_1"],
        {"app.core.logging.x__redact_pii": [*names, slow_name]},
        durations,
    )


def test_full_map_confirmation_degrades_only_as_far_as_the_job_cap_demands() -> None:
    """Run 35488190240 failed 58 of 128 groups deriving this exact shape.

    ``app/core/logging.py``'s PII helpers each map to ~1355 tests totalling
    ~1335 seconds, so mutmut's own 15x watchdog derives more than GitHub's hard
    21_600-second job maximum -- unsatisfiable on *any* hosted runner.  The
    resolver must give up exactly one step of watchdog headroom, not the whole
    margin, and the 15x half of this test pins why the resolver exists at all.
    """

    selected, tests_by_function, durations = _hub_stats(
        fast_tests=1305, fast_seconds=1.0, slow_seconds=31.0
    )

    blocked = calculate_shard_budget(
        selected, tests_by_function, durations, **_CONFIRMATION_KWARGS
    )
    assert blocked.execution_multiplier == MUTMUT_WALL_TIMEOUT_MULTIPLIER
    assert blocked.outer_timeout_seconds > MUTMUT_JOB_DEADLINE_SECONDS

    resolved = resolve_execution_multiplier(
        selected,
        tests_by_function,
        durations,
        max_timeout_seconds=DEFAULT_MAX_TIMEOUT_SECONDS,
        **_CONFIRMATION_KWARGS,
    )
    assert resolved.execution_multiplier == MUTMUT_WALL_TIMEOUT_MULTIPLIER - 1
    assert resolved.outer_timeout_seconds <= DEFAULT_MAX_TIMEOUT_SECONDS
    serialized = resolved.as_json(max_timeout_seconds=DEFAULT_MAX_TIMEOUT_SECONDS)
    assert serialized["execution_multiplier"] == MUTMUT_WALL_TIMEOUT_MULTIPLIER - 1
    assert serialized["mutmut_watchdog_multiplier"] == MUTMUT_WALL_TIMEOUT_MULTIPLIER


def test_whole_suite_hub_resolves_to_the_minimum_execution_multiplier() -> None:
    """The widest functions are covered by the entire suite (~6080 seconds).

    Their 15x budget is 97_567 seconds -- 4.5x the whole job envelope -- so they
    can only ever be confirmed at the floor.  The floor must still fit, or the
    confirmation gate would be underivable for them no matter what.
    """

    selected, tests_by_function, durations = _hub_stats(
        fast_tests=6012, fast_seconds=1.0, slow_seconds=68.0
    )

    resolved = resolve_execution_multiplier(
        selected,
        tests_by_function,
        durations,
        max_timeout_seconds=DEFAULT_MAX_TIMEOUT_SECONDS,
        **_CONFIRMATION_KWARGS,
    )
    assert resolved.execution_multiplier == MUTMUT_MINIMUM_EXECUTION_MULTIPLIER
    assert resolved.outer_timeout_seconds <= DEFAULT_MAX_TIMEOUT_SECONDS

    one_step_higher = calculate_shard_budget(
        selected,
        tests_by_function,
        durations,
        execution_multiplier=MUTMUT_MINIMUM_EXECUTION_MULTIPLIER + 1,
        **_CONFIRMATION_KWARGS,
    )
    assert one_step_higher.outer_timeout_seconds > DEFAULT_MAX_TIMEOUT_SECONDS


def test_resolver_fails_closed_when_even_the_minimum_multiplier_overruns() -> None:
    """A shard no hosted runner can confirm must fail loudly, not truncate."""

    selected, tests_by_function, durations = _hub_stats(
        fast_tests=20_000, fast_seconds=1.0, slow_seconds=1.0
    )

    with pytest.raises(ValueError, match="exceeds the configured maximum"):
        resolve_execution_multiplier(
            selected,
            tests_by_function,
            durations,
            max_timeout_seconds=DEFAULT_MAX_TIMEOUT_SECONDS,
            **_CONFIRMATION_KWARGS,
        )


def test_execution_multiplier_defaults_to_the_mutmut_watchdog_contract() -> None:
    """Every existing caller must stay bit-for-bit identical.

    ``scripts/plan_mutmut_shards.py`` keeps its own copy of the multiplier for a
    cheap greedy bound; this equivalence is what keeps the two honest.
    """

    args = (
        ["app.module.f__mutmut_1"],
        {"app.module.f": ["tests/test_f.py::test_f"]},
        {"tests/test_f.py::test_f": 3.0},
    )
    assert calculate_shard_budget(*args, max_children=2) == calculate_shard_budget(
        *args,
        max_children=2,
        execution_multiplier=MUTMUT_WALL_TIMEOUT_MULTIPLIER,
    )


@pytest.mark.parametrize(
    "multiplier",
    [0, -1, MUTMUT_WALL_TIMEOUT_MULTIPLIER + 1, 15.0, True, "2"],
)
def test_execution_multiplier_rejects_values_outside_the_watchdog_bound(
    multiplier: object,
) -> None:
    """Above mutmut's own watchdog the derived integer stops being a bound."""

    with pytest.raises(ValueError, match="execution_multiplier"):
        calculate_shard_budget(
            ["app.module.f__mutmut_1"],
            {"app.module.f": ["tests/test_f.py::test_f"]},
            {"tests/test_f.py::test_f": 1.0},
            max_children=1,
            execution_multiplier=multiplier,  # type: ignore[arg-type]
        )


def _write_cli_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    selected_file = tmp_path / "full-map-survivor.txt"
    stats_file = tmp_path / "mutmut-stats-full.json"
    output_file = tmp_path / "budget.json"
    selected, tests_by_function, durations = _hub_stats(
        fast_tests=1305, fast_seconds=1.0, slow_seconds=31.0
    )
    selected_file.write_text(selected[0] + "\n", encoding="utf-8")
    stats_file.write_text(
        json.dumps(
            {
                "tests_by_mangled_function_name": tests_by_function,
                "duration_by_test": durations,
            }
        ),
        encoding="utf-8",
    )
    return selected_file, stats_file, output_file


def _cli_argv(
    selected_file: Path, stats_file: Path, output_file: Path, *extra: str
) -> list[str]:
    return [
        "mutmut_shard_budget.py",
        "--selected-file",
        str(selected_file),
        "--stats",
        str(stats_file),
        "--max-children",
        "3",
        "--control-cycle-reserve-seconds",
        "5",
        "--metadata-startup-reserve-seconds",
        "120",
        "--max-timeout-seconds",
        str(DEFAULT_MAX_TIMEOUT_SECONDS),
        *extra,
        "--output",
        str(output_file),
    ]


def test_budget_cli_auto_records_both_the_request_and_the_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The uploaded artifact must show how far a confirmation degraded."""

    selected_file, stats_file, output_file = _write_cli_fixture(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        _cli_argv(
            selected_file,
            stats_file,
            output_file,
            "--execution-multiplier",
            "auto",
            "--min-execution-multiplier",
            str(MUTMUT_MINIMUM_EXECUTION_MULTIPLIER),
        ),
    )

    main()

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 3
    assert payload["execution_multiplier"] == MUTMUT_WALL_TIMEOUT_MULTIPLIER - 1
    assert payload["execution_multiplier_requested"] == "auto"
    assert payload["minimum_execution_multiplier"] == (
        MUTMUT_MINIMUM_EXECUTION_MULTIPLIER
    )
    assert payload["mutmut_watchdog_multiplier"] == MUTMUT_WALL_TIMEOUT_MULTIPLIER
    assert payload["outer_timeout_seconds"] <= DEFAULT_MAX_TIMEOUT_SECONDS
    assert capsys.readouterr().out.strip() == str(payload["outer_timeout_seconds"])


def test_budget_cli_without_the_flag_still_fails_closed_at_the_mutmut_watchdog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Omitting the flag must reproduce the pre-resolver behaviour exactly."""

    selected_file, stats_file, output_file = _write_cli_fixture(tmp_path)
    monkeypatch.setattr(sys, "argv", _cli_argv(selected_file, stats_file, output_file))

    with pytest.raises(SystemExit) as error:
        main()
    assert "exceeds the configured maximum" in str(error.value)
    assert not output_file.exists()


@pytest.mark.parametrize("multiplier", ["0", "16", "auto-ish", "2.5"])
def test_budget_cli_rejects_an_unusable_execution_multiplier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, multiplier: str
) -> None:
    selected_file, stats_file, output_file = _write_cli_fixture(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        _cli_argv(
            selected_file,
            stats_file,
            output_file,
            "--execution-multiplier",
            multiplier,
        ),
    )

    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert not output_file.exists()
