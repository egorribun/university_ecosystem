"""Plan exact mutmut mutants into duration-balanced CI shards.

The helper imports mutmut lazily because mutmut is POSIX-only while the
repository's contract tests also run on Windows.  CI generates the normal
mutmut universe once per mutation job, reads the complete merged test-time
map, and writes only the exact mutant names assigned to that job.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if not __package__:  # pragma: no cover - direct CI script entry point
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.mutmut_universe import (
    prepare_mutants_directory,
    write_universe_manifest,
)


@dataclass(frozen=True, slots=True)
class MutantEstimate:
    """One mutant and the estimated cost of its associated tests."""

    name: str
    estimated_seconds: float


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


def _selection_digest(names: Iterable[str]) -> str:
    """Return a stable digest for an unordered exact-mutant population."""

    canonical = "\n".join(sorted(names)).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def write_shard_plan_bundle(
    output_directory: Path,
    shards: Sequence[Sequence[str]],
    estimates: Iterable[MutantEstimate],
) -> dict[str, Any]:
    """Persist every exact shard plus a deterministic population manifest."""

    if not shards:
        raise ValueError("shard plan must contain at least one shard")
    if any(not shard for shard in shards):
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
    shards = plan_mutant_shards(estimates, num_shards=args.num_shards)
    if args.output_directory is not None:
        manifest = write_shard_plan_bundle(args.output_directory, shards, estimates)
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
