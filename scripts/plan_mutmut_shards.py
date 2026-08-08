"""Plan exact mutmut mutants into duration-balanced CI shards.

The helper imports mutmut lazily because mutmut is POSIX-only while the
repository's contract tests also run on Windows.  CI generates the normal
mutmut universe once per mutation job, reads the complete merged test-time
map, and writes only the exact mutant names assigned to that job.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MutantEstimate:
    """One mutant and the estimated cost of its associated tests."""

    name: str
    estimated_seconds: float


def normalize_source_path(path: str | Path) -> str:
    """Return a repository-relative path in the CI manifest format."""

    normalized = str(path).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def estimate_mutant_times(
    mutant_names: Iterable[str],
    tests_by_mangled_function_name: Mapping[str, Sequence[str]],
    duration_by_test: Mapping[str, float | int],
) -> list[MutantEstimate]:
    """Attach mutmut's worst-case test estimate to every unique mutant."""

    durations = {name: float(duration) for name, duration in duration_by_test.items()}
    estimates: list[MutantEstimate] = []
    for mutant_name in sorted(set(mutant_names)):
        mangled_name, separator, _ = mutant_name.partition("__mutmut_")
        if not separator:
            raise ValueError(f"Invalid mutmut name without __mutmut_: {mutant_name}")
        estimated_seconds = sum(
            durations.get(test_name, 0.0)
            for test_name in tests_by_mangled_function_name.get(mangled_name, ())
        )
        estimates.append(
            MutantEstimate(
                name=mutant_name,
                estimated_seconds=max(estimated_seconds, 0.0),
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changed-files", type=Path, required=True)
    parser.add_argument("--shard-id", type=int, required=True)
    parser.add_argument("--num-shards", type=int, required=True)
    parser.add_argument("--max-children", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.num_shards < 1:
        parser.error("--num-shards must be positive")
    if not 1 <= args.shard_id <= args.num_shards:
        parser.error("--shard-id must be within the configured 1-based range")
    if args.max_children < 1:
        parser.error("--max-children must be positive")
    return args


def _load_mutmut_cli():
    """Load mutmut's orchestration module only on the Linux CI runner."""

    try:
        from mutmut import __main__ as mutmut_cli
    except SystemExit as exc:  # mutmut exits with a platform hint on Windows
        raise RuntimeError(
            "mutmut shard planning must run on the Linux CI runner"
        ) from exc
    return mutmut_cli


def _generate_mutant_universe(mutmut_cli, *, max_children: int) -> None:
    """Create the same source copy and metadata that ``mutmut run`` uses."""

    mutmut_cli.ensure_config_loaded()
    mutants_dir = Path("mutants")
    mutants_dir.mkdir(parents=True, exist_ok=True)
    mutmut_cli.copy_src_dir()
    mutmut_cli.copy_also_copy_files()
    mutmut_cli.setup_source_paths()

    # This is false in the repository configuration.  Keep the branch so a
    # future config change cannot make the planner and mutmut use different
    # mutant universes.
    import mutmut

    if mutmut.config.mutate_only_covered_lines:
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


def _collect_changed_mutants(mutmut_cli, changed_files: set[str]) -> list[str]:
    names: list[str] = []
    for path in mutmut_cli.walk_source_files():
        if normalize_source_path(path) not in changed_files:
            continue
        metadata = mutmut_cli.SourceFileMutationData(path=path)
        metadata.load()
        names.extend(metadata.exit_code_by_key)
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
    _generate_mutant_universe(mutmut_cli, max_children=args.max_children)
    mutant_names = _collect_changed_mutants(mutmut_cli, changed_files)
    if not mutant_names:
        raise RuntimeError(
            "Changed Python source produced no mutmut mutants; refusing to skip mutation evidence"
        )

    tests_by_function, durations = _load_stats(Path("mutants/mutmut-stats.json"))
    estimates = estimate_mutant_times(mutant_names, tests_by_function, durations)
    shards = plan_mutant_shards(estimates, num_shards=args.num_shards)
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
