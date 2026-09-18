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
import shutil
import sys
import tempfile
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

# ``mutmut`` forks each mutant after pytest has imported the application.  The
# test bootstrap therefore has already selected one automatic SQLite file and
# constructed a SQLAlchemy engine in the parent.  Forked children must never
# reuse either object: SQLite's WAL/journal state and inherited async engine
# pools are process-local resources.  These names intentionally mirror the
# bootstrap's private contract; they are only consumed when the harness owns
# the database (an explicit caller database is never rewritten here).
_AUTO_DATABASE_URL_ENV = "UNIVERSITY_ECOSYSTEM_PYTEST_AUTO_DATABASE_URL"
_AUTO_DATABASE_DIR_ENV = "UNIVERSITY_ECOSYSTEM_PYTEST_AUTO_DATABASE_DIR"
_DATABASE_MODE_ENV = "UNIVERSITY_ECOSYSTEM_PYTEST_DATABASE_MODE"
_MUTATION_CACHE_PREFIX = "mutmut-cache-"
_MUTATION_CACHE_DIR_BY_PID: dict[int, Path] = {}


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


def _configure_process_local_pytest_cache(runner: Any) -> Path | None:
    """Give this mutmut process a private pytest cache directory.

    Pytest's default ``.pytest_cache`` lives below ``mutants/`` and is shared
    by all forked mutant workers.  Most cache writes are harmless, but a
    process-local path removes the race and makes a cache failure fail only the
    owning worker.  The path is placed below the harness database directory so
    the existing sentinel-protected cleanup owns both resources.
    """

    pytest_args = getattr(runner, "_pytest_add_cli_args", None)
    if not isinstance(pytest_args, list):
        # Lightweight fakes used by contract tests do not model mutmut's
        # PytestRunner.  Do not alter their behavior or global test options.
        return None

    process_id = os.getpid()
    cache_dir = _MUTATION_CACHE_DIR_BY_PID.get(process_id)
    if cache_dir is None:
        database_dir_value = os.environ.get(_AUTO_DATABASE_DIR_ENV)
        if database_dir_value:
            cache_dir = (
                Path(database_dir_value).resolve()
                / f"{_MUTATION_CACHE_PREFIX}{process_id}"
            )
            cache_dir.mkdir(parents=True, exist_ok=True)
        else:
            cache_dir = Path(
                tempfile.mkdtemp(prefix=f"{_MUTATION_CACHE_PREFIX}{process_id}-")
            ).resolve()
        _MUTATION_CACHE_DIR_BY_PID[process_id] = cache_dir

    filtered_args: list[str] = []
    skip_next = False
    for index, arg in enumerate(pytest_args):
        if skip_next:
            skip_next = False
            continue
        if arg in {"--cache-dir", "-o", "--override-ini"}:
            # Remove the legacy unsupported flag and any stale cache_dir
            # override.  ``-o``/``--override-ini`` may also configure other
            # pytest options, which must remain untouched.
            if arg == "--cache-dir":
                skip_next = True
                continue
            next_index = index + 1
            if next_index < len(pytest_args) and pytest_args[next_index].startswith(
                "cache_dir="
            ):
                skip_next = True
                continue
            filtered_args.append(arg)
            continue
        if arg.startswith("--cache-dir="):
            continue
        if arg.startswith("--override-ini=") and arg.removeprefix(
            "--override-ini="
        ).startswith("cache_dir="):
            continue
        filtered_args.append(arg)
    # ``cache_dir`` is a pytest ini option, not a native CLI flag.  Passing
    # ``--cache-dir`` makes pytest return exit code 4 (usage error), which
    # mutmut reports as ``BadTestExecutionCommandsException`` before any
    # mutation can start.  Use pytest's documented ``-o name=value`` override
    # so every isolated process gets a private cache without invalid CLI args.
    filtered_args.extend(["-o", f"cache_dir={cache_dir}"])
    runner._pytest_add_cli_args = filtered_args
    return cache_dir


def _dispose_inherited_database() -> None:
    """Dispose inherited SQLAlchemy pools before a mutmut child rebinds SQLite."""

    from app.core import database

    for name in ("_engine", "_read_replica_engine"):
        inherited_engine = getattr(database, name, None)
        if inherited_engine is None:
            continue
        sync_engine = getattr(inherited_engine, "sync_engine", None)
        if sync_engine is not None:
            # ``close=False`` avoids closing descriptors which belong to the
            # parent after fork; replacing the child pool is the important
            # isolation boundary.  The child exits with os._exit, so this is
            # deliberately explicit rather than relying on atexit.
            sync_engine.dispose(close=False)

    database._engine = None
    database._async_session = None
    database._read_replica_engine = None
    database._read_session_factory = None


def _isolate_mutation_child_database() -> Path | None:
    """Allocate a fresh harness SQLite file for a forked mutmut worker.

    Returns the owned directory so the caller can remove it before mutmut's
    child uses ``os._exit`` (which does not run atexit handlers).  Explicit
    databases and PostgreSQL mutation runs are intentionally untouched.
    """

    if os.environ.get(_DATABASE_MODE_ENV) != "harness-sqlite":
        return None
    if not os.environ.get(_AUTO_DATABASE_URL_ENV):
        return None

    import tests.conftest as test_bootstrap

    _dispose_inherited_database()
    worker_id = os.environ.get("PYTEST_XDIST_WORKER")
    database_url = test_bootstrap._create_automatic_sqlite_database_url(worker_id)

    from app.core.config import settings

    settings.database_url = database_url
    # An automatic harness database never has a read replica.  Clearing this
    # prevents an inherited replica engine from reintroducing a shared path.
    settings.database_read_replica_url = None
    return Path(os.environ[_AUTO_DATABASE_DIR_ENV]).resolve()


def _cleanup_mutation_child_database(database_dir: Path | None) -> None:
    """Remove one child-owned database/cache directory after pytest teardown."""

    if database_dir is None:
        return
    import tests.conftest as test_bootstrap

    if database_dir.parent != test_bootstrap._AUTO_DATABASE_ROOT:
        return
    if not database_dir.name.startswith(f"pytest-{os.getpid()}-"):
        return
    sentinel = database_dir / ".pytest-owned"
    expected = f"university-ecosystem-pytest:{os.getpid()}:{database_dir.name}\n"
    try:
        if sentinel.read_text(encoding="utf-8") != expected:
            return
    except OSError:
        return
    shutil.rmtree(database_dir, ignore_errors=True)


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
    original_run_tests = getattr(cli.PytestRunner, "run_tests", None)
    parent_pid = os.getpid()

    def _prepare_runner_process(runner: Any) -> Path | None:
        """Apply all process-local resources before a pytest invocation."""

        if os.getpid() == parent_pid:
            _configure_process_local_pytest_cache(runner)
            return None
        database_dir = _isolate_mutation_child_database()
        _configure_process_local_pytest_cache(runner)
        return database_dir

    def _reuse_precomputed_test_ids(_runner: Any) -> Any:
        _prepare_runner_process(_runner)
        return cli.ListAllTestsResult(ids=set(cli.collected_test_names()))

    def _run_selected_forced_fail(runner: Any) -> Any:
        return runner.run_tests(
            mutant_name=None,
            tests=cli.tests_for_mutant_names(selected_mutants),
        )

    def _run_process_isolated_tests(
        runner: Any, *, mutant_name: str | None, tests: Sequence[str]
    ) -> int:
        database_dir = _prepare_runner_process(runner)
        try:
            if original_run_tests is None:
                raise RuntimeError("mutmut PytestRunner does not implement run_tests")
            return int(original_run_tests(runner, mutant_name=mutant_name, tests=tests))
        finally:
            if database_dir is not None:
                _dispose_inherited_database()
                _cleanup_mutation_child_database(database_dir)

    cli.PytestRunner.list_all_tests = _reuse_precomputed_test_ids
    cli.PytestRunner.run_forced_fail = _run_selected_forced_fail
    if original_run_tests is not None:
        cli.PytestRunner.run_tests = _run_process_isolated_tests
    try:
        # `_run` is pinned with mutmut==3.7.0.  It still owns all mutation
        # phases. The temporary hooks reuse redundant collection and align
        # forced-fail with mutmut's exact clean/mutation test selection.
        with _reuse_universe():
            cli._run(selected_mutants, max_children=max_children)
    finally:
        cli.PytestRunner.list_all_tests = original_list_all_tests
        cli.PytestRunner.run_forced_fail = original_run_forced_fail
        if original_run_tests is not None:
            cli.PytestRunner.run_tests = original_run_tests


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
