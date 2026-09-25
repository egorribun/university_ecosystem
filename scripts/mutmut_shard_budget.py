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

A caller may lower the watchdog multiplier below mutmut's own via
``execution_multiplier``, and ``resolve_execution_multiplier`` picks the
largest value that still fits a cap.  That is required, not merely
convenient: a hub function mapped to the whole suite derives a 15x budget of
97_567 seconds, and even a 1_335-second union derives 21_611 seconds against
GitHub's hard 21_600-second job maximum, so the full watchdog bound cannot fit
in *any* hosted job (measured in run 35488190240).  Lowering it is safe
because the 15x watchdog is a backstop that should never fire: pytest's own
``--timeout=120 --timeout-method=signal`` (pyproject.toml) is what detects a
mutant-induced hang, and mutmut's ``-x`` aborts at the first failing test.
When the shorter shell cap does preempt a run, the caller sees exit 124 and
must fail closed; it can never turn an unconfirmed mutant into a passing one.
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
# Smallest watchdog multiplier a caller may degrade to.  Two full passes of a
# mutant's complete mapped union is the floor at which a confirmation still
# carries evidence; below that a slow-but-healthy mutant would be preempted
# routinely.  Sweeping the 1_814-function universe of run 35488190240 shows
# 1_799 functions still fit at the full 15x, seven (the app/core/logging.py PII
# helpers) resolve to 14, and the eight whole-suite hubs resolve to exactly 2 —
# so this floor is the smallest value that keeps every function derivable.
MUTMUT_MINIMUM_EXECUTION_MULTIPLIER = 2
# Keep this synchronized with [tool.mutmut].timeout_constant in pyproject.toml.
# Six seconds intentionally exceeds pytest's 120-second child-test timeout for
# the shortest exact mutation shard while preserving a fail-closed outer cap.
MUTMUT_WALL_TIMEOUT_GRACE_SECONDS = 6
METADATA_AND_STARTUP_RESERVE_SECONDS = 900
CONTROL_CYCLE_RESERVE_SECONDS = 15
TERMINATION_GRACE_SECONDS = 30
# Keep the CI cap below the six-hour mutation job envelope.  The workflow
# reserves 600 seconds for post-run evidence and 30 seconds for timeout's KILL
# grace, leaving an exact maximum outer timeout of 20_970 seconds:
# 21_600 - 600 - 30 = 20_970.  The job's live deadline check starts before
# setup, subtracts the same post-run/kill reserves from the remaining deadline,
# and remains authoritative when setup consumes part of that budget.  This cap
# is not a license to truncate evidence.
MUTMUT_JOB_DEADLINE_SECONDS = 21_600
MUTMUT_POST_RUN_UPLOAD_RESERVE_SECONDS = 600
MUTMUT_TIMEOUT_KILL_GRACE_SECONDS = 30
DEFAULT_MAX_TIMEOUT_SECONDS = (
    MUTMUT_JOB_DEADLINE_SECONDS
    - MUTMUT_POST_RUN_UPLOAD_RESERVE_SECONDS
    - MUTMUT_TIMEOUT_KILL_GRACE_SECONDS
)
_GLOB_TOKENS = frozenset("*?[")


@dataclass(frozen=True, slots=True)
class ShardBudget:
    """Auditable upper-bound components for one exact mutmut invocation."""

    selected_count: int
    max_children: int
    selected_test_union_seconds: int
    forced_fail_test_seconds: int
    metadata_and_startup_reserve_seconds: int
    pre_mutation_reserve_seconds: int
    execution_multiplier: int
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
            # 3: execution_cap_seconds is no longer reconstructible from the
            # mutmut watchdog multiplier alone; read execution_multiplier.
            "schema_version": 3,
            "selected_count": self.selected_count,
            "max_children": self.max_children,
            "selected_test_union_seconds": self.selected_test_union_seconds,
            "forced_fail_test_seconds": self.forced_fail_test_seconds,
            "metadata_and_startup_reserve_seconds": (
                self.metadata_and_startup_reserve_seconds
            ),
            "pre_mutation_reserve_seconds": self.pre_mutation_reserve_seconds,
            "execution_multiplier": self.execution_multiplier,
            "mutmut_watchdog_multiplier": MUTMUT_WALL_TIMEOUT_MULTIPLIER,
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
        if isinstance(duration, bool):
            raise ValueError(
                f"merged mutmut stats have an invalid duration for {test_name!r}"
            )
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


def _validated_duration_map(durations: Mapping[str, float]) -> dict[str, float]:
    """Normalize direct callers to the same strict duration contract as JSON."""

    validated: dict[str, float] = {}
    for test_name, duration in durations.items():
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            raise ValueError(
                f"merged mutmut stats have an invalid duration for {test_name!r}"
            )
        numeric_duration = float(duration)
        if not math.isfinite(numeric_duration) or numeric_duration < 0:
            raise ValueError(
                f"merged mutmut stats have an invalid duration for {test_name!r}"
            )
        validated[test_name] = numeric_duration
    return validated


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


def _selected_test_names(
    selected_mutants: Iterable[str],
    tests_by_function: Mapping[str, Sequence[str]],
    durations: Mapping[str, float],
) -> set[str]:
    """Return the validated de-duplicated test IDs for an exact shard."""

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
    return selected_test_names


def _selected_test_union_seconds(
    selected_mutants: Iterable[str],
    tests_by_function: Mapping[str, Sequence[str]],
    durations: Mapping[str, float],
) -> int:
    """Return the de-duplicated mapped clean-test duration for an exact shard."""

    selected_test_names = _selected_test_names(
        selected_mutants, tests_by_function, durations
    )
    return _conservative_ceil(_duration_total(selected_test_names, durations))


def _forced_fail_test_seconds(
    selected_mutants: Iterable[str],
    tests_by_function: Mapping[str, Sequence[str]],
    durations: Mapping[str, float],
) -> int:
    """Bound mutmut's forced-fail phase to its first failing test.

    ``run_mutmut_with_stats.py`` scopes the forced-fail invocation to the same
    mapped union as the clean baseline, while the repository's mutmut pytest
    arguments include ``-x``.  ``MUTANT_UNDER_TEST=fail`` therefore stops at
    the first test that reaches a selected trampoline; charging the slowest
    mapped test is a conservative bound without paying for the full union a
    second time.  The clean phase remains fully charged by
    ``_selected_test_union_seconds`` above.
    """

    selected_test_names = _selected_test_names(
        selected_mutants, tests_by_function, durations
    )
    if not selected_test_names:
        raise ValueError("mutmut stats contain no mapped tests for selected mutants")
    return max(
        _conservative_ceil(_duration_total((test_name,), durations))
        for test_name in selected_test_names
    )


def _schedule_execution_caps(
    estimates: Iterable[tuple[str, _DurationTotal]],
    *,
    max_children: int,
    execution_multiplier: int,
) -> int:
    """Model mutmut's ascending-estimate fork schedule with wall watchdog caps.

    ``execution_multiplier`` is deliberately required rather than defaulted so
    a new call site cannot silently inherit mutmut's 15x watchdog; the default
    lives only on the public boundary in ``calculate_shard_budget``.
    """
    if max_children < 1:
        raise ValueError("max_children must be positive")
    worker_loads = [0] * max_children
    heapq.heapify(worker_loads)
    for _mutant_name, estimate in sorted(
        estimates,
        key=lambda item: (item[1].exact_seconds, item[0]),
    ):
        watchdog_exact_seconds = execution_multiplier * (
            estimate.exact_seconds + MUTMUT_WALL_TIMEOUT_GRACE_SECONDS
        )
        watchdog_fsum_seconds = (
            None
            if estimate.fsum_seconds is None
            else execution_multiplier
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


def _validate_execution_multiplier(execution_multiplier: int) -> None:
    """Reject a multiplier that would make the derived bound meaningless.

    The upper bound is the load-bearing half.  Above mutmut's own watchdog the
    shell ``timeout`` would be more permissive than the cap mutmut already
    enforces, so the derived integer stops being an upper bound on real wall
    cost.  Callers who need more startup headroom must raise
    ``metadata_and_startup_reserve_seconds``, which is what it is for.
    """
    if (
        isinstance(execution_multiplier, bool)
        or not isinstance(execution_multiplier, int)
        or not 1 <= execution_multiplier <= MUTMUT_WALL_TIMEOUT_MULTIPLIER
    ):
        raise ValueError(
            "execution_multiplier must be an integer between 1 and "
            f"{MUTMUT_WALL_TIMEOUT_MULTIPLIER}"
        )


def calculate_shard_budget(
    selected_mutants: Sequence[str],
    tests_by_function: Mapping[str, Sequence[str]],
    durations: Mapping[str, float],
    *,
    max_children: int,
    control_cycle_reserve_seconds: int = CONTROL_CYCLE_RESERVE_SECONDS,
    metadata_and_startup_reserve_seconds: int = METADATA_AND_STARTUP_RESERVE_SECONDS,
    execution_multiplier: int = MUTMUT_WALL_TIMEOUT_MULTIPLIER,
) -> ShardBudget:
    """Derive a conservative, stats-backed whole-process timeout."""
    if max_children < 1:
        raise ValueError("max_children must be positive")
    if control_cycle_reserve_seconds < 1:
        raise ValueError("control_cycle_reserve_seconds must be positive")
    _validate_execution_multiplier(execution_multiplier)
    if (
        isinstance(metadata_and_startup_reserve_seconds, bool)
        or not isinstance(metadata_and_startup_reserve_seconds, int)
        or metadata_and_startup_reserve_seconds < 0
    ):
        raise ValueError("metadata_and_startup_reserve_seconds must be non-negative")
    if not selected_mutants:
        raise ValueError("selected mutant names must not be empty")
    if len(selected_mutants) != len(set(selected_mutants)):
        raise ValueError("selected mutant names contain duplicates")

    validated_durations = _validated_duration_map(durations)
    estimates = _estimated_test_seconds(
        selected_mutants, tests_by_function, validated_durations
    )
    selected_test_union_seconds = _selected_test_union_seconds(
        selected_mutants, tests_by_function, validated_durations
    )
    forced_fail_test_seconds = _forced_fail_test_seconds(
        selected_mutants, tests_by_function, validated_durations
    )
    pre_mutation_reserve = (
        metadata_and_startup_reserve_seconds
        + selected_test_union_seconds
        + forced_fail_test_seconds
    )
    watchdog_execution_cap = _schedule_execution_caps(
        estimates,
        max_children=max_children,
        execution_multiplier=execution_multiplier,
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
        forced_fail_test_seconds=forced_fail_test_seconds,
        metadata_and_startup_reserve_seconds=metadata_and_startup_reserve_seconds,
        pre_mutation_reserve_seconds=pre_mutation_reserve,
        execution_multiplier=execution_multiplier,
        watchdog_execution_cap_seconds=watchdog_execution_cap,
        control_cycle_count=control_cycle_count,
        control_cycle_reserve_per_child_seconds=control_cycle_reserve_seconds,
        control_cycle_reserve_seconds=control_cycle_reserve,
        execution_cap_seconds=execution_cap,
        termination_grace_seconds=TERMINATION_GRACE_SECONDS,
        outer_timeout_seconds=outer_timeout,
        total_wall_cap_seconds=total_wall_cap,
    )


def resolve_execution_multiplier(
    selected_mutants: Sequence[str],
    tests_by_function: Mapping[str, Sequence[str]],
    durations: Mapping[str, float],
    *,
    max_children: int,
    max_timeout_seconds: int,
    control_cycle_reserve_seconds: int = CONTROL_CYCLE_RESERVE_SECONDS,
    metadata_and_startup_reserve_seconds: int = METADATA_AND_STARTUP_RESERVE_SECONDS,
    minimum_execution_multiplier: int = MUTMUT_MINIMUM_EXECUTION_MULTIPLIER,
) -> ShardBudget:
    """Return the budget for the largest multiplier that still fits the cap.

    Degrading only as far as the cap demands keeps mutmut's full 15x watchdog
    contract for every shard that can afford it, and spends the reduction only
    where the platform makes the full bound underivable.  Failing closed when
    even ``minimum_execution_multiplier`` overruns is deliberate: that is a
    shard no hosted runner can confirm, and silently truncating it would trade
    a loud scheduling failure for quiet evidence loss.
    """
    _validate_execution_multiplier(minimum_execution_multiplier)

    def _budget(multiplier: int) -> ShardBudget:
        return calculate_shard_budget(
            selected_mutants,
            tests_by_function,
            durations,
            max_children=max_children,
            control_cycle_reserve_seconds=control_cycle_reserve_seconds,
            metadata_and_startup_reserve_seconds=(metadata_and_startup_reserve_seconds),
            execution_multiplier=multiplier,
        )

    # Reject the underivable shard before searching: if the floor overruns, no
    # larger multiplier can fit either, and the floor is the number to report.
    floor_budget = _budget(minimum_execution_multiplier)
    if floor_budget.outer_timeout_seconds > max_timeout_seconds:
        raise ValueError(
            "derived mutmut shard timeout exceeds the configured maximum: "
            f"required {floor_budget.outer_timeout_seconds}s, "
            f"maximum {max_timeout_seconds}s "
            f"at the minimum execution multiplier {minimum_execution_multiplier}"
        )
    for multiplier in range(
        MUTMUT_WALL_TIMEOUT_MULTIPLIER, minimum_execution_multiplier, -1
    ):
        budget = _budget(multiplier)
        if budget.outer_timeout_seconds <= max_timeout_seconds:
            return budget
    return floor_budget


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
        "--metadata-startup-reserve-seconds",
        type=int,
        default=METADATA_AND_STARTUP_RESERVE_SECONDS,
        help=(
            "reserve for metadata/startup work outside the selected-test phase; "
            "reuse-generated-universe callers may provide an evidence-backed value"
        ),
    )
    parser.add_argument(
        "--max-timeout-seconds",
        type=int,
        default=DEFAULT_MAX_TIMEOUT_SECONDS,
        help="fail rather than exceed this CI-supported outer timeout",
    )
    parser.add_argument(
        "--execution-multiplier",
        default=str(MUTMUT_WALL_TIMEOUT_MULTIPLIER),
        help=(
            "watchdog multiplier charged per child, or 'auto' to take the "
            "largest one that still fits --max-timeout-seconds; only "
            "full-map survivor confirmation may degrade below mutmut's own"
        ),
    )
    parser.add_argument(
        "--min-execution-multiplier",
        type=int,
        default=MUTMUT_MINIMUM_EXECUTION_MULTIPLIER,
        help="floor for --execution-multiplier auto; fail closed below it",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.max_children < 1:
        parser.error("--max-children must be positive")
    if args.control_cycle_reserve_seconds < 1:
        parser.error("--control-cycle-reserve-seconds must be positive")
    if args.metadata_startup_reserve_seconds < 0:
        parser.error("--metadata-startup-reserve-seconds must be non-negative")
    if args.max_timeout_seconds < 1:
        parser.error("--max-timeout-seconds must be positive")
    if args.execution_multiplier != "auto":
        try:
            args.execution_multiplier = int(args.execution_multiplier)
        except ValueError:
            parser.error("--execution-multiplier must be an integer or 'auto'")
        if not 1 <= args.execution_multiplier <= MUTMUT_WALL_TIMEOUT_MULTIPLIER:
            parser.error(
                "--execution-multiplier must be between 1 and "
                f"{MUTMUT_WALL_TIMEOUT_MULTIPLIER}"
            )
    if not 1 <= args.min_execution_multiplier <= MUTMUT_WALL_TIMEOUT_MULTIPLIER:
        parser.error(
            "--min-execution-multiplier must be between 1 and "
            f"{MUTMUT_WALL_TIMEOUT_MULTIPLIER}"
        )
    return args


def main() -> None:
    """Write an auditable budget and print only its shell-safe timeout integer."""
    args = _parse_args()
    try:
        selected = load_selected_mutants(args.selected_file)
        tests_by_function, durations = _load_stats(args.stats)
        if args.execution_multiplier == "auto":
            budget = resolve_execution_multiplier(
                selected,
                tests_by_function,
                durations,
                max_children=args.max_children,
                max_timeout_seconds=args.max_timeout_seconds,
                control_cycle_reserve_seconds=args.control_cycle_reserve_seconds,
                metadata_and_startup_reserve_seconds=(
                    args.metadata_startup_reserve_seconds
                ),
                minimum_execution_multiplier=args.min_execution_multiplier,
            )
        else:
            budget = calculate_shard_budget(
                selected,
                tests_by_function,
                durations,
                max_children=args.max_children,
                control_cycle_reserve_seconds=args.control_cycle_reserve_seconds,
                metadata_and_startup_reserve_seconds=(
                    args.metadata_startup_reserve_seconds
                ),
                execution_multiplier=args.execution_multiplier,
            )
            if budget.outer_timeout_seconds > args.max_timeout_seconds:
                raise ValueError(
                    "derived mutmut shard timeout exceeds the configured maximum: "
                    f"required {budget.outer_timeout_seconds}s, "
                    f"maximum {args.max_timeout_seconds}s"
                )
        payload: dict[str, int | str] = dict(
            budget.as_json(max_timeout_seconds=args.max_timeout_seconds)
        )
        # Record what the caller asked for, so the uploaded artifact shows both
        # the requested policy and the multiplier it actually resolved to.
        payload["execution_multiplier_requested"] = str(args.execution_multiplier)
        payload["minimum_execution_multiplier"] = args.min_execution_multiplier
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise SystemExit(
            f"ERROR: unable to derive trustworthy mutmut budget: {exc}"
        ) from exc

    print(budget.outer_timeout_seconds)


if __name__ == "__main__":
    main()
