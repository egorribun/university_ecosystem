#!/usr/bin/env python3
"""Export fail-closed mutation statistics for an exact shard or full mutmut run.

``mutmut export-cicd-stats`` aggregates every generated ``.meta`` file.  That
is unsuitable for the incremental CI job because a positional run deliberately
leaves unselected mutants as ``not checked``. This helper exports only the
exact mutant names assigned to an incremental shard. Its explicit ``--all``
mode is for a freshly-created full-run ``mutants`` directory and also retains
``caught_by_type_check``, which mutmut does not serialize itself.
"""

from __future__ import annotations

import argparse
import hashlib
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
_EXECUTION_PROOF_SCHEMA_VERSION = 1
_EXECUTION_EVIDENCE_SCHEMA_VERSION = 1
_SELECTED_MUTANTS_MANIFEST = "selected-mutants.json"
_SELECTED_RESULTS_MANIFEST = "selected-results.json"


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
    mutmut_cli.Config.ensure_loaded()
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


def _collect_all_results(mutmut_cli: Any) -> list[tuple[str, int | None]]:
    """Read the complete generated mutation metadata without filtering it."""
    mutmut_cli.Config.ensure_loaded()
    all_mutants, _ = mutmut_cli.collect_source_file_mutation_data(mutant_names=[])
    return [(mutant_name, exit_code) for _, mutant_name, exit_code in all_mutants]


def _validate_exact_mutant_names(selected_mutants: Sequence[str]) -> list[str]:
    names = list(selected_mutants)
    if not names:
        raise ValueError("selected mutant names must not be empty")
    if len(names) != len(set(names)):
        raise ValueError("selected mutant names contain duplicates")
    if any(any(token in name for token in _GLOB_TOKENS) for name in names):
        raise ValueError(
            "selected mutant names must be exact; glob patterns are forbidden"
        )
    return names


def _index_execution_results(
    all_results: Iterable[tuple[str, int | None]],
) -> dict[str, int | None]:
    observed: dict[str, int | None] = {}
    for mutant_name, exit_code in all_results:
        if mutant_name in observed:
            raise ValueError(f"mutant metadata contains duplicate {mutant_name!r}")
        observed[mutant_name] = exit_code
    if not observed:
        raise ValueError("mutmut metadata contains no mutants")
    return observed


def _selection_digest(names: Iterable[str]) -> str:
    """Return a stable digest for an unordered exact-name set."""
    canonical = "\n".join(sorted(names)).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _selected_mutants_manifest(selected_mutants: Sequence[str]) -> dict[str, Any]:
    """Build a stable, concrete manifest of the exact selected mutant IDs."""
    names = sorted(_validate_exact_mutant_names(selected_mutants))
    return {
        "schema_version": _EXECUTION_EVIDENCE_SCHEMA_VERSION,
        "selection_sha256": _selection_digest(names),
        "selected_count": len(names),
        "selected_mutants": names,
    }


def _selected_result_records(
    selected_mutants: Sequence[str],
    selected_results: Iterable[tuple[str, int | None]],
    status_by_exit_code: Mapping[int | None, str],
) -> list[dict[str, int | str]]:
    """Return canonical terminal records for the exact selected mutant IDs."""
    names = sorted(_validate_exact_mutant_names(selected_mutants))
    expected = set(names)
    observed: dict[str, int | None] = {}
    for mutant_name, exit_code in selected_results:
        if mutant_name not in expected:
            raise ValueError(
                f"mutmut returned result outside the selected shard: {mutant_name!r}"
            )
        if mutant_name in observed:
            raise ValueError(f"mutant {mutant_name!r} appears more than once")
        if exit_code is None:
            raise ValueError(f"selected mutant {mutant_name!r} has no terminal outcome")
        observed[mutant_name] = exit_code

    missing = sorted(expected - observed.keys())
    if missing:
        raise ValueError(f"mutmut is missing selected mutants: {missing}")

    records: list[dict[str, int | str]] = []
    for mutant_name in names:
        exit_code = observed[mutant_name]
        try:
            status = status_by_exit_code[exit_code]
        except KeyError as exc:
            raise ValueError(
                f"mutmut returned an unmapped exit code for {mutant_name!r}"
            ) from exc
        if status == "not checked":
            raise ValueError(f"selected mutant {mutant_name!r} has no terminal outcome")
        records.append(
            {
                "mutant_name": mutant_name,
                "exit_code": exit_code,
                "status": status,
            }
        )
    return records


def _selected_results_digest(records: Iterable[Mapping[str, int | str]]) -> str:
    """Return a stable digest over the concrete selected-outcome records."""
    canonical = "\n".join(
        f"{record['mutant_name']}\t{record['exit_code']}\t{record['status']}"
        for record in records
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def write_exact_execution_selection_manifest(
    evidence_dir: Path, selected_mutants: Sequence[str]
) -> None:
    """Persist concrete selected IDs before mutmut starts its exact run."""
    _write_json(
        evidence_dir / _SELECTED_MUTANTS_MANIFEST,
        _selected_mutants_manifest(selected_mutants),
    )


def write_exact_execution_evidence(
    evidence_dir: Path,
    selected_mutants: Sequence[str],
    selected_results: Iterable[tuple[str, int | None]],
    status_by_exit_code: Mapping[int | None, str],
) -> None:
    """Persist deterministic selected IDs and terminal mutmut outcomes."""
    selected_manifest = _selected_mutants_manifest(selected_mutants)
    result_records = _selected_result_records(
        selected_mutants, selected_results, status_by_exit_code
    )
    _write_json(evidence_dir / _SELECTED_MUTANTS_MANIFEST, selected_manifest)
    _write_json(
        evidence_dir / _SELECTED_RESULTS_MANIFEST,
        {
            "schema_version": _EXECUTION_EVIDENCE_SCHEMA_VERSION,
            "selection_sha256": selected_manifest["selection_sha256"],
            "selected_count": selected_manifest["selected_count"],
            "selected_results_sha256": _selected_results_digest(result_records),
            "selected_results": result_records,
        },
    )


def _partial_selected_result_records(
    selected_mutants: Sequence[str],
    all_results: Iterable[tuple[str, int | None]] | None,
    status_by_exit_code: Mapping[int | None, str],
) -> tuple[list[dict[str, Any]], dict[str, int | None], list[str]]:
    """Build concrete selected records without requiring every child to finish."""
    names = sorted(_validate_exact_mutant_names(selected_mutants))
    observed: dict[str, int | None] = {}
    duplicate_names: list[str] = []
    if all_results is not None:
        for mutant_name, exit_code in all_results:
            if mutant_name in observed:
                duplicate_names.append(mutant_name)
                continue
            observed[mutant_name] = exit_code

    records: list[dict[str, Any]] = []
    for mutant_name in names:
        exit_code = observed.get(mutant_name)
        if exit_code is None:
            status = status_by_exit_code.get(None, "not checked")
            terminal = False
        else:
            status = status_by_exit_code.get(exit_code, "unknown")
            terminal = status != "not checked"
        records.append(
            {
                "mutant_name": mutant_name,
                "exit_code": exit_code,
                "status": status,
                "terminal": terminal,
            }
        )
    return records, observed, sorted(duplicate_names)


def _partial_selected_results_digest(records: Iterable[Mapping[str, Any]]) -> str:
    """Return a stable digest over partial records, including terminal state."""
    canonical = "\n".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) for record in records
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def write_incomplete_exact_execution_evidence(
    evidence_dir: Path,
    selected_mutants: Sequence[str],
    all_results: Iterable[tuple[str, int | None]] | None,
    status_by_exit_code: Mapping[int | None, str],
    execution_plan: Mapping[str, Any],
    *,
    mutation_exit_code: int | None,
    tee_exit_code: int | None,
    failure_exit_code: int,
    failure_reason: str,
    metadata_collection_error: str | None = None,
) -> dict[str, Any]:
    """Persist auditable partial outcomes after a failed exact mutmut run.

    Failure evidence must never masquerade as a completed exact run.  Missing
    metadata therefore becomes a concrete ``not checked`` outcome for every
    selected ID, while any terminal records already persisted by mutmut remain
    visible to reviewers.
    """
    selected_manifest = _selected_mutants_manifest(selected_mutants)
    result_records, observed, duplicate_names = _partial_selected_result_records(
        selected_mutants, all_results, status_by_exit_code
    )
    selected_names = selected_manifest["selected_mutants"]
    expected_names = set(selected_names)
    completed_selected_count = sum(record["terminal"] for record in result_records)
    incomplete_selected_count = len(result_records) - completed_selected_count
    plan_matches_selection = (
        execution_plan.get("schema_version") == _EXECUTION_PROOF_SCHEMA_VERSION
        and execution_plan.get("selection_sha256")
        == selected_manifest["selection_sha256"]
        and execution_plan.get("selected_count") == selected_manifest["selected_count"]
    )
    plan_matches_universe = (
        all_results is not None
        and not duplicate_names
        and execution_plan.get("universe_sha256") == _selection_digest(observed)
        and execution_plan.get("universe_count") == len(observed)
    )
    _write_json(evidence_dir / _SELECTED_MUTANTS_MANIFEST, selected_manifest)
    _write_json(
        evidence_dir / _SELECTED_RESULTS_MANIFEST,
        {
            "schema_version": _EXECUTION_EVIDENCE_SCHEMA_VERSION,
            "execution_complete": False,
            "selection_sha256": selected_manifest["selection_sha256"],
            "selected_count": selected_manifest["selected_count"],
            "selected_results_sha256": _partial_selected_results_digest(result_records),
            "selected_results": result_records,
        },
    )
    return {
        "schema_version": _EXECUTION_PROOF_SCHEMA_VERSION,
        "execution_complete": False,
        "failure_reason": failure_reason,
        "failure_exit_code": failure_exit_code,
        "mutation_exit_code": mutation_exit_code,
        "tee_exit_code": tee_exit_code,
        "selection_sha256": selected_manifest["selection_sha256"],
        "selected_count": selected_manifest["selected_count"],
        "universe_sha256": _selection_digest(observed),
        "universe_count": len(observed),
        "completed_selected_count": completed_selected_count,
        "incomplete_selected_count": incomplete_selected_count,
        "completed_unselected_count": sum(
            exit_code is not None
            for mutant_name, exit_code in observed.items()
            if mutant_name not in expected_names
        ),
        "metadata_available": all_results is not None,
        "metadata_duplicate_names": duplicate_names,
        "metadata_collection_error": metadata_collection_error,
        "execution_plan_matches_selection": plan_matches_selection,
        "execution_plan_matches_universe": plan_matches_universe,
        "selected_manifest": _SELECTED_MUTANTS_MANIFEST,
        "selected_results_manifest": _SELECTED_RESULTS_MANIFEST,
    }


def _validated_execution_universe(
    selected_mutants: Sequence[str], all_results: Iterable[tuple[str, int | None]]
) -> tuple[list[str], dict[str, int | None]]:
    names = _validate_exact_mutant_names(selected_mutants)
    observed = _index_execution_results(all_results)
    missing = set(names) - observed.keys()
    if missing:
        raise ValueError(f"mutmut is missing selected mutants: {sorted(missing)}")
    return names, observed


def verify_exact_execution(
    selected_mutants: Sequence[str], all_results: Iterable[tuple[str, int | None]]
) -> list[tuple[str, int | None]]:
    """Fail unless a completed run executed exactly the assigned mutant names."""
    names, observed = _validated_execution_universe(selected_mutants, all_results)
    expected = set(names)
    incomplete = sorted(
        mutant_name for mutant_name in names if observed[mutant_name] is None
    )
    if incomplete:
        raise ValueError(f"selected mutants were not executed: {incomplete}")

    outside_shard = sorted(
        mutant_name
        for mutant_name, exit_code in observed.items()
        if mutant_name not in expected and exit_code is not None
    )
    if outside_shard:
        raise ValueError(f"mutmut executed unselected mutants: {outside_shard}")
    return [(mutant_name, observed[mutant_name]) for mutant_name in names]


def prepare_exact_execution_plan(
    selected_mutants: Sequence[str], all_results: Iterable[tuple[str, int | None]]
) -> dict[str, int | str]:
    """Snapshot a pristine metadata universe before an exact mutmut run."""
    names, observed = _validated_execution_universe(selected_mutants, all_results)
    preexisting_results = sorted(
        mutant_name
        for mutant_name, exit_code in observed.items()
        if exit_code is not None
    )
    if preexisting_results:
        raise ValueError(
            "mutmut metadata is not pristine before exact execution: "
            f"{preexisting_results}"
        )
    return {
        "schema_version": _EXECUTION_PROOF_SCHEMA_VERSION,
        "selection_sha256": _selection_digest(names),
        "selected_count": len(names),
        "universe_sha256": _selection_digest(observed),
        "universe_count": len(observed),
    }


def _validate_execution_plan(
    plan: Mapping[str, Any],
    selected_names: Sequence[str],
    observed: Mapping[str, int | None],
) -> None:
    expected = {
        "schema_version": _EXECUTION_PROOF_SCHEMA_VERSION,
        "selection_sha256": _selection_digest(selected_names),
        "selected_count": len(selected_names),
        "universe_sha256": _selection_digest(observed),
        "universe_count": len(observed),
    }
    for field, expected_value in expected.items():
        if plan.get(field) != expected_value:
            if field.startswith("universe"):
                raise ValueError("mutmut execution universe changed after planning")
            if field.startswith("selection") or field == "selected_count":
                raise ValueError("mutmut exact selection changed after planning")
            raise ValueError("mutmut execution plan has an unsupported schema")


def verify_exact_execution_plan(
    selected_mutants: Sequence[str],
    all_results: Iterable[tuple[str, int | None]],
    plan: Mapping[str, Any],
) -> tuple[list[tuple[str, int | None]], dict[str, int | str]]:
    """Verify a completed exact run against its immutable pristine snapshot."""
    results = list(all_results)
    names, observed = _validated_execution_universe(selected_mutants, results)
    _validate_execution_plan(plan, names, observed)
    selected_results = verify_exact_execution(names, results)
    return selected_results, {
        "schema_version": _EXECUTION_PROOF_SCHEMA_VERSION,
        "selection_sha256": _selection_digest(names),
        "selected_count": len(names),
        "universe_sha256": _selection_digest(observed),
        "universe_count": len(observed),
        "completed_selected_count": len(selected_results),
        "completed_unselected_count": 0,
        "selected_manifest": _SELECTED_MUTANTS_MANIFEST,
        "selected_results_manifest": _SELECTED_RESULTS_MANIFEST,
    }


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
    parser.add_argument(
        "--verify-exact-execution",
        type=Path,
        metavar="EXECUTION_PLAN",
        help=("verify a completed exact run against this pristine execution plan"),
    )
    parser.add_argument(
        "--prepare-exact-execution",
        type=Path,
        metavar="EXECUTION_PLAN",
        help="write a pristine exact-execution plan before running mutmut",
    )
    parser.add_argument(
        "--finalize-incomplete-execution",
        type=Path,
        metavar="EXECUTION_PLAN",
        help="write partial exact-execution evidence after a failed mutmut run",
    )
    parser.add_argument(
        "--mutation-exit-code",
        type=int,
        help="captured timeout/mutmut pipeline exit code for incomplete evidence",
    )
    parser.add_argument(
        "--tee-exit-code",
        type=int,
        help="captured tee pipeline exit code for incomplete evidence",
    )
    parser.add_argument(
        "--failure-exit-code",
        type=int,
        help="exit code of the post-selection branch that requires failure evidence",
    )
    parser.add_argument(
        "--failure-reason",
        help="auditable reason the exact mutation evidence did not complete",
    )
    parser.add_argument(
        "--execution-proof",
        type=Path,
        default=Path("mutants/mutmut-exact-evidence/execution-proof.json"),
        help="destination for the verified or incomplete exact-execution proof",
    )
    parser.add_argument(
        "--execution-evidence-dir",
        type=Path,
        default=Path("mutants/mutmut-exact-evidence"),
        help="directory for deterministic selected-ID and selected-result evidence",
    )
    args = parser.parse_args()
    execution_modes = (
        args.verify_exact_execution,
        args.prepare_exact_execution,
        args.finalize_incomplete_execution,
    )
    if sum(mode is not None for mode in execution_modes) > 1:
        parser.error("exact-execution modes are mutually exclusive")
    if any(mode is not None for mode in execution_modes) and args.selected_file is None:
        parser.error("exact-execution planning requires --selected-file")
    if args.finalize_incomplete_execution is not None:
        if args.failure_exit_code is None:
            parser.error("--finalize-incomplete-execution requires --failure-exit-code")
        if not args.failure_reason:
            parser.error("--finalize-incomplete-execution requires --failure-reason")
    return args


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read exact-execution plan {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("exact-execution plan must be a JSON object")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        raise ValueError(f"unable to write JSON evidence to {path}: {exc}") from exc


def main() -> None:
    """Export trustworthy mutation evidence or fail before its score can be used."""
    args = _parse_args()
    try:
        selected_mutants = (
            load_selected_mutants(args.selected_file)
            if args.selected_file is not None
            else []
        )
        if args.finalize_incomplete_execution is not None:
            failure_details: list[str] = []
            try:
                execution_plan = _read_json(args.finalize_incomplete_execution)
            except ValueError as exc:
                execution_plan = {}
                failure_details.append(str(exc))

            all_results: list[tuple[str, int | None]] | None = None
            status_by_exit_code: Mapping[int | None, str] = {}
            try:
                mutmut_cli = _load_mutmut_cli()
                all_results = _collect_all_results(mutmut_cli)
                status_by_exit_code = mutmut_cli.status_by_exit_code
            except Exception as exc:  # RZ-22-01-JUSTIFIED: preserve failure evidence when mutmut metadata probing itself fails
                failure_details.append(
                    "unable to collect mutmut metadata for incomplete evidence: "
                    f"{type(exc).__name__}: {exc}"
                )

            execution_proof = write_incomplete_exact_execution_evidence(
                args.execution_evidence_dir,
                selected_mutants,
                all_results,
                status_by_exit_code,
                execution_plan,
                mutation_exit_code=args.mutation_exit_code,
                tee_exit_code=args.tee_exit_code,
                failure_exit_code=args.failure_exit_code,
                failure_reason=args.failure_reason,
                metadata_collection_error="; ".join(failure_details) or None,
            )
            _write_json(args.execution_proof, execution_proof)
            print(
                "Exported incomplete exact mutmut evidence for "
                f"{execution_proof['selected_count']} selected mutants to "
                f"{args.execution_evidence_dir}"
            )
            return

        mutmut_cli = _load_mutmut_cli()
        if args.prepare_exact_execution is not None:
            plan = prepare_exact_execution_plan(
                selected_mutants,
                _collect_all_results(mutmut_cli),
            )
            _write_json(args.prepare_exact_execution, plan)
            write_exact_execution_selection_manifest(
                args.execution_evidence_dir, selected_mutants
            )
            print(
                "Prepared pristine exact mutmut execution plan for "
                f"{plan['selected_count']} selected mutants at "
                f"{args.prepare_exact_execution}"
            )
            return

        if args.verify_exact_execution is not None:
            selected_results, execution_proof = verify_exact_execution_plan(
                selected_mutants,
                _collect_all_results(mutmut_cli),
                _read_json(args.verify_exact_execution),
            )
            write_exact_execution_evidence(
                args.execution_evidence_dir,
                selected_mutants,
                selected_results,
                mutmut_cli.status_by_exit_code,
            )
            _write_json(args.execution_proof, execution_proof)
        else:
            selected_results, _ = _collect_selected_results(
                selected_mutants, mutmut_cli
            )
        status_by_exit_code = mutmut_cli.status_by_exit_code
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
        _write_json(args.output, stats)
    except ValueError as exc:
        raise SystemExit(
            f"ERROR: unable to write trustworthy mutmut stats: {exc}"
        ) from exc
    scope = "complete mutmut universe" if args.all else "exact mutmut shard"
    print(f"Exported {scope} evidence for {stats['total']} mutants to {args.output}")


if __name__ == "__main__":
    main()
