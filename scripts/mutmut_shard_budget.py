#!/usr/bin/env python3
"""Calculate a fail-closed outer timeout for one exact mutmut shard.

Mutmut 3.7.0 aborts a child after
``15 * (estimated_test_seconds + timeout_constant)`` wall seconds.  The
repository sets ``timeout_constant = 6`` so pytest's 120-second per-test
watchdog classifies a pathological mutant as a killed test before mutmut's
own watchdog records an incomplete timeout.  A shorter shell ``timeout`` can
still terminate a valid child before mutmut has classified it.  This helper
derives an upper bound from the same merged stats and exact IDs used by the
shard planner.  It also reserves parent-side watchdog polling, fork/reap,
registration, and metadata-persistence time for every selected child; those
costs are not part of a child's watchdog cap.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

MUTMUT_WALL_TIMEOUT_MULTIPLIER = 15
# Keep this synchronized with [tool.mutmut].timeout_constant in pyproject.toml.
# Six seconds intentionally exceeds pytest's 120-second child-test timeout for
# the shortest exact mutation shard while preserving a fail-closed outer cap.
MUTMUT_WALL_TIMEOUT_GRACE_SECONDS = 6
METADATA_AND_STARTUP_RESERVE_SECONDS = 900
SELECTED_TEST_PHASE_MULTIPLIER = 2
CONTROL_CYCLE_RESERVE_SECONDS = 15
TERMINATION_GRACE_SECONDS = 30
# Keep the CI cap below the six-hour mutation job envelope.  The workflow
# reserves 600 seconds for post-run evidence plus a 30-second kill grace, so a
# 20,000-second execution cap still leaves 1,570 seconds for setup and exit
# handling while covering the slowest stats-derived PR shards.
DEFAULT_MAX_TIMEOUT_SECONDS = 20_000
_GLOB_TOKENS = frozenset("*?[")


@dataclass(frozen=True, slots=True)
class ShardBudget:
    """Auditable upper-bound components for one exact mutmut invocation."""

    selected_count: int
    max_children: int
    selected_test_union_seconds: int
    pre_mutation_reserve_seconds: int
    watchdog_execution_cap_seconds: int
    control_cycle_count: int
    control_cycle_reserve_per_child_seconds: int
    control_cycle_reserve_seconds: int
    execution_cap_seconds: int
    termination_grace_seconds: int
    outer_timeout_seconds: int
    total_wall_cap_seconds: int

    def as_json(self, *, max_timeout_seconds: int) -> dict[str, int]:
        return {
            "schema_version": 2,
            "selected_count": self.selected_count,
            "max_children": self.max_children,
            "selected_test_union_seconds": self.selected_test_union_seconds,
            "pre_mutation_reserve_seconds": self.pre_mutation_reserve_seconds,
            "watchdog_execution_cap_seconds": self.watchdog_execution_cap_seconds,
            "control_cycle_count": self.control_cycle_count,
            "control_cycle_reserve_per_child_seconds": (
                self.control_cycle_reserve_per_child_seconds
            ),
            "control_cycle_reserve_seconds": self.control_cycle_reserve_seconds,
            "execution_cap_seconds": self.execution_cap_seconds,
            "termination_grace_seconds": self.termination_grace_seconds,
            "outer_timeout_seconds": self.outer_timeout_seconds,
            "total_wall_cap_seconds": self.total_wall_cap_seconds,
            "max_timeout_seconds": max_timeout_seconds,
        }


@dataclass(frozen=True, slots=True)
class _DurationTotal:
    """One deterministic duration sum before its one-sided integer rounding."""

    exact_seconds: Fraction
    fsum_seconds: float | None


def load_selected_mutants(path: Path) -> list[str]:
    """Load a non-empty exact selected-ID manifest."""
    try:
        names = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    except (OSError, UnicodeError) as exc:
        raise ValueError(
            f"unable to read selected mutant names from {path}: {exc}"
        ) from exc

    names = [name for name in names if name]
    if not names:
        raise ValueError("selected mutant names must not be empty")
    if len(names) != len(set(names)):
        raise ValueError("selected mutant names contain duplicates")
    if any(any(token in name for token in _GLOB_TOKENS) for name in names):
        raise ValueError(
            "selected mutant names must be exact; glob patterns are forbidden"
        )
    return names


def _load_stats(path: Path) -> tuple[dict[str, list[str]], dict[str, float]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read merged mutmut stats {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("merged mutmut stats must be a JSON object")

    try:
        raw_tests_by_function = payload["tests_by_mangled_function_name"]
        raw_durations = payload["duration_by_test"]
    except KeyError as exc:
        raise ValueError(f"merged mutmut stats missing required field: {exc}") from exc
    if not isinstance(raw_tests_by_function, dict) or not isinstance(
        raw_durations, dict
    ):
        raise ValueError("merged mutmut stats have an invalid schema")

    tests_by_function: dict[str, list[str]] = {}
    for function_name, test_names in raw_tests_by_function.items():
        if not isinstance(function_name, str) or not isinstance(test_names, list):
            raise ValueError("merged mutmut stats have an invalid test mapping")
        if not all(isinstance(test_name, str) for test_name in test_names):
            raise ValueError("merged mutmut stats have a non-string test identifier")
        tests_by_function[function_name] = test_names

    durations: dict[str, float] = {}
    for test_name, duration in raw_durations.items():
        if not isinstance(test_name, str):
            raise ValueError("merged mutmut stats have a non-string duration key")
        try:
            numeric_duration = float(duration)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"merged mutmut stats have a non-numeric duration for {test_name!r}"
            ) from exc
        if not math.isfinite(numeric_duration) or numeric_duration < 0:
            raise ValueError(
                f"merged mutmut stats have an invalid duration for {test_name!r}"
            )
        durations[test_name] = numeric_duration
    if not durations:
        raise ValueError("merged mutmut stats contain no active tests")
    return tests_by_function, durations


def _duration_total(
    test_names: Iterable[str], durations: Mapping[str, float]
) -> _DurationTotal:
    """Sum durations in canonical order without losing a positive sub-ULP tail.

    ``math.fsum`` makes the floating aggregate deterministic across hash seeds.
    ``Fraction.from_float`` retains each valid input float exactly until the final
    upward rounding, so a mathematically positive fraction cannot round down to
    a whole-second timeout.
    """

    ordered_durations = tuple(durations[test_name] for test_name in sorted(test_names))
    try:
        fsum_seconds: float | None = math.fsum(ordered_durations)
    except OverflowError:
        # The exact rational total remains usable for a fail-closed cap check.
        fsum_seconds = None
    exact_seconds = sum(
        (Fraction.from_float(duration) for duration in ordered_durations),
        start=Fraction(),
    )
    return _DurationTotal(
        exact_seconds=exact_seconds,
        fsum_seconds=fsum_seconds,
    )


def _conservative_ceil(total: _DurationTotal) -> int:
    """Return an integer that is never below the mathematical float total."""

    exact_ceiling = math.ceil(total.exact_seconds)
    if total.fsum_seconds is None:
        return exact_ceiling
    return max(exact_ceiling, math.ceil(total.fsum_seconds))


def _estimated_test_seconds(
    selected_mutants: Iterable[str],
    tests_by_function: Mapping[str, Sequence[str]],
    durations: Mapping[str, float],
) -> list[tuple[str, _DurationTotal]]:
    estimates: list[tuple[str, _DurationTotal]] = []
    for mutant_name in sorted(selected_mutants):
        function_name, separator, _ = mutant_name.partition("__mutmut_")
        if not separator:
            raise ValueError(f"invalid mutmut name without __mutmut_: {mutant_name}")
        test_names = tests_by_function.get(function_name, ())
        if not test_names:
            raise ValueError(
                "mutmut stats contain no mapped tests for selected mutant "
                f"{mutant_name!r}"
            )
        missing_durations = sorted(
            test_name for test_name in test_names if test_name not in durations
        )
        if missing_durations:
            raise ValueError(
                "mutmut stats contain missing durations for selected mutant "
                f"{mutant_name!r}: {missing_durations}"
            )
        estimates.append((mutant_name, _duration_total(test_names, durations)))
    return estimates


def _selected_test_union_seconds(
    selected_mutants: Iterable[str],
    tests_by_function: Mapping[str, Sequence[str]],
    durations: Mapping[str, float],
) -> int:
    """Return the de-duplicated mapped test duration for an exact shard."""

    selected_test_names: set[str] = set()
    for mutant_name in selected_mutants:
        function_name, separator, _ = mutant_name.partition("__mutmut_")
        if not separator:
            raise ValueError(f"invalid mutmut name without __mutmut_: {mutant_name}")
        test_names = tests_by_function.get(function_name, ())
        if not test_names:
            raise ValueError(
                "mutmut stats contain no mapped tests for selected mutant "
                f"{mutant_name!r}"
            )
        missing_durations = sorted(
            test_name for test_name in test_names if test_name not in durations
        )
        if missing_durations:
            raise ValueError(
                "mutmut stats contain missing durations for selected mutant "
                f"{mutant_name!r}: {missing_durations}"
            )
        selected_test_names.update(test_names)
    return _conservative_ceil(_duration_total(selected_test_names, durations))


def _schedule_execution_caps(
    estimates: Iterable[tuple[str, _DurationTotal]], *, max_children: int
) -> int:
    """Model mutmut's ascending-estimate fork schedule with wall watchdog caps."""
    if max_children < 1:
        raise ValueError("max_children must be positive")
    worker_loads = [0] * max_children
    heapq.heapify(worker_loads)
    for _mutant_name, estimate in sorted(
        estimates,
        key=lambda item: (item[1].exact_seconds, item[0]),
    ):
        watchdog_exact_seconds = MUTMUT_WALL_TIMEOUT_MULTIPLIER * (
            estimate.exact_seconds + MUTMUT_WALL_TIMEOUT_GRACE_SECONDS
        )
        watchdog_fsum_seconds = (
            None
            if estimate.fsum_seconds is None
            else MUTMUT_WALL_TIMEOUT_MULTIPLIER
            * (estimate.fsum_seconds + MUTMUT_WALL_TIMEOUT_GRACE_SECONDS)
        )
        worker_cap = _conservative_ceil(
            _DurationTotal(
                exact_seconds=watchdog_exact_seconds,
                fsum_seconds=watchdog_fsum_seconds,
            )
        )
        current_load = heapq.heappop(worker_loads)
        heapq.heappush(worker_loads, current_load + worker_cap)
    return max(worker_loads)


def _control_cycle_reserve(
    selected_count: int, *, reserve_per_child_seconds: int
) -> tuple[int, int]:
    """Reserve parent-side control work for every selected mutmut child.

    Each child completion can cause watchdog polling, a fork, a reap,
    registration, and metadata persistence.  Those operations can happen for
    every child within a concurrent wave, rather than once per wave, and sit
    outside the child watchdog budgets.  Charging the fixed reserve per exact
    selected child therefore remains conservative regardless of scheduling
    order or a partial final wave.
    """
    if selected_count < 1:
        raise ValueError("selected_count must be positive")
    if reserve_per_child_seconds < 1:
        raise ValueError("reserve_per_child_seconds must be positive")
    return (
        selected_count,
        selected_count * reserve_per_child_seconds,
    )


def calculate_shard_budget(
    selected_mutants: Sequence[str],
    tests_by_function: Mapping[str, Sequence[str]],
    durations: Mapping[str, float],
    *,
    max_children: int,
    control_cycle_reserve_seconds: int = CONTROL_CYCLE_RESERVE_SECONDS,
) -> ShardBudget:
    """Derive a conservative, stats-backed whole-process timeout."""
    if max_children < 1:
        raise ValueError("max_children must be positive")
    if control_cycle_reserve_seconds < 1:
        raise ValueError("control_cycle_reserve_seconds must be positive")
    if not selected_mutants:
        raise ValueError("selected mutant names must not be empty")
    if len(selected_mutants) != len(set(selected_mutants)):
        raise ValueError("selected mutant names contain duplicates")

    estimates = _estimated_test_seconds(selected_mutants, tests_by_function, durations)
    selected_test_union_seconds = _selected_test_union_seconds(
        selected_mutants, tests_by_function, durations
    )
    pre_mutation_reserve = (
        METADATA_AND_STARTUP_RESERVE_SECONDS
        + SELECTED_TEST_PHASE_MULTIPLIER * selected_test_union_seconds
    )
    watchdog_execution_cap = _schedule_execution_caps(
        estimates, max_children=max_children
    )
    control_cycle_count, control_cycle_reserve = _control_cycle_reserve(
        len(estimates),
        reserve_per_child_seconds=control_cycle_reserve_seconds,
    )
    execution_cap = watchdog_execution_cap + control_cycle_reserve
    outer_timeout = pre_mutation_reserve + execution_cap
    total_wall_cap = outer_timeout + TERMINATION_GRACE_SECONDS
    return ShardBudget(
        selected_count=len(selected_mutants),
        max_children=max_children,
        selected_test_union_seconds=selected_test_union_seconds,
        pre_mutation_reserve_seconds=pre_mutation_reserve,
        watchdog_execution_cap_seconds=watchdog_execution_cap,
        control_cycle_count=control_cycle_count,
        control_cycle_reserve_per_child_seconds=control_cycle_reserve_seconds,
        control_cycle_reserve_seconds=control_cycle_reserve,
        execution_cap_seconds=execution_cap,
        termination_grace_seconds=TERMINATION_GRACE_SECONDS,
        outer_timeout_seconds=outer_timeout,
        total_wall_cap_seconds=total_wall_cap,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selected-file", type=Path, required=True)
    parser.add_argument(
        "--stats",
        type=Path,
        default=Path("mutants/mutmut-stats.json"),
        help="merged mutmut test-duration mapping",
    )
    parser.add_argument("--max-children", type=int, required=True)
    parser.add_argument(
        "--control-cycle-reserve-seconds",
        type=int,
        default=CONTROL_CYCLE_RESERVE_SECONDS,
        help="parent orchestration reserve charged for every selected child",
    )
    parser.add_argument(
        "--max-timeout-seconds",
        type=int,
        default=DEFAULT_MAX_TIMEOUT_SECONDS,
        help="fail rather than exceed this CI-supported outer timeout",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.max_children < 1:
        parser.error("--max-children must be positive")
    if args.control_cycle_reserve_seconds < 1:
        parser.error("--control-cycle-reserve-seconds must be positive")
    if args.max_timeout_seconds < 1:
        parser.error("--max-timeout-seconds must be positive")
    return args


def main() -> None:
    """Write an auditable budget and print only its shell-safe timeout integer."""
    args = _parse_args()
    try:
        selected = load_selected_mutants(args.selected_file)
        tests_by_function, durations = _load_stats(args.stats)
        budget = calculate_shard_budget(
            selected,
            tests_by_function,
            durations,
            max_children=args.max_children,
            control_cycle_reserve_seconds=args.control_cycle_reserve_seconds,
        )
        if budget.outer_timeout_seconds > args.max_timeout_seconds:
            raise ValueError(
                "derived mutmut shard timeout exceeds the configured maximum: "
                f"required {budget.outer_timeout_seconds}s, "
                f"maximum {args.max_timeout_seconds}s"
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                budget.as_json(max_timeout_seconds=args.max_timeout_seconds), indent=2
            )
            + "\n",
            encoding="utf-8",
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise SystemExit(
            f"ERROR: unable to derive trustworthy mutmut budget: {exc}"
        ) from exc

    print(budget.outer_timeout_seconds)


if __name__ == "__main__":
    main()
