#!/usr/bin/env python3
"""Merge exact mutmut execution shards without weakening the score gate.

Each execution leg publishes a machine-readable shard report together with
the exact-selection manifests produced by ``export_mutmut_shard_stats.py``.
This helper validates every report, rejects overlaps, requires every leg to
have the same pristine universe fingerprint, and only then writes the summed
CI/CD statistics consumed by ``check_mutation_score.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

_SCHEMA_VERSION = 1
_REQUIRED_STATS_FIELDS = (
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
_STATUS_TO_FIELD = {
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


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read JSON evidence {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON evidence must be an object: {path}")
    return payload


def _digest_names(names: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(sorted(names)).encode("utf-8")).hexdigest()


def _digest_results(records: Iterable[Mapping[str, Any]]) -> str:
    canonical = "\n".join(
        f"{record['mutant_name']}\t{record['exit_code']}\t{record['status']}"
        for record in records
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _non_negative_int(payload: Mapping[str, Any], field: str, path: Path) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{path}: {field} must be a non-negative integer")
    return value


def _validate_shard(stats_path: Path) -> tuple[list[str], dict[str, int], str, int]:
    stats = _read_json(stats_path)
    evidence_dir = stats_path.parent / "mutmut-exact-evidence"
    selected_path = evidence_dir / "selected-mutants.json"
    results_path = evidence_dir / "selected-results.json"
    proof_path = evidence_dir / "execution-proof.json"
    selected = _read_json(selected_path)
    results = _read_json(results_path)
    proof = _read_json(proof_path)

    names_value = selected.get("selected_mutants")
    if not isinstance(names_value, list) or not names_value:
        raise ValueError(f"{selected_path}: selected_mutants must be non-empty")
    if any(not isinstance(name, str) or not name for name in names_value):
        raise ValueError(f"{selected_path}: selected mutant IDs must be strings")
    names = list(names_value)
    if names != sorted(names) or len(names) != len(set(names)):
        raise ValueError(f"{selected_path}: mutant IDs must be sorted and unique")
    if selected.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError(f"{selected_path}: unsupported schema version")
    if selected.get("selected_count") != len(names):
        raise ValueError(f"{selected_path}: selected_count does not match IDs")
    selection_digest = _digest_names(names)
    if selected.get("selection_sha256") != selection_digest:
        raise ValueError(f"{selected_path}: selection digest mismatch")

    result_records = results.get("selected_results")
    if results.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError(f"{results_path}: unsupported schema version")
    if results.get("execution_complete") is False:
        raise ValueError(f"{results_path}: incomplete execution evidence")
    if (
        not isinstance(result_records, list)
        or len(result_records) != len(names)
        or any(not isinstance(record, dict) for record in result_records)
    ):
        raise ValueError(f"{results_path}: terminal result count mismatch")
    result_names = [record.get("mutant_name") for record in result_records]
    if result_names != names:
        raise ValueError(f"{results_path}: result IDs do not match selection")
    if results.get("selected_count") != len(names):
        raise ValueError(f"{results_path}: selected_count does not match IDs")
    if results.get("selection_sha256") != selection_digest:
        raise ValueError(f"{results_path}: selection digest mismatch")
    if results.get("selected_results_sha256") != _digest_results(result_records):
        raise ValueError(f"{results_path}: results digest mismatch")
    if any(
        not isinstance(record, dict)
        or not isinstance(record.get("status"), str)
        or record.get("status") == "not checked"
        or record.get("exit_code") is None
        for record in result_records
    ):
        raise ValueError(f"{results_path}: every result must be terminal")

    universe_digest = proof.get("universe_sha256")
    universe_count = proof.get("universe_count")
    if proof.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError(f"{proof_path}: unsupported schema version")
    if proof.get("selection_sha256") != selection_digest:
        raise ValueError(f"{proof_path}: selection digest mismatch")
    if proof.get("selected_count") != len(names):
        raise ValueError(f"{proof_path}: selected_count does not match IDs")
    if proof.get("completed_selected_count") != len(names):
        raise ValueError(f"{proof_path}: not every selected mutant completed")
    if proof.get("completed_unselected_count") != 0:
        raise ValueError(f"{proof_path}: unselected mutants were executed")
    if not isinstance(universe_digest, str) or not universe_digest:
        raise ValueError(f"{proof_path}: missing universe digest")
    if (
        isinstance(universe_count, bool)
        or not isinstance(universe_count, int)
        or universe_count < 1
    ):
        raise ValueError(f"{proof_path}: invalid universe count")

    counts = {
        field: _non_negative_int(stats, field, stats_path)
        for field in _REQUIRED_STATS_FIELDS
    }
    if counts["total"] != len(names):
        raise ValueError(f"{stats_path}: total does not match selected mutant count")
    expected_counts = {field: 0 for field in _REQUIRED_STATS_FIELDS}
    expected_counts["total"] = len(names)
    for record in result_records:
        field = _STATUS_TO_FIELD.get(record["status"])
        if field is None:
            raise ValueError(f"{results_path}: unsupported status {record['status']!r}")
        expected_counts[field] += 1
    if counts != expected_counts:
        raise ValueError(f"{stats_path}: status counts do not match exact results")

    return names, counts, universe_digest, universe_count


def merge_stats(paths: list[Path], *, expected_shards: int) -> dict[str, int | str]:
    """Validate and sum exact mutation shards."""

    if expected_shards < 1:
        raise ValueError("expected_shards must be positive")
    if len(paths) != expected_shards:
        raise ValueError(
            f"expected {expected_shards} exact mutation shards, found {len(paths)}"
        )

    totals = {field: 0 for field in _REQUIRED_STATS_FIELDS}
    all_names: set[str] = set()
    universe_digest: str | None = None
    universe_count: int | None = None
    for path in sorted(paths):
        names, counts, shard_universe_digest, shard_universe_count = _validate_shard(
            path
        )
        overlap = all_names.intersection(names)
        if overlap:
            raise ValueError(f"exact mutation shard overlap: {sorted(overlap)}")
        if universe_digest is None:
            universe_digest = shard_universe_digest
            universe_count = shard_universe_count
        elif (shard_universe_digest, shard_universe_count) != (
            universe_digest,
            universe_count,
        ):
            raise ValueError(
                "exact mutation shards were generated from different universes"
            )
        all_names.update(names)
        for field, value in counts.items():
            totals[field] += value

    if universe_count is None or universe_digest is None:
        raise ValueError("exact mutation shards contain no universe fingerprint")
    if len(all_names) != universe_count:
        raise ValueError(
            "exact mutation shards do not cover the complete universe: "
            f"selected={len(all_names)} universe={universe_count}"
        )
    if totals["total"] != universe_count:
        raise ValueError("merged exact mutation total does not match universe count")
    return {
        **totals,
        "shards": expected_shards,
        "universe_count": universe_count,
        "universe_sha256": universe_digest,
        "selection_sha256": _digest_names(all_names),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=Path("mutmut-shards"))
    parser.add_argument("--expected-shards", type=int, required=True)
    parser.add_argument(
        "--output", type=Path, default=Path("mutants/mutmut-cicd-stats.json")
    )
    args = parser.parse_args()
    if args.expected_shards < 1:
        parser.error("--expected-shards must be positive")
    if not args.input_root.exists():
        parser.error(f"input directory does not exist: {args.input_root}")
    return args


def main() -> None:
    args = _parse_args()
    paths = sorted(args.input_root.rglob("mutmut-cicd-stats.json"))
    merged = merge_stats(paths, expected_shards=args.expected_shards)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(merged, indent=4, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"Merged {args.expected_shards} exact mutmut shards: "
        f"{merged['total']} mutants, universe {merged['universe_sha256']}"
    )


if __name__ == "__main__":
    main()
