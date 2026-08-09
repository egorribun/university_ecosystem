#!/usr/bin/env python3
"""Export fail-closed mutation statistics for an exact shard or full mutmut run.

``mutmut export-cicd-stats`` aggregates every generated ``.meta`` file.  That
is unsuitable for the incremental CI job because a positional run deliberately
leaves unselected mutants as ``not checked``. This helper exports only the
exact mutant names assigned to an incremental shard. Its explicit ``--all``
mode is for a freshly-created full-run ``mutants`` directory and also retains
``caught_by_type_check``, which mutmut 3.5 does not serialize itself.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

_STATUS_FIELD_BY_MUTMUT_STATUS = {
    "killed": "killed",
    "survived": "survived",
    "no tests": "no_tests",
    "skipped": "skipped",
    "suspicious": "suspicious",
    "timeout": "timeout",
    "check was interrupted by user": "check_was_interrupted_by_user",
    "segfault": "segfault",
    "caught by type check": "caught_by_type_check",
}
_STATS_FIELDS = (
    "killed",
    "survived",
    "total",
    "no_tests",
    "skipped",
    "suspicious",
    "timeout",
    "check_was_interrupted_by_user",
    "segfault",
    "caught_by_type_check",
)
_GLOB_TOKENS = frozenset("*?[")


def load_selected_mutants(path: Path) -> list[str]:
    """Load a non-empty, duplicate-free list of exact mutant names."""
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


def _collect_selected_results(
    selected_mutants: Sequence[str], mutmut_cli: Any
) -> tuple[list[tuple[str, int | None]], Mapping[int | None, str]]:
    """Read exact records, or the complete universe when ``selected_mutants`` is empty."""
    mutmut_cli.ensure_config_loaded()
    selected, _ = mutmut_cli.collect_source_file_mutation_data(
        mutant_names=list(selected_mutants)
    )

    selected_results: list[tuple[str, int | None]] = []
    for source_file_data, mutant_name, _ in selected:
        try:
            exit_code = source_file_data.exit_code_by_key[mutant_name]
        except KeyError as exc:
            raise ValueError(
                f"mutmut selected mutant {mutant_name!r} has no recorded exit code"
            ) from exc
        selected_results.append((mutant_name, exit_code))
    return selected_results, mutmut_cli.status_by_exit_code


def build_shard_stats(
    selected_mutants: Sequence[str],
    selected_results: Iterable[tuple[str, int | None]],
    status_by_exit_code: Mapping[int | None, str],
) -> dict[str, int]:
    """Build the mutmut CI/CD JSON schema from exact selected results."""
    names = list(selected_mutants)
    if not names:
        raise ValueError("selected mutant names must not be empty")
    if len(names) != len(set(names)):
        raise ValueError("selected mutant names contain duplicate mutant names")
    if any(any(token in name for token in _GLOB_TOKENS) for name in names):
        raise ValueError(
            "selected mutant names must be exact; glob patterns are forbidden"
        )

    expected = set(names)
    observed: dict[str, int | None] = {}
    for mutant_name, exit_code in selected_results:
        if mutant_name not in expected:
            raise ValueError(
                f"mutmut returned result outside the selected shard: {mutant_name!r}"
            )
        if mutant_name in observed:
            raise ValueError(f"mutant {mutant_name!r} appears more than once")
        observed[mutant_name] = exit_code

    missing = expected - observed.keys()
    if missing:
        raise ValueError(f"mutmut is missing selected mutants: {sorted(missing)}")

    stats = {field: 0 for field in _STATS_FIELDS}
    stats["total"] = len(names)
    for mutant_name in names:
        try:
            status = status_by_exit_code[observed[mutant_name]]
        except KeyError as exc:
            raise ValueError(
                f"mutmut returned an unmapped exit code for {mutant_name!r}"
            ) from exc
        if status == "not checked":
            # The standard schema represents this as total minus known status counts.
            continue
        field = _STATUS_FIELD_BY_MUTMUT_STATUS.get(status)
        if field is None:
            raise ValueError(
                f"mutmut returned unsupported status {status!r} for {mutant_name!r}"
            )
        stats[field] += 1
    return stats


def build_full_stats(
    full_results: Iterable[tuple[str, int | None]],
    status_by_exit_code: Mapping[int | None, str],
) -> dict[str, int]:
    """Build fail-closed stats for every mutant recorded by a clean full run."""
    results = list(full_results)
    return build_shard_stats(
        [mutant_name for mutant_name, _ in results],
        results,
        status_by_exit_code,
    )


def _load_mutmut_cli() -> Any:
    """Load mutmut lazily so unsupported local platforms fail with a clear error."""
    try:
        from mutmut import __main__ as mutmut_cli
    except ImportError as exc:
        raise ValueError("mutmut is not installed in the active environment") from exc
    except SystemExit as exc:
        raise ValueError(
            "mutmut could not initialize on this platform; run the mutation gate in Linux CI"
        ) from exc
    return mutmut_cli


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--selected-file",
        type=Path,
        help="newline-delimited exact mutant names assigned to this shard",
    )
    selection.add_argument(
        "--all",
        action="store_true",
        help="export the complete universe from a freshly-created full mutmut run",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("mutants/mutmut-cicd-stats.json"),
        help="destination for fail-closed CI/CD stats",
    )
    return parser.parse_args()


def main() -> None:
    """Export trustworthy mutation evidence or fail before its score can be used."""
    args = _parse_args()
    try:
        selected_mutants = (
            load_selected_mutants(args.selected_file)
            if args.selected_file is not None
            else []
        )
        mutmut_cli = _load_mutmut_cli()
        selected_results, status_by_exit_code = _collect_selected_results(
            selected_mutants, mutmut_cli
        )
        stats = (
            build_full_stats(selected_results, status_by_exit_code)
            if args.all
            else build_shard_stats(
                selected_mutants, selected_results, status_by_exit_code
            )
        )
    except (ImportError, OSError, UnicodeError, ValueError, AssertionError) as exc:
        raise SystemExit(
            f"ERROR: unable to export trustworthy mutmut stats: {exc}"
        ) from exc

    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise SystemExit(
            f"ERROR: unable to write trustworthy mutmut stats: {exc}"
        ) from exc
    scope = "complete mutmut universe" if args.all else "exact mutmut shard"
    print(f"Exported {scope} evidence for {stats['total']} mutants to {args.output}")


if __name__ == "__main__":
    main()
