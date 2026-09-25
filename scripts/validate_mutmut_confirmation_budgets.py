#!/usr/bin/env python3
"""Prove every function's full-map survivor confirmation is still derivable.

The incremental gate confirms each primary survivor against the *complete*
mapped test set, so a confirmation is charged the union of every test that
touched the survivor's function.  For a hub function that union is most of the
suite, and mutmut's own 15x watchdog then derives a bound larger than GitHub's
hard 21_600-second job maximum -- underivable on any hosted runner.
``mutmut_shard_budget.resolve_execution_multiplier`` degrades the multiplier
only as far as the cap demands, but it cannot degrade below a floor that still
carries evidence.

Without this sweep, a function crossing that floor is discovered by 58 of 128
consumer jobs failing hours into a matrix (run 35488190240).  Running it in the
producer, where the merged stats already exist, turns the same fact into one
fast failure that names the offending functions.  The sweep is deliberately
independent of which mutants a given change selects: any function *could*
produce a survivor, so all of them must remain confirmable.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# The CI workflow invokes this file directly (like the other mutation helpers),
# while unit tests import it as ``scripts.validate_mutmut_confirmation_budgets``.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.mutmut_shard_budget import (
    CONTROL_CYCLE_RESERVE_SECONDS,
    DEFAULT_MAX_TIMEOUT_SECONDS,
    METADATA_AND_STARTUP_RESERVE_SECONDS,
    MUTMUT_MINIMUM_EXECUTION_MULTIPLIER,
    MUTMUT_WALL_TIMEOUT_MULTIPLIER,
    _load_stats,
    calculate_shard_budget,
    resolve_execution_multiplier,
)

_MUTANT_SUFFIX = "__mutmut_1"


class ConfirmationBudgetValidationError(ValueError):
    """Raised when a function could never have a survivor confirmed."""


@dataclass(frozen=True, slots=True)
class UndeliverableFunction:
    """One function whose survivor could never be confirmed in a hosted job."""

    function: str
    mapped_tests: int
    mapped_test_seconds: int
    required_seconds: int

    def as_json(self) -> dict[str, int | str]:
        return {
            "function": self.function,
            "mapped_tests": self.mapped_tests,
            "mapped_test_seconds": self.mapped_test_seconds,
            "required_seconds": self.required_seconds,
        }


@dataclass(frozen=True, slots=True)
class ConfirmationSweep:
    """Auditable proof that every mapped function stays confirmable."""

    functions_checked: int
    minimum_execution_multiplier: int
    max_timeout_seconds: int
    resolved_multiplier_counts: dict[int, int]
    worst_function: str
    worst_outer_timeout_seconds: int
    undeliverable_functions: tuple[UndeliverableFunction, ...]

    def as_json(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "functions_checked": self.functions_checked,
            "mutmut_watchdog_multiplier": MUTMUT_WALL_TIMEOUT_MULTIPLIER,
            "minimum_execution_multiplier": self.minimum_execution_multiplier,
            "max_timeout_seconds": self.max_timeout_seconds,
            "resolved_multiplier_counts": {
                str(multiplier): count
                for multiplier, count in sorted(
                    self.resolved_multiplier_counts.items(), reverse=True
                )
            },
            "worst_function": self.worst_function,
            "worst_outer_timeout_seconds": self.worst_outer_timeout_seconds,
            "undeliverable_functions": [
                entry.as_json() for entry in self.undeliverable_functions
            ],
        }


def sweep_confirmation_budgets(
    tests_by_function: dict[str, list[str]],
    durations: dict[str, float],
    *,
    max_children: int,
    control_cycle_reserve_seconds: int,
    metadata_and_startup_reserve_seconds: int,
    max_timeout_seconds: int,
    minimum_execution_multiplier: int,
) -> ConfirmationSweep:
    """Resolve a single-mutant confirmation budget for every mapped function."""

    resolved_multipliers: Counter[int] = Counter()
    undeliverable: list[UndeliverableFunction] = []
    worst_outer_seconds = 0
    worst_function = ""

    for function_name in sorted(tests_by_function):
        test_names = tests_by_function[function_name]
        if not test_names:
            # mutmut records a mutant with no mapped tests as "no tests"; it can
            # never become a survivor needing confirmation.
            continue
        if _MUTANT_SUFFIX.rstrip("1") in function_name:
            raise ConfirmationBudgetValidationError(
                f"function name is not a valid confirmation base: {function_name!r}"
            )
        selected = [function_name + _MUTANT_SUFFIX]
        shared = {
            "max_children": max_children,
            "control_cycle_reserve_seconds": control_cycle_reserve_seconds,
            "metadata_and_startup_reserve_seconds": (
                metadata_and_startup_reserve_seconds
            ),
        }
        try:
            budget = resolve_execution_multiplier(
                selected,
                tests_by_function,
                durations,
                max_timeout_seconds=max_timeout_seconds,
                minimum_execution_multiplier=minimum_execution_multiplier,
                **shared,
            )
        except ValueError:
            floor = calculate_shard_budget(
                selected,
                tests_by_function,
                durations,
                execution_multiplier=minimum_execution_multiplier,
                **shared,
            )
            undeliverable.append(
                UndeliverableFunction(
                    function=function_name,
                    mapped_tests=len(test_names),
                    mapped_test_seconds=floor.selected_test_union_seconds,
                    required_seconds=floor.outer_timeout_seconds,
                )
            )
            continue
        resolved_multipliers[budget.execution_multiplier] += 1
        if budget.outer_timeout_seconds > worst_outer_seconds:
            worst_outer_seconds = budget.outer_timeout_seconds
            worst_function = function_name

    return ConfirmationSweep(
        functions_checked=sum(resolved_multipliers.values()) + len(undeliverable),
        minimum_execution_multiplier=minimum_execution_multiplier,
        max_timeout_seconds=max_timeout_seconds,
        resolved_multiplier_counts=dict(resolved_multipliers),
        worst_function=worst_function,
        worst_outer_timeout_seconds=worst_outer_seconds,
        undeliverable_functions=tuple(undeliverable),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stats",
        type=Path,
        default=Path("mutants/mutmut-stats-full.json"),
        help="complete (unreduced) mutmut test-duration mapping",
    )
    parser.add_argument("--max-children", type=int, required=True)
    parser.add_argument(
        "--control-cycle-reserve-seconds",
        type=int,
        default=CONTROL_CYCLE_RESERVE_SECONDS,
    )
    parser.add_argument(
        "--metadata-startup-reserve-seconds",
        type=int,
        default=METADATA_AND_STARTUP_RESERVE_SECONDS,
    )
    parser.add_argument(
        "--max-timeout-seconds",
        type=int,
        default=DEFAULT_MAX_TIMEOUT_SECONDS,
        help="the consumer's outer cap; pass the stricter producer value",
    )
    parser.add_argument(
        "--min-execution-multiplier",
        type=int,
        default=MUTMUT_MINIMUM_EXECUTION_MULTIPLIER,
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
    if not 1 <= args.min_execution_multiplier <= MUTMUT_WALL_TIMEOUT_MULTIPLIER:
        parser.error(
            "--min-execution-multiplier must be between 1 and "
            f"{MUTMUT_WALL_TIMEOUT_MULTIPLIER}"
        )
    return args


def main() -> None:
    """Write an auditable sweep and fail closed on any undeliverable function."""
    args = _parse_args()
    try:
        tests_by_function, durations = _load_stats(args.stats)
        sweep = sweep_confirmation_budgets(
            tests_by_function,
            durations,
            max_children=args.max_children,
            control_cycle_reserve_seconds=args.control_cycle_reserve_seconds,
            metadata_and_startup_reserve_seconds=(
                args.metadata_startup_reserve_seconds
            ),
            max_timeout_seconds=args.max_timeout_seconds,
            minimum_execution_multiplier=args.min_execution_multiplier,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(sweep.as_json(), indent=2) + "\n", encoding="utf-8"
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise SystemExit(
            f"ERROR: unable to sweep mutmut confirmation budgets: {exc}"
        ) from exc

    print(
        f"mutmut confirmation budgets: {sweep.functions_checked} functions, "
        "resolved multipliers "
        + ", ".join(
            f"{multiplier}x={count}"
            for multiplier, count in sorted(
                sweep.resolved_multiplier_counts.items(), reverse=True
            )
        )
        + f"; worst {sweep.worst_outer_timeout_seconds}s "
        f"({sweep.worst_function})"
    )

    if sweep.undeliverable_functions:
        for entry in sweep.undeliverable_functions:
            print(
                "::error::Full-map confirmation is underivable for "
                f"{entry.function}: {entry.mapped_tests} mapped tests "
                f"({entry.mapped_test_seconds}s) require "
                f"{entry.required_seconds}s at the minimum multiplier "
                f"{sweep.minimum_execution_multiplier}, above the "
                f"{sweep.max_timeout_seconds}s cap.",
                file=sys.stderr,
            )
        raise SystemExit(
            "ERROR: unable to sweep mutmut confirmation budgets: "
            f"{len(sweep.undeliverable_functions)} function(s) could never have "
            "a survivor confirmed within the job envelope"
        )


if __name__ == "__main__":
    main()
