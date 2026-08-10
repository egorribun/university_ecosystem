#!/usr/bin/env python3
"""Run mutmut 3.7 with a precomputed stats map in a fresh pytest process.

Mutmut reloads an existing ``mutants/mutmut-stats.json`` and then normally
uses ``pytest.main(--collect-only)`` to discover new tests before its clean
baseline.  Pytest does not support repeated in-process invocations for this
suite: imported test modules and dependencies remain cached.  CI has already
created a complete, same-revision stats map in a separate process, so reuse
its test IDs for that discovery check and leave the clean baseline as this
process's first pytest invocation.  All mutation generation, clean/forced-fail
checks, watchdogs, exact selection, and result persistence remain mutmut's
own pinned-3.7 implementation.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_STATS_PATH = Path("mutants/mutmut-stats.json")
_REQUIRED_STATS_KEYS = frozenset(
    {"tests_by_mangled_function_name", "duration_by_test", "stats_time"}
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-children", type=int, default=2)
    parser.add_argument("mutant_names", nargs="*")
    args = parser.parse_args()
    if args.max_children < 1:
        parser.error("--max-children must be positive")
    return args


def _require_precomputed_stats(path: Path = _STATS_PATH) -> None:
    """Fail closed unless the preceding stats job produced usable metadata."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(
            "mutmut requires a precomputed mutants/mutmut-stats.json artifact"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"mutmut stats artifact is not valid JSON: {path}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"mutmut stats artifact must be a JSON object: {path}")
    missing = _REQUIRED_STATS_KEYS - payload.keys()
    if missing:
        raise RuntimeError(
            f"mutmut stats artifact is missing required keys: {sorted(missing)}"
        )
    if not isinstance(payload["tests_by_mangled_function_name"], dict):
        raise RuntimeError(
            "mutmut stats artifact has an invalid mutant-to-test mapping"
        )
    if not isinstance(payload["duration_by_test"], dict):
        raise RuntimeError("mutmut stats artifact has an invalid test-duration mapping")
    if not payload["tests_by_mangled_function_name"]:
        raise RuntimeError("mutmut stats artifact has no mutant-to-test mappings")
    if not payload["duration_by_test"]:
        raise RuntimeError("mutmut stats artifact has no active tests")


def _load_mutmut_cli() -> Any:
    """Load mutmut lazily so local Windows contract tests stay runnable."""

    try:
        from mutmut import __main__ as mutmut_cli
    except SystemExit as exc:  # mutmut exits with a platform hint on Windows
        raise RuntimeError("run the mutmut gate in Linux CI") from exc
    return mutmut_cli


def run_mutmut_from_stats(
    *,
    mutant_names: Sequence[str],
    max_children: int,
    mutmut_cli: Any | None = None,
) -> None:
    """Run mutmut while bypassing only its redundant same-process collection."""

    if max_children < 1:
        raise ValueError("max_children must be positive")
    _require_precomputed_stats()
    cli = mutmut_cli or _load_mutmut_cli()

    original_list_all_tests = cli.PytestRunner.list_all_tests

    def _reuse_precomputed_test_ids(_runner: Any) -> Any:
        return cli.ListAllTestsResult(ids=set(cli.collected_test_names()))

    cli.PytestRunner.list_all_tests = _reuse_precomputed_test_ids
    try:
        # `_run` is pinned with mutmut==3.7.0.  It still owns all mutation
        # phases; the temporary hook only replaces redundant test discovery.
        cli._run(tuple(mutant_names), max_children=max_children)
    finally:
        cli.PytestRunner.list_all_tests = original_list_all_tests


def main() -> None:
    args = _parse_args()
    run_mutmut_from_stats(
        mutant_names=args.mutant_names,
        max_children=args.max_children,
    )


if __name__ == "__main__":
    main()
