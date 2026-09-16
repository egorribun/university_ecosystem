"""Plan exact mutmut mutants into duration-balanced CI shards.

The helper imports mutmut lazily because mutmut is POSIX-only while the
repository's contract tests also run on Windows.  CI generates the normal
mutmut universe once per mutation job, reads the complete merged test-time
map, and writes only the exact mutant names assigned to that job.  Callers
that provide the complete timeout contract use the budget-aware planner so
the output is checked against mutmut's watchdog schedule before publication.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import re
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

if not __package__:  # pragma: no cover - direct CI script entry point
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.mutmut_shard_budget import (
    CONTROL_CYCLE_RESERVE_SECONDS,
    METADATA_AND_STARTUP_RESERVE_SECONDS,
    MUTMUT_WALL_TIMEOUT_GRACE_SECONDS,
    MUTMUT_WALL_TIMEOUT_MULTIPLIER,
)
from scripts.mutmut_universe import (
    prepare_mutants_directory,
    prepare_reused_generation,
    write_universe_manifest,
)


@dataclass(frozen=True, slots=True)
class MutantEstimate:
    """One mutant and the estimated cost of its associated tests."""

    name: str
    estimated_seconds: float


@dataclass(frozen=True, slots=True)
class _BudgetMutant:
    """A validated mutant cost used by the budget-aware planner."""

    name: str
    estimate_exact_seconds: Fraction
    estimate_fsum_seconds: float
    test_names: tuple[str, ...]
    watchdog_cap_seconds: int
    forced_fail_cap_seconds: int


@dataclass(slots=True)
class _BudgetBin:
    """Mutable state for one deterministic budget-aware logical shard."""

    names: list[str]
    mutants: list[_BudgetMutant]
    test_names: set[str]
    union_exact_seconds: Fraction
    union_fsum_seconds: float | None
    forced_fail_cap_seconds: int


ChangedLineRanges = Mapping[str, Sequence[tuple[int, int]]]


def normalize_source_path(path: str | Path) -> str:
    """Return a repository-relative path in the CI manifest format."""

    normalized = str(path).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def parse_unified_diff_line_ranges(diff_text: str) -> dict[str, list[tuple[int, int]]]:
    """Return changed new-file line ranges from a zero-context git diff."""

    ranges_by_path: dict[str, list[tuple[int, int]]] = defaultdict(list)
    current_path: str | None = None
    hunk_pattern = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @")

    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            raw_path = line[4:].strip()
            if raw_path == "/dev/null":
                current_path = None
                continue
            current_path = normalize_source_path(raw_path.removeprefix("b/"))
            ranges_by_path.setdefault(current_path, [])
            continue

        match = hunk_pattern.match(line)
        if not match or current_path is None:
            continue

        start = int(match.group(1))
        count = int(match.group(2) or "1")
        if count:
            ranges_by_path[current_path].append((start, start + count - 1))

    return dict(ranges_by_path)


def estimate_mutant_times(
    mutant_names: Iterable[str],
    tests_by_mangled_function_name: Mapping[str, Sequence[str]],
    duration_by_test: Mapping[str, float | int],
) -> list[MutantEstimate]:
    """Attach mutmut's worst-case test estimate to every unique mutant."""

    durations: dict[str, float] = {}
    for test_name, duration in duration_by_test.items():
        # ``bool`` is an ``int`` subclass, but accepting True/False here would
        # silently turn malformed stats into one-second/zero-second budgets.
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            raise ValueError(
                "mutmut test durations must be finite non-negative numbers: "
                f"{test_name!r}"
            )
        value = float(duration)
        if not math.isfinite(value) or value < 0:
            raise ValueError(
                "mutmut test durations must be finite non-negative numbers: "
                f"{test_name!r}"
            )
        durations[test_name] = value
    estimates: list[MutantEstimate] = []
    for mutant_name in sorted(set(mutant_names)):
        mangled_name, separator, _ = mutant_name.partition("__mutmut_")
        if not separator:
            raise ValueError(f"Invalid mutmut name without __mutmut_: {mutant_name}")
        associated_tests = tests_by_mangled_function_name.get(mangled_name, ())
        if not associated_tests:
            raise ValueError(
                "mutmut stats contain no mapped tests for planned mutant "
                f"{mutant_name!r}"
            )
        missing_durations = sorted(
            test_name for test_name in associated_tests if test_name not in durations
        )
        if missing_durations:
            raise ValueError(
                "mutmut stats contain missing durations for planned mutant "
                f"{mutant_name!r}: {missing_durations}"
            )
        estimated_seconds = math.fsum(
            durations[test_name] for test_name in associated_tests
        )
        if not math.isfinite(estimated_seconds):
            raise ValueError(
                f"mutmut estimated duration is not finite: {mutant_name!r}"
            )
        estimates.append(
            MutantEstimate(
                name=mutant_name,
                estimated_seconds=estimated_seconds,
            )
        )
    return estimates


def plan_mutant_shards(
    estimates: Iterable[MutantEstimate], *, num_shards: int
) -> list[list[str]]:
    """Greedily balance exact mutants by estimated test duration.

    Long mutants are assigned first to the currently lightest shard.  The
    stable name tie-breaker makes the plan reproducible, while a zero-duration
    fallback naturally balances by mutant count when no timing is available.
    """

    if num_shards < 1:
        raise ValueError("num_shards must be positive")

    shard_names: list[list[str]] = [[] for _ in range(num_shards)]
    shard_loads = [0.0] * num_shards
    ordered_estimates = sorted(
        estimates,
        key=lambda estimate: (-estimate.estimated_seconds, estimate.name),
    )
    for estimate in ordered_estimates:
        shard_index = min(
            range(num_shards),
            key=lambda index: (shard_loads[index], len(shard_names[index]), index),
        )
        shard_names[shard_index].append(estimate.name)
        shard_loads[shard_index] += estimate.estimated_seconds
    return shard_names


def _duration_ceil(value: float) -> int:
    """Return the conservative integer ceiling used by the budget helper."""

    exact = Fraction.from_float(value)
    return max(math.ceil(exact), math.ceil(value))


def _budget_mutants(
    estimates: Sequence[MutantEstimate],
    tests_by_mangled_function_name: Mapping[str, Sequence[str]],
    duration_by_test: Mapping[str, float | int],
) -> list[_BudgetMutant]:
    """Normalize planner inputs into the same per-mutant costs as mutmut."""

    durations: dict[str, float] = {}
    for test_name, duration in duration_by_test.items():
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            raise ValueError(
                "mutmut test durations must be finite non-negative numbers: "
                f"{test_name!r}"
            )
        value = float(duration)
        if not math.isfinite(value) or value < 0:
            raise ValueError(
                "mutmut test durations must be finite non-negative numbers: "
                f"{test_name!r}"
            )
        durations[test_name] = value

    names = [estimate.name for estimate in estimates]
    if len(names) != len(set(names)):
        raise ValueError("mutant estimates contain duplicate names")

    normalized: list[_BudgetMutant] = []
    for estimate in estimates:
        function_name, separator, _ = estimate.name.partition("__mutmut_")
        if not separator:
            raise ValueError(f"Invalid mutmut name without __mutmut_: {estimate.name}")
        associated_tests = tests_by_mangled_function_name.get(function_name, ())
        if not associated_tests:
            raise ValueError(
                "mutmut stats contain no mapped tests for planned mutant "
                f"{estimate.name!r}"
            )
        missing_durations = sorted(
            test_name for test_name in associated_tests if test_name not in durations
        )
        if missing_durations:
            raise ValueError(
                "mutmut stats contain missing durations for planned mutant "
                f"{estimate.name!r}: {missing_durations}"
            )

        ordered_tests = tuple(sorted(set(associated_tests)))
        exact_seconds = sum(
            (Fraction.from_float(durations[test_name]) for test_name in ordered_tests),
            start=Fraction(),
        )
        try:
            fsum_seconds = math.fsum(
                durations[test_name] for test_name in ordered_tests
            )
        except OverflowError as error:
            raise ValueError(
                f"mutmut estimated duration is not finite: {estimate.name!r}"
            ) from error
        if not math.isfinite(fsum_seconds):
            raise ValueError(
                f"mutmut estimated duration is not finite: {estimate.name!r}"
            )

        watchdog_exact = MUTMUT_WALL_TIMEOUT_MULTIPLIER * (
            exact_seconds + MUTMUT_WALL_TIMEOUT_GRACE_SECONDS
        )
        watchdog_fsum = MUTMUT_WALL_TIMEOUT_MULTIPLIER * (
            fsum_seconds + MUTMUT_WALL_TIMEOUT_GRACE_SECONDS
        )
        watchdog_cap = max(math.ceil(watchdog_exact), math.ceil(watchdog_fsum))
        forced_fail_cap = max(
            _duration_ceil(durations[test_name]) for test_name in ordered_tests
        )
        normalized.append(
            _BudgetMutant(
                name=estimate.name,
                estimate_exact_seconds=exact_seconds,
                estimate_fsum_seconds=fsum_seconds,
                test_names=tuple(sorted(set(associated_tests))),
                watchdog_cap_seconds=watchdog_cap,
                forced_fail_cap_seconds=forced_fail_cap,
            )
        )
    return normalized


def _budget_bin_upper_bound(
    bucket: _BudgetBin,
    candidate: _BudgetMutant,
    *,
    durations: Mapping[str, float | int],
    max_children: int,
    control_cycle_reserve_seconds: int,
    metadata_and_startup_reserve_seconds: int,
) -> int:
    """Compute a conservative candidate budget without reparsing stats."""

    mutants = [*bucket.mutants, candidate]
    worker_loads = [0] * max_children
    for mutant in sorted(
        mutants, key=lambda item: (item.estimate_exact_seconds, item.name)
    ):
        worker_index = min(
            range(max_children), key=lambda index: (worker_loads[index], index)
        )
        worker_loads[worker_index] += mutant.watchdog_cap_seconds

    new_tests = sorted(set(candidate.test_names).difference(bucket.test_names))
    new_exact = sum(
        (Fraction.from_float(float(durations[test_name])) for test_name in new_tests),
        start=Fraction(),
    )
    union_exact = bucket.union_exact_seconds + new_exact
    union_fsum: float | None = None
    if bucket.union_fsum_seconds is not None:
        try:
            union_fsum = math.fsum(
                [
                    bucket.union_fsum_seconds,
                    *(float(durations[test_name]) for test_name in new_tests),
                ]
            )
        except OverflowError:
            pass
    union_upper = math.ceil(union_exact)
    if union_fsum is not None:
        union_upper = max(union_upper, math.ceil(union_fsum))
    return (
        metadata_and_startup_reserve_seconds
        + union_upper
        + max(bucket.forced_fail_cap_seconds, candidate.forced_fail_cap_seconds)
        + max(worker_loads)
        + control_cycle_reserve_seconds * len(mutants)
    )


def _add_budget_mutant(
    bucket: _BudgetBin,
    mutant: _BudgetMutant,
    durations: Mapping[str, float | int],
) -> None:
    """Apply a selected candidate to a budget-bin state."""

    new_tests = sorted(set(mutant.test_names).difference(bucket.test_names))
    bucket.names.append(mutant.name)
    bucket.mutants.append(mutant)
    bucket.test_names.update(new_tests)
    bucket.union_exact_seconds += sum(
        (Fraction.from_float(float(durations[test_name])) for test_name in new_tests),
        start=Fraction(),
    )
    if bucket.union_fsum_seconds is not None:
        try:
            bucket.union_fsum_seconds = math.fsum(
                [
                    bucket.union_fsum_seconds,
                    *(float(durations[test_name]) for test_name in new_tests),
                ]
            )
        except OverflowError:
            bucket.union_fsum_seconds = None
    bucket.forced_fail_cap_seconds = max(
        bucket.forced_fail_cap_seconds, mutant.forced_fail_cap_seconds
    )


def _budget_bin_from_mutants(
    mutants: Iterable[_BudgetMutant],
    durations: Mapping[str, float | int],
) -> _BudgetBin:
    """Rebuild a budget bin from an ordered mutant assignment."""

    bucket = _BudgetBin(
        names=[],
        mutants=[],
        test_names=set(),
        union_exact_seconds=Fraction(),
        union_fsum_seconds=0.0,
        forced_fail_cap_seconds=0,
    )
    for mutant in mutants:
        _add_budget_mutant(bucket, mutant, durations)
    return bucket


def _rebalance_for_budget_candidate(
    buckets: Sequence[_BudgetBin],
    candidate: _BudgetMutant,
    *,
    durations: Mapping[str, float | int],
    max_children: int,
    control_cycle_reserve_seconds: int,
    metadata_and_startup_reserve_seconds: int,
    max_timeout_seconds: int,
    max_evictions: int = 2,
    max_search_nodes: int = 20_000,
) -> list[list[_BudgetMutant]] | None:
    """Find a bounded deterministic move that makes ``candidate`` fit.

    Greedy bin packing is intentionally retained as the fast path.  When a
    candidate has no direct destination, this bounded repair searches for a
    small set of mutants to evict from one bin and places those mutants into
    the remaining bins. Every prospective state is evaluated with the same
    conservative budget bound as the fast path; the caller performs the
    canonical exact validation before publishing a plan. The finite node
    limit keeps a pathological input from turning planning into an unbounded
    knapsack search.
    """

    if max_evictions < 1 or max_search_nodes < 1:
        return None

    assignments = [list(bucket.mutants) for bucket in buckets]
    search_nodes = 0

    def projected(
        mutants: Sequence[_BudgetMutant],
        item: _BudgetMutant,
    ) -> int:
        bucket = _budget_bin_from_mutants(mutants, durations)
        return _budget_bin_upper_bound(
            bucket,
            item,
            durations=durations,
            max_children=max_children,
            control_cycle_reserve_seconds=control_cycle_reserve_seconds,
            metadata_and_startup_reserve_seconds=metadata_and_startup_reserve_seconds,
        )

    def place_pending(
        state: list[list[_BudgetMutant]],
        pending: list[_BudgetMutant],
        remaining_evictions: int,
        *,
        allow_eviction: bool,
    ) -> list[list[_BudgetMutant]] | None:
        nonlocal search_nodes
        if not pending:
            return state
        if search_nodes >= max_search_nodes:
            return None

        item = pending[0]
        direct: list[tuple[int, int, int]] = []
        for index, mutants in enumerate(state):
            search_nodes += 1
            if search_nodes > max_search_nodes:
                return None
            budget = projected(mutants, item)
            if budget <= max_timeout_seconds:
                direct.append((budget, len(mutants), index))
        for _, _, index in sorted(direct):
            trial = [list(mutants) for mutants in state]
            trial[index].append(item)
            result = place_pending(
                trial,
                pending[1:],
                remaining_evictions,
                allow_eviction=False,
            )
            if result is not None:
                return result

        if not allow_eviction or remaining_evictions < 1:
            return None

        # Start with the largest mutants. This makes the common one-move
        # repair cheap and keeps the search reproducible.
        for target_index, mutants in enumerate(state):
            ordered_existing = sorted(
                mutants,
                key=lambda mutant: (-mutant.estimate_exact_seconds, mutant.name),
            )
            for count in range(1, min(remaining_evictions, len(ordered_existing)) + 1):
                for evicted in itertools.combinations(ordered_existing, count):
                    search_nodes += 1
                    if search_nodes > max_search_nodes:
                        return None
                    evicted_set = set(evicted)
                    remaining = [
                        mutant for mutant in mutants if mutant not in evicted_set
                    ]
                    if projected(remaining, item) > max_timeout_seconds:
                        continue
                    trial = [list(current) for current in state]
                    trial[target_index] = [*remaining, item]
                    # Reinsert evicted items without opening another eviction
                    # branch; this bounded frontier cannot cycle.
                    result = place_pending(
                        trial,
                        [*evicted, *pending[1:]],
                        remaining_evictions - count,
                        allow_eviction=False,
                    )
                    if result is not None:
                        return result
        return None

    return place_pending(
        assignments,
        [candidate],
        max_evictions,
        allow_eviction=True,
    )


def _repack_budget_frontier(
    buckets: Sequence[_BudgetBin],
    candidate: _BudgetMutant,
    *,
    durations: Mapping[str, float | int],
    max_children: int,
    control_cycle_reserve_seconds: int,
    metadata_and_startup_reserve_seconds: int,
    max_timeout_seconds: int,
    max_frontier_items: int = 48,
    max_search_nodes: int = 100_000,
) -> list[list[_BudgetMutant]] | None:
    """Repack a bounded recent frontier when local repair is insufficient.

    The complete bin-packing problem is deliberately not attempted for a
    production-sized mutation universe. Instead, a bounded round-robin
    frontier of the most recently assigned mutants is removed from otherwise
    valid bins and solved with deterministic depth-first search. This catches
    multi-bin greedy dead ends (including the small adversarial fixture) while
    retaining a strict node limit for pathological inputs.
    """

    if max_frontier_items < 2 or max_search_nodes < 1:
        return None

    frontier_limit = max_frontier_items - 1
    selected: list[_BudgetMutant] = []
    remaining = [list(bucket.mutants) for bucket in buckets]
    # Select the newest item from each bin in round-robin order. The stable
    # index tie-breaker keeps the frontier independent of set/hash ordering.
    cursors = [len(mutants) - 1 for mutants in remaining]
    while len(selected) < frontier_limit:
        progressed = False
        for index, cursor in enumerate(cursors):
            if cursor < 0 or len(selected) >= frontier_limit:
                continue
            selected.append(remaining[index][cursor])
            cursors[index] -= 1
            progressed = True
        if not progressed:
            break
    selected.append(candidate)
    selected_set = set(selected)
    for index, mutants in enumerate(remaining):
        remaining[index] = [mutant for mutant in mutants if mutant not in selected_set]

    items = sorted(
        selected,
        key=lambda mutant: (-mutant.estimate_exact_seconds, mutant.name),
    )
    nodes = 0

    def search(
        state: list[list[_BudgetMutant]],
        position: int,
    ) -> list[list[_BudgetMutant]] | None:
        nonlocal nodes
        if position == len(items):
            return state
        nodes += 1
        if nodes > max_search_nodes:
            return None
        item = items[position]
        candidates: list[tuple[int, int, int]] = []
        seen_signatures: set[tuple[str, ...]] = set()
        for index, mutants in enumerate(state):
            signature = tuple(sorted(mutant.name for mutant in mutants))
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            bucket = _budget_bin_from_mutants(mutants, durations)
            projected = _budget_bin_upper_bound(
                bucket,
                item,
                durations=durations,
                max_children=max_children,
                control_cycle_reserve_seconds=control_cycle_reserve_seconds,
                metadata_and_startup_reserve_seconds=(
                    metadata_and_startup_reserve_seconds
                ),
            )
            if projected <= max_timeout_seconds:
                candidates.append((projected, len(mutants), index))
        for _, _, index in sorted(candidates):
            trial = [list(mutants) for mutants in state]
            trial[index].append(item)
            result = search(trial, position + 1)
            if result is not None:
                return result
        return None

    return search(remaining, 0)


def plan_mutant_shards_with_budget(
    estimates: Sequence[MutantEstimate],
    tests_by_mangled_function_name: Mapping[str, Sequence[str]],
    duration_by_test: Mapping[str, float | int],
    *,
    num_shards: int,
    max_children: int,
    control_cycle_reserve_seconds: int,
    metadata_and_startup_reserve_seconds: int,
    max_timeout_seconds: int,
) -> list[list[str]]:
    """Balance exact mutants against the full stats-derived timeout model.

    The legacy planner balances only the scalar clean-test estimate.  That is
    insufficient when one long mutant dominates a three-worker watchdog
    schedule or when a shard's mapped test union is large.  This planner uses
    the same per-mutant watchdog costs and reserve semantics as
    :func:`scripts.mutmut_shard_budget.calculate_shard_budget`, rejects a
    candidate that cannot fit, and performs an exact final validation before
    returning the fixed-width logical plan. A bounded deterministic
    rebalancing pass repairs small greedy dead ends without turning the normal
    planning path into an unbounded bin-packing search.
    """

    if (
        isinstance(num_shards, bool)
        or not isinstance(num_shards, int)
        or num_shards < 1
    ):
        raise ValueError("num_shards must be positive")
    if (
        isinstance(max_children, bool)
        or not isinstance(max_children, int)
        or max_children < 1
    ):
        raise ValueError("max_children must be positive")
    if (
        isinstance(control_cycle_reserve_seconds, bool)
        or not isinstance(control_cycle_reserve_seconds, int)
        or control_cycle_reserve_seconds < 1
    ):
        raise ValueError("control_cycle_reserve_seconds must be positive")
    if (
        isinstance(metadata_and_startup_reserve_seconds, bool)
        or not isinstance(metadata_and_startup_reserve_seconds, int)
        or metadata_and_startup_reserve_seconds < 0
    ):
        raise ValueError("metadata_and_startup_reserve_seconds must be non-negative")
    if (
        isinstance(max_timeout_seconds, bool)
        or not isinstance(max_timeout_seconds, int)
        or max_timeout_seconds < 1
    ):
        raise ValueError("max_timeout_seconds must be positive")

    normalized = _budget_mutants(
        estimates,
        tests_by_mangled_function_name,
        duration_by_test,
    )
    buckets = [
        _BudgetBin(
            names=[],
            mutants=[],
            test_names=set(),
            union_exact_seconds=Fraction(),
            union_fsum_seconds=0.0,
            forced_fail_cap_seconds=0,
        )
        for _ in range(num_shards)
    ]
    ordered = sorted(
        normalized,
        key=lambda item: (-item.estimate_exact_seconds, item.name),
    )

    # Seeding one expensive mutant per bucket prevents the dominant watchdog
    # costs from being co-located before the candidate feasibility pass.
    seed_count = min(num_shards, len(ordered))
    for bucket, mutant in zip(buckets, ordered[:seed_count], strict=False):
        if (
            _budget_bin_upper_bound(
                bucket,
                mutant,
                durations=duration_by_test,
                max_children=max_children,
                control_cycle_reserve_seconds=control_cycle_reserve_seconds,
                metadata_and_startup_reserve_seconds=metadata_and_startup_reserve_seconds,
            )
            > max_timeout_seconds
        ):
            raise ValueError(
                "mutant cannot fit within configured timeout: "
                f"{mutant.name} requires more than {max_timeout_seconds}s"
            )

    # ``zip`` above only checked prospective values.  Apply the seed in a
    # second pass so the candidate evaluation stays side-effect free.
    for bucket, mutant in zip(buckets, ordered[:seed_count], strict=False):
        _add_budget_mutant(bucket, mutant, duration_by_test)

    for mutant in ordered[seed_count:]:
        candidates: list[tuple[int, int, int]] = []
        for index, bucket in enumerate(buckets):
            projected = _budget_bin_upper_bound(
                bucket,
                mutant,
                durations=duration_by_test,
                max_children=max_children,
                control_cycle_reserve_seconds=control_cycle_reserve_seconds,
                metadata_and_startup_reserve_seconds=metadata_and_startup_reserve_seconds,
            )
            if projected <= max_timeout_seconds:
                candidates.append((projected, len(bucket.mutants), index))
        if not candidates:
            repaired = _rebalance_for_budget_candidate(
                buckets,
                mutant,
                durations=duration_by_test,
                max_children=max_children,
                control_cycle_reserve_seconds=control_cycle_reserve_seconds,
                metadata_and_startup_reserve_seconds=(
                    metadata_and_startup_reserve_seconds
                ),
                max_timeout_seconds=max_timeout_seconds,
            )
            if repaired is None:
                repaired = _repack_budget_frontier(
                    buckets,
                    mutant,
                    durations=duration_by_test,
                    max_children=max_children,
                    control_cycle_reserve_seconds=control_cycle_reserve_seconds,
                    metadata_and_startup_reserve_seconds=(
                        metadata_and_startup_reserve_seconds
                    ),
                    max_timeout_seconds=max_timeout_seconds,
                )
            if repaired is None:
                raise ValueError(
                    "mutant cannot fit within configured timeout: "
                    f"{mutant.name} requires a new logical shard"
                )
            buckets = [
                _budget_bin_from_mutants(mutants, duration_by_test)
                for mutants in repaired
            ]
            continue
        _, _, selected_index = min(candidates)
        _add_budget_mutant(buckets[selected_index], mutant, duration_by_test)

    # The candidate loop uses an inexpensive conservative upper bound.  The
    # canonical helper remains authoritative and must agree for every nonempty
    # logical assignment before any files are written.
    from scripts.mutmut_shard_budget import calculate_shard_budget

    for shard_id, bucket in enumerate(buckets, start=1):
        if not bucket.mutants:
            continue
        budget = calculate_shard_budget(
            bucket.names,
            tests_by_mangled_function_name,
            duration_by_test,
            max_children=max_children,
            control_cycle_reserve_seconds=control_cycle_reserve_seconds,
            metadata_and_startup_reserve_seconds=metadata_and_startup_reserve_seconds,
        )
        if budget.outer_timeout_seconds > max_timeout_seconds:
            raise ValueError(
                "budget-aware planner produced an oversized shard: "
                f"shard {shard_id} requires {budget.outer_timeout_seconds}s, "
                f"maximum {max_timeout_seconds}s"
            )
    return [bucket.names for bucket in buckets]


def _selection_digest(names: Iterable[str]) -> str:
    """Return a stable digest for an unordered exact-mutant population."""

    canonical = "\n".join(sorted(names)).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def write_shard_plan_bundle(
    output_directory: Path,
    shards: Sequence[Sequence[str]],
    estimates: Iterable[MutantEstimate],
    *,
    allow_empty_shards: bool = False,
) -> dict[str, Any]:
    """Persist every exact shard plus a deterministic population manifest.

    Nightly full mutation plans require every shard to carry work.  Incremental
    plans may intentionally have fewer changed mutants than their fixed matrix;
    callers must opt in explicitly when preserving those empty assignments.
    """

    if not shards:
        raise ValueError("shard plan must contain at least one shard")
    if any(not shard for shard in shards) and not allow_empty_shards:
        raise ValueError("planned shards must not be empty")

    flattened = [name for shard in shards for name in shard]
    if len(flattened) != len(set(flattened)):
        raise ValueError("shard plan contains duplicate mutant names")

    estimate_list = list(estimates)
    estimate_by_name = {estimate.name: estimate for estimate in estimate_list}
    if len(estimate_by_name) != len(estimate_list):
        raise ValueError("mutant estimates contain duplicate names")
    if set(flattened) != set(estimate_by_name):
        raise ValueError("shard plan does not match the estimated mutant universe")

    output_directory.mkdir(parents=True, exist_ok=True)
    manifest_shards: list[dict[str, Any]] = []
    for shard_id, selected in enumerate(shards, start=1):
        filename = f"shard-{shard_id:02d}.txt"
        (output_directory / filename).write_text(
            "".join(f"{mutant_name}\n" for mutant_name in selected),
            encoding="utf-8",
            newline="\n",
        )
        manifest_shards.append(
            {
                "shard_id": shard_id,
                "path": filename,
                "selected_count": len(selected),
                "selection_sha256": _selection_digest(selected),
                "estimated_load_seconds": math.fsum(
                    estimate_by_name[name].estimated_seconds for name in selected
                ),
            }
        )

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "num_shards": len(shards),
        "universe_count": len(flattened),
        "universe_sha256": _selection_digest(flattened),
        "shards": manifest_shards,
    }
    (output_directory / "plan-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changed-files", type=Path, required=True)
    parser.add_argument("--shard-id", type=int)
    parser.add_argument("--num-shards", type=int, required=True)
    parser.add_argument("--max-children", type=int, default=2)
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
        help="reserve for metadata/startup work outside selected-test execution",
    )
    parser.add_argument(
        "--max-timeout-seconds",
        type=int,
        help=(
            "enable full budget-aware planning and reject assignments above "
            "this outer timeout"
        ),
    )
    parser.add_argument(
        "--reuse-generated-universe",
        action="store_true",
        help="validate and reuse the extracted generation artifact",
    )
    parser.add_argument(
        "--allow-empty-shards",
        action="store_true",
        help="preserve empty assignments for fixed-size incremental matrices",
    )
    parser.add_argument(
        "--changed-diff",
        type=Path,
        help="Optional git diff --unified=0 used to select changed source lines",
    )
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--output", type=Path)
    output.add_argument(
        "--output-directory",
        type=Path,
        help="write every exact shard and a population manifest in one pass",
    )
    args = parser.parse_args()
    if args.num_shards < 1:
        parser.error("--num-shards must be positive")
    if args.output is not None:
        if args.shard_id is None or not 1 <= args.shard_id <= args.num_shards:
            parser.error(
                "--shard-id must be within the configured 1-based range with --output"
            )
    elif args.shard_id is not None:
        parser.error("--shard-id cannot be combined with --output-directory")
    if args.max_children < 1:
        parser.error("--max-children must be positive")
    if args.control_cycle_reserve_seconds < 1:
        parser.error("--control-cycle-reserve-seconds must be positive")
    if args.metadata_startup_reserve_seconds < 0:
        parser.error("--metadata-startup-reserve-seconds must be non-negative")
    if args.max_timeout_seconds is not None and args.max_timeout_seconds < 1:
        parser.error("--max-timeout-seconds must be positive")
    return args


def _load_mutmut_cli() -> Any:
    """Load mutmut's orchestration module only on the Linux CI runner."""

    try:
        from mutmut import __main__ as mutmut_cli
    except SystemExit as exc:  # mutmut exits with a platform hint on Windows
        raise RuntimeError(
            "mutmut shard planning must run on the Linux CI runner"
        ) from exc
    return mutmut_cli


def _generate_mutant_universe(mutmut_cli: Any, *, max_children: int) -> None:
    """Create the same source copy and metadata that ``mutmut run`` uses."""

    mutmut_cli.Config.ensure_loaded()
    mutants_dir = Path("mutants")
    mutants_dir.mkdir(parents=True, exist_ok=True)
    # mutmut's mtime fast path intentionally retains newer generated files.
    # A shard planner must start from a pristine generated source tree so stale
    # files cannot be mistaken for the manifest it is about to publish.
    prepare_mutants_directory(mutmut_cli)
    mutmut_cli.copy_src_dir()
    mutmut_cli.copy_also_copy_files()
    mutmut_cli.setup_source_paths()

    # This is false in the repository configuration.  Keep the branch so a
    # future config change cannot make the planner and mutmut use different
    # mutant universes.
    if mutmut_cli.Config.get().mutate_only_covered_lines:
        mutmut_cli.store_lines_covered_by_tests()
    stats = mutmut_cli.create_mutants(max_children)
    metadata = list(mutants_dir.rglob("*.py.meta"))
    if not metadata:
        raise RuntimeError("mutmut generated no mutation metadata files")
    print(
        "Generated mutmut universe: "
        f"{stats.mutated} mutated, {stats.ignored} ignored, "
        f"{stats.unmodified} unmodified source files"
    )


def _read_changed_files(path: Path) -> set[str]:
    return {
        normalize_source_path(line.strip())
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def _mutant_line_ranges(mutmut_cli: Any, path: Path) -> dict[str, tuple[int, int]]:
    """Map generated mutmut names to the original source node they mutate."""

    import libcst as cst
    from libcst.metadata import MetadataWrapper, PositionProvider
    from mutmut.mutation.file_mutation import MutationVisitor
    from mutmut.mutation.mutators import mutation_operators
    from mutmut.mutation.pragma_handling import get_ignored_lines
    from mutmut.mutation.trampoline_templates import mangle_function_name

    source = path.read_text(encoding="utf-8")
    module = cst.parse_module(source)
    wrapper = MetadataWrapper(module)
    ignored_code = get_ignored_lines(str(path), source, wrapper)
    visitor = MutationVisitor(mutation_operators, ignored_code, None)
    wrapper.visit(visitor)
    positions = wrapper.resolve(PositionProvider)

    class_name_by_function_id: dict[int, str] = {}
    for node in wrapper.module.body:
        if isinstance(node, cst.ClassDef) and isinstance(node.body, cst.IndentedBlock):
            for child in node.body.body:
                if isinstance(child, cst.FunctionDef):
                    class_name_by_function_id[id(child)] = node.name.value

    mutation_numbers_by_function_id: defaultdict[int, int] = defaultdict(int)
    line_ranges: dict[str, tuple[int, int]] = {}
    for mutation in visitor.mutations:
        function = mutation.contained_by_top_level_function
        if not isinstance(function, cst.FunctionDef):
            # Only top-level functions and class methods receive trampolines.
            continue

        function_id = id(function)
        mutation_numbers_by_function_id[function_id] += 1
        mangled_name = mangle_function_name(
            name=function.name.value,
            class_name=class_name_by_function_id.get(function_id),
        )
        mutant_method_name = (
            f"{mangled_name}__mutmut_{mutation_numbers_by_function_id[function_id]}"
        )
        mutant_name = mutmut_cli.get_mutant_name(path, mutant_method_name)
        position = positions[mutation.original_node]
        line_ranges[mutant_name] = (position.start.line, position.end.line)

    return line_ranges


def _line_ranges_intersect(
    mutant_range: tuple[int, int], changed_ranges: Sequence[tuple[int, int]]
) -> bool:
    return any(
        mutant_range[0] <= changed_end and changed_start <= mutant_range[1]
        for changed_start, changed_end in changed_ranges
    )


def _collect_changed_mutants(
    mutmut_cli: Any,
    changed_files: set[str],
    changed_line_ranges: ChangedLineRanges | None = None,
) -> list[str]:
    names: list[str] = []
    for path in mutmut_cli.walk_source_files():
        normalized_path = normalize_source_path(path)
        if normalized_path not in changed_files:
            continue
        metadata = mutmut_cli.SourceFileMutationData(path=path)
        metadata.load()
        mutant_names = set(metadata.exit_code_by_key)
        if changed_line_ranges is not None:
            changed_ranges = changed_line_ranges.get(normalized_path, ())
            if not changed_ranges:
                continue
            line_ranges = _mutant_line_ranges(mutmut_cli, Path(path))
            mutant_names = {
                mutant_name
                for mutant_name in mutant_names
                if mutant_name in line_ranges
                and _line_ranges_intersect(line_ranges[mutant_name], changed_ranges)
            }
        names.extend(mutant_names)
    return sorted(set(names))


def _load_stats(path: Path) -> tuple[dict[str, list[str]], dict[str, float | int]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        return payload["tests_by_mangled_function_name"], payload["duration_by_test"]
    except KeyError as exc:
        raise ValueError(f"Merged mutmut stats missing required field: {exc}") from exc


def main() -> None:
    args = _parse_args()
    changed_files = _read_changed_files(args.changed_files)
    if not changed_files:
        raise ValueError("Changed-file manifest is empty")

    mutmut_cli = _load_mutmut_cli()
    if args.reuse_generated_universe:
        prepare_reused_generation(mutmut_cli)
    else:
        _generate_mutant_universe(mutmut_cli, max_children=args.max_children)
    # Persist a content-addressed source/metadata/config snapshot so the exact
    # mutation runner can safely reuse this expensive generation phase.
    write_universe_manifest(mutmut_cli)
    changed_line_ranges = None
    if args.changed_diff is not None:
        changed_line_ranges = parse_unified_diff_line_ranges(
            args.changed_diff.read_text(encoding="utf-8")
        )
    mutant_names = _collect_changed_mutants(
        mutmut_cli,
        changed_files,
        changed_line_ranges,
    )
    if not mutant_names:
        raise RuntimeError(
            "Changed Python source produced no mutmut mutants; refusing to skip mutation evidence"
        )

    tests_by_function, durations = _load_stats(Path("mutants/mutmut-stats.json"))
    estimates = estimate_mutant_times(mutant_names, tests_by_function, durations)
    if args.max_timeout_seconds is None:
        shards = plan_mutant_shards(estimates, num_shards=args.num_shards)
    else:
        shards = plan_mutant_shards_with_budget(
            estimates,
            tests_by_function,
            durations,
            num_shards=args.num_shards,
            max_children=args.max_children,
            control_cycle_reserve_seconds=args.control_cycle_reserve_seconds,
            metadata_and_startup_reserve_seconds=args.metadata_startup_reserve_seconds,
            max_timeout_seconds=args.max_timeout_seconds,
        )
    if args.output_directory is not None:
        manifest = write_shard_plan_bundle(
            args.output_directory,
            shards,
            estimates,
            allow_empty_shards=args.allow_empty_shards,
        )
        print(
            f"Planned all {manifest['num_shards']} mutmut shards: "
            f"{manifest['universe_count']} exact mutants"
        )
        return

    if args.shard_id is None or args.output is None:
        raise RuntimeError("validated single-shard output target is missing")
    selected = shards[args.shard_id - 1]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(f"{mutant_name}\n" for mutant_name in selected), encoding="utf-8"
    )

    selected_names = set(selected)
    selected_load = sum(
        item.estimated_seconds for item in estimates if item.name in selected_names
    )
    print(
        f"Planned mutmut shard {args.shard_id}/{args.num_shards}: "
        f"{len(selected)} of {len(mutant_names)} mutants; "
        f"estimated load {selected_load:.2f}s"
    )


if __name__ == "__main__":
    main()
