"""Generate the mutmut universe and collect one complete test-stats shard.

mutmut 3.5.0 applies positional mutant filters only after it has collected
stats for the entire pytest population.  Running those filters in a matrix
therefore repeats the expensive full stats pass.  This helper keeps the
mutmut-generated universe unchanged, but lets CI collect disjoint pytest
shards whose JSON outputs can be merged before mutation execution.

The mutmut imports are intentionally lazy: mutmut has no native Windows
runner, while the repository's local contract tests must remain runnable on
Windows.  The helper itself is executed on the Linux CI runner only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard-id", type=int, required=True)
    parser.add_argument("--num-shards", type=int, required=True)
    parser.add_argument("--max-children", type=int, default=2)
    args = parser.parse_args()
    if args.num_shards < 1:
        parser.error("--num-shards must be positive")
    if not 0 <= args.shard_id < args.num_shards:
        parser.error("--shard-id must be within the configured shard range")
    if args.max_children < 1:
        parser.error("--max-children must be positive")
    return args


def _load_mutmut_cli():
    """Load mutmut's 3.5.x orchestration module only on the CI platform."""

    try:
        from mutmut import __main__ as mutmut_cli
    except SystemExit as exc:  # mutmut exits with a platform hint on Windows
        raise RuntimeError(
            "mutmut stats sharding must run on the Linux CI runner"
        ) from exc
    return mutmut_cli


def _generate_mutant_universe(mutmut_cli, *, max_children: int) -> None:
    """Create the normal mutmut copy and metadata before collecting stats."""

    mutmut_cli.ensure_config_loaded()
    mutants_dir = Path("mutants")
    mutants_dir.mkdir(parents=True, exist_ok=True)

    mutmut_cli.copy_src_dir()
    mutmut_cli.copy_also_copy_files()
    mutmut_cli.setup_source_paths()
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


def collect_stats_shard(*, shard_id: int, num_shards: int, max_children: int) -> Path:
    """Generate the mutmut universe and persist one pytest stats shard."""

    mutmut_cli = _load_mutmut_cli()
    _generate_mutant_universe(mutmut_cli, max_children=max_children)

    # The repository conftest assigns whole test files to deterministic shards.
    # Appending these options to mutmut's normal test-selection population keeps
    # all existing exclusions intact while partitioning only the stats pass.
    import mutmut

    mutmut_cli.ensure_config_loaded()
    config = mutmut.config
    config.pytest_add_cli_args_test_selection = [
        *config.pytest_add_cli_args_test_selection,
        f"--shard-id={shard_id}",
        f"--num-shards={num_shards}",
    ]
    mutmut_cli.setup_source_paths()
    runner = mutmut_cli.PytestRunner()
    runner.prepare_main_test_run()
    mutmut_cli.run_stats_collection(runner)

    stats_path = Path("mutants/mutmut-stats.json")
    if not stats_path.is_file():
        raise RuntimeError("mutmut did not produce mutants/mutmut-stats.json")
    payload = json.loads(stats_path.read_text(encoding="utf-8"))
    if not payload.get("duration_by_test"):
        raise RuntimeError("mutmut stats shard contains no active tests")
    print(
        f"Collected stats shard {shard_id + 1}/{num_shards}: "
        f"{len(payload['duration_by_test'])} tests"
    )
    return stats_path


def main() -> None:
    args = _parse_args()
    collect_stats_shard(
        shard_id=args.shard_id,
        num_shards=args.num_shards,
        max_children=args.max_children,
    )


if __name__ == "__main__":
    main()
