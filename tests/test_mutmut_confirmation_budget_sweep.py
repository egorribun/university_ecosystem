from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.mutmut_shard_budget import (
    DEFAULT_MAX_TIMEOUT_SECONDS,
    MUTMUT_MINIMUM_EXECUTION_MULTIPLIER,
    MUTMUT_WALL_TIMEOUT_MULTIPLIER,
)
from scripts.validate_mutmut_confirmation_budgets import (
    main,
    sweep_confirmation_budgets,
)

_SWEEP_KWARGS = {
    "max_children": 3,
    "control_cycle_reserve_seconds": 5,
    "metadata_and_startup_reserve_seconds": 120,
    "max_timeout_seconds": DEFAULT_MAX_TIMEOUT_SECONDS,
    "minimum_execution_multiplier": MUTMUT_MINIMUM_EXECUTION_MULTIPLIER,
}


def _universe(
    specs: dict[str, tuple[int, float, float]],
) -> tuple[dict[str, list[str]], dict[str, float]]:
    """Build ``tests_by_function``/``durations`` from (count, fast, slow) specs."""

    tests_by_function: dict[str, list[str]] = {}
    durations: dict[str, float] = {}
    for function_name, (count, fast_seconds, slow_seconds) in specs.items():
        names = [f"tests/{function_name}.py::test_{index}" for index in range(count)]
        slow_name = f"tests/{function_name}.py::test_slow"
        for name in names:
            durations[name] = fast_seconds
        durations[slow_name] = slow_seconds
        tests_by_function[function_name] = [*names, slow_name]
    return tests_by_function, durations


def test_sweep_reports_where_the_watchdog_contract_had_to_degrade() -> None:
    """A narrow function keeps 15x; a hub gives up only the steps it must."""

    tests_by_function, durations = _universe(
        {
            "app.module.x_narrow": (3, 1.0, 1.0),
            "app.core.logging.x__redact_pii": (1305, 1.0, 31.0),
            "app.core.database.x__on_checkout": (6012, 1.0, 68.0),
        }
    )

    sweep = sweep_confirmation_budgets(tests_by_function, durations, **_SWEEP_KWARGS)

    assert sweep.functions_checked == 3
    assert sweep.undeliverable_functions == ()
    assert sweep.resolved_multiplier_counts == {
        MUTMUT_WALL_TIMEOUT_MULTIPLIER: 1,
        MUTMUT_WALL_TIMEOUT_MULTIPLIER - 1: 1,
        MUTMUT_MINIMUM_EXECUTION_MULTIPLIER: 1,
    }
    assert sweep.worst_function == "app.core.logging.x__redact_pii"
    assert sweep.worst_outer_timeout_seconds <= DEFAULT_MAX_TIMEOUT_SECONDS


def test_sweep_skips_functions_mutmut_records_as_having_no_tests() -> None:
    """An unmapped function becomes "no tests", never a survivor to confirm."""

    tests_by_function, durations = _universe({"app.module.x_mapped": (2, 1.0, 1.0)})
    tests_by_function["app.module.x_unmapped"] = []

    sweep = sweep_confirmation_budgets(tests_by_function, durations, **_SWEEP_KWARGS)

    assert sweep.functions_checked == 1


def test_sweep_names_a_function_that_could_never_be_confirmed() -> None:
    """The whole point: fail once in the producer, naming the offender."""

    tests_by_function, durations = _universe(
        {
            "app.module.x_narrow": (3, 1.0, 1.0),
            "app.core.x_unbounded": (20_000, 1.0, 1.0),
        }
    )

    sweep = sweep_confirmation_budgets(tests_by_function, durations, **_SWEEP_KWARGS)

    assert [entry.function for entry in sweep.undeliverable_functions] == [
        "app.core.x_unbounded"
    ]
    offender = sweep.undeliverable_functions[0]
    assert offender.mapped_tests == 20_001
    assert offender.required_seconds > DEFAULT_MAX_TIMEOUT_SECONDS


def _write_stats(tmp_path: Path, specs: dict[str, tuple[int, float, float]]) -> Path:
    tests_by_function, durations = _universe(specs)
    stats_file = tmp_path / "mutmut-stats-full.json"
    stats_file.write_text(
        json.dumps(
            {
                "tests_by_mangled_function_name": tests_by_function,
                "duration_by_test": durations,
            }
        ),
        encoding="utf-8",
    )
    return stats_file


def _argv(stats_file: Path, output_file: Path, *extra: str) -> list[str]:
    return [
        "validate_mutmut_confirmation_budgets.py",
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
        "--min-execution-multiplier",
        str(MUTMUT_MINIMUM_EXECUTION_MULTIPLIER),
        *extra,
        "--output",
        str(output_file),
    ]


def test_sweep_cli_writes_the_report_and_succeeds_on_a_derivable_universe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stats_file = _write_stats(
        tmp_path,
        {
            "app.module.x_narrow": (3, 1.0, 1.0),
            "app.core.logging.x__redact_pii": (1305, 1.0, 31.0),
        },
    )
    output_file = tmp_path / "sweep.json"
    monkeypatch.setattr(sys, "argv", _argv(stats_file, output_file))

    main()

    report = json.loads(output_file.read_text(encoding="utf-8"))
    assert report["schema_version"] == 1
    assert report["mutmut_watchdog_multiplier"] == MUTMUT_WALL_TIMEOUT_MULTIPLIER
    assert report["undeliverable_functions"] == []
    assert "resolved multipliers" in capsys.readouterr().out


def test_sweep_cli_fails_closed_but_still_preserves_the_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing sweep must leave the report behind; it *is* the diagnosis."""

    stats_file = _write_stats(tmp_path, {"app.core.x_unbounded": (20_000, 1.0, 1.0)})
    output_file = tmp_path / "sweep.json"
    monkeypatch.setattr(sys, "argv", _argv(stats_file, output_file))

    with pytest.raises(SystemExit) as error:
        main()

    assert "could never have a survivor confirmed" in str(error.value)
    report = json.loads(output_file.read_text(encoding="utf-8"))
    assert report["undeliverable_functions"][0]["function"] == "app.core.x_unbounded"


@pytest.mark.parametrize("minimum", ["0", "16"])
def test_sweep_cli_rejects_a_floor_outside_the_watchdog_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, minimum: str
) -> None:
    stats_file = _write_stats(tmp_path, {"app.module.x_narrow": (3, 1.0, 1.0)})
    output_file = tmp_path / "sweep.json"
    argv = [
        arg
        for arg in _argv(stats_file, output_file)
        if arg
        not in {"--min-execution-multiplier", str(MUTMUT_MINIMUM_EXECUTION_MULTIPLIER)}
    ]
    monkeypatch.setattr(sys, "argv", [*argv, "--min-execution-multiplier", minimum])

    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert not output_file.exists()
