#!/usr/bin/env python3
"""Run mutmut 3.7 with a precomputed stats map in a fresh pytest process.

Mutmut reloads an existing ``mutants/mutmut-stats.json`` and then normally
uses ``pytest.main(--collect-only)`` to discover new tests before its clean
baseline.  Pytest does not support repeated in-process invocations for this
suite: imported test modules and dependencies remain cached.  CI has already
created a complete, same-revision stats map in a separate process, so reuse
its test IDs for that discovery check and leave the clean baseline as this
process's first pytest invocation. For an exact shard, the forced-fail check
is scoped to the same mapped test union mutmut uses for its clean baseline and
mutation children. ``--reuse-generated-universe`` additionally validates the
planner's content-addressed source/metadata snapshot and skips only mutmut's
duplicate source-generation phase. Watchdogs, exact selection, and result
persistence remain mutmut's own pinned-3.7 implementation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import weakref
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

if not __package__:  # pragma: no cover - direct CI script entry point
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.mutmut_universe import (
    load_reused_generation_stats,
    validate_universe_manifest,
)

_STATS_PATH = Path("mutants/mutmut-stats.json")
_REQUIRED_STATS_KEYS = frozenset(
    {"tests_by_mangled_function_name", "duration_by_test", "stats_time"}
)

# OpenTelemetry 1.41 registers an ``after_in_child`` callback containing a
# WeakMethod for every finite PeriodicExportingMetricReader.  Its callback is
# left registered after shutdown and raises ``TypeError`` when a mutmut fork
# runs after the reader has been collected.  The guard below is installed only
# by this mutation runner (never by application startup) and changes no test or
# mutant selection: callbacks with a live target behave exactly as before,
# while a callback whose weak target is gone is safely a no-op.
_ATFORK_ORIGINAL: Any | None = None
_ATFORK_GUARD_INSTALLED = False


def _callback_weak_references(callback: Any) -> tuple[weakref.ReferenceType[Any], ...]:
    """Return weak references captured by a callback closure."""

    closure = getattr(callback, "__closure__", None)
    if not closure:
        return ()
    references: list[weakref.ReferenceType[Any]] = []
    for cell in closure:
        try:
            value = cell.cell_contents
        except ValueError:
            continue
        if isinstance(value, weakref.ReferenceType):
            references.append(value)
    return tuple(references)


def _guard_atfork_callback(callback: Any) -> Any:
    """Avoid invoking an upstream callback after its weak target was collected."""

    references = _callback_weak_references(callback)
    if not references:
        return callback

    def guarded_callback() -> Any:
        if any(reference() is None for reference in references):
            return None
        return callback()

    return guarded_callback


def install_mutation_atfork_guard() -> None:
    """Install the mutation-only OpenTelemetry weak-callback compatibility guard."""

    global _ATFORK_GUARD_INSTALLED, _ATFORK_ORIGINAL
    if _ATFORK_GUARD_INSTALLED:
        return
    original = getattr(os, "register_at_fork", None)
    if original is None:
        return

    def register_at_fork_guarded(
        *, before: Any = None, after_in_parent: Any = None, after_in_child: Any = None
    ) -> Any:
        callbacks: dict[str, Any] = {}
        if before is not None:
            callbacks["before"] = before
        if after_in_parent is not None:
            callbacks["after_in_parent"] = after_in_parent
        if after_in_child is not None:
            callbacks["after_in_child"] = _guard_atfork_callback(after_in_child)
        return original(**callbacks)

    _ATFORK_ORIGINAL = original
    os.register_at_fork = register_at_fork_guarded  # type: ignore[attr-defined]
    _ATFORK_GUARD_INSTALLED = True


def restore_mutation_atfork_guard() -> None:
    """Restore the process-global fork registration function for unit tests."""

    global _ATFORK_GUARD_INSTALLED, _ATFORK_ORIGINAL
    if _ATFORK_ORIGINAL is not None:
        os.register_at_fork = _ATFORK_ORIGINAL  # type: ignore[attr-defined]
    _ATFORK_ORIGINAL = None
    _ATFORK_GUARD_INSTALLED = False


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-children", type=int, default=2)
    parser.add_argument(
        "--reuse-generated-universe",
        action="store_true",
        help="reuse and validate the planner-created mutmut source universe",
    )
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
    reuse_generated_universe: bool = False,
) -> None:
    """Run an exact mutmut shard with reused stats and matching forced-fail scope."""

    if max_children < 1:
        raise ValueError("max_children must be positive")
    _require_precomputed_stats()
    cli = mutmut_cli or _load_mutmut_cli()

    @contextmanager
    def _reuse_universe() -> Any:
        """Skip only mutmut's duplicate generation after fail-closed validation."""

        if not reuse_generated_universe:
            yield
            return

        validate_universe_manifest(cli)
        originals = {
            name: getattr(cli, name)
            for name in ("copy_src_dir", "copy_also_copy_files", "create_mutants")
        }

        def _reuse_create_mutants(_max_children: int) -> Any:
            return load_reused_generation_stats(cli)

        def _skip_generation_copy() -> None:
            return None

        # ``mutmut._run`` resolves these names on its module, so replacing them
        # for this bounded call avoids a second full source/metadata generation.
        cli.copy_src_dir = _skip_generation_copy
        cli.copy_also_copy_files = _skip_generation_copy
        cli.create_mutants = _reuse_create_mutants
        try:
            yield
        finally:
            for name, original in originals.items():
                setattr(cli, name, original)

    selected_mutants = tuple(mutant_names)
    original_list_all_tests = cli.PytestRunner.list_all_tests
    original_run_forced_fail = cli.PytestRunner.run_forced_fail

    def _reuse_precomputed_test_ids(_runner: Any) -> Any:
        return cli.ListAllTestsResult(ids=set(cli.collected_test_names()))

    def _run_selected_forced_fail(runner: Any) -> Any:
        return runner.run_tests(
            mutant_name=None,
            tests=cli.tests_for_mutant_names(selected_mutants),
        )

    cli.PytestRunner.list_all_tests = _reuse_precomputed_test_ids
    cli.PytestRunner.run_forced_fail = _run_selected_forced_fail
    try:
        # `_run` is pinned with mutmut==3.7.0.  It still owns all mutation
        # phases. The temporary hooks reuse redundant collection and align
        # forced-fail with mutmut's exact clean/mutation test selection.
        with _reuse_universe():
            cli._run(selected_mutants, max_children=max_children)
    finally:
        cli.PytestRunner.list_all_tests = original_list_all_tests
        cli.PytestRunner.run_forced_fail = original_run_forced_fail


def main() -> None:
    args = _parse_args()
    # Install before mutmut imports/collects the application so forked test
    # workers inherit the narrow OTel lifecycle guard.
    install_mutation_atfork_guard()
    run_mutmut_from_stats(
        mutant_names=args.mutant_names,
        max_children=args.max_children,
        reuse_generated_universe=args.reuse_generated_universe,
    )


if __name__ == "__main__":
    main()
