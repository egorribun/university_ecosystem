#!/usr/bin/env python3
"""Reduce mutmut's test map to deterministic, observed kill probes.

Every selected test comes from mutmut's own runtime association map, so it is
known to execute the mapped function.  The reduction is monotonic for a strict
mutation gate: removing tests can turn a killed mutant into a survivor, but it
cannot turn a survivor into a killed mutant.  The nightly full-population gate
therefore uses this map for its primary pass and confirms every primary
survivor against the original complete map before publishing final evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _validated_durations(value: object) -> dict[str, float]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("duration_by_test must be a non-empty object")
    durations: dict[str, float] = {}
    for test_name, duration in value.items():
        if not isinstance(test_name, str) or not test_name:
            raise ValueError("duration_by_test keys must be non-empty strings")
        if isinstance(duration, bool) or not isinstance(duration, int | float):
            raise ValueError(f"duration for {test_name!r} must be numeric")
        numeric = float(duration)
        if not math.isfinite(numeric) or numeric < 0:
            raise ValueError(
                f"duration for {test_name!r} must be finite and non-negative"
            )
        durations[test_name] = numeric
    return durations


def _validated_mapping(
    value: object, durations: Mapping[str, float]
) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("tests_by_mangled_function_name must be a non-empty object")
    mapping: dict[str, tuple[str, ...]] = {}
    for function_name, raw_tests in value.items():
        if not isinstance(function_name, str) or not function_name:
            raise ValueError("mutmut function names must be non-empty strings")
        if (
            not isinstance(raw_tests, Sequence)
            or isinstance(raw_tests, str | bytes)
            or not raw_tests
            or any(
                not isinstance(test_name, str) or not test_name
                for test_name in raw_tests
            )
        ):
            raise ValueError(f"{function_name!r} must have a non-empty test list")
        tests = tuple(dict.fromkeys(raw_tests))
        missing = sorted(test_name for test_name in tests if test_name not in durations)
        if missing:
            raise ValueError(
                f"{function_name!r} has a missing duration for mapped tests: {missing}"
            )
        mapping[function_name] = tests
    return mapping


def reduce_stats_payload(
    payload: Mapping[str, Any], *, tests_per_function: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a deterministic monotonic subset and its auditable proof."""

    if tests_per_function < 1:
        raise ValueError("tests_per_function must be positive")
    durations = _validated_durations(payload.get("duration_by_test"))
    mapping = _validated_mapping(
        payload.get("tests_by_mangled_function_name"), durations
    )

    selected_mapping = {
        function_name: sorted(
            tests,
            key=lambda test_name: (durations[test_name], test_name),
        )[:tests_per_function]
        for function_name, tests in sorted(mapping.items())
    }
    selected_test_names = sorted(
        {
            test_name
            for test_names in selected_mapping.values()
            for test_name in test_names
        }
    )
    reduced: dict[str, Any] = {
        **payload,
        "tests_by_mangled_function_name": selected_mapping,
        "duration_by_test": {
            test_name: durations[test_name] for test_name in selected_test_names
        },
    }
    audit = {
        "schema_version": 1,
        "selection_policy": "fastest-observed-tests-per-function",
        "tests_per_function": tests_per_function,
        "function_count": len(mapping),
        "original_mapping_edges": sum(len(tests) for tests in mapping.values()),
        "selected_mapping_edges": sum(
            len(tests) for tests in selected_mapping.values()
        ),
        "original_test_count": len(durations),
        "selected_test_count": len(selected_test_names),
        "original_duration_seconds": math.fsum(durations.values()),
        "selected_duration_seconds": math.fsum(
            durations[test_name] for test_name in selected_test_names
        ),
        "monotonic_subset": True,
        "survivor_confirmation_required": True,
        "source_sha256": _sha256(payload),
        "reduced_sha256": _sha256(reduced),
    }
    return reduced, audit


def _read_payload(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read mutmut stats {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"mutmut stats must be a JSON object: {path}")
    return value


def _atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:  # RZ-22-01-JUSTIFIED: remove temp file, then re-raise
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--tests-per-function", type=int, default=1)
    args = parser.parse_args()
    if args.tests_per_function < 1:
        parser.error("--tests-per-function must be positive")
    return args


def main() -> int:
    args = _parse_args()
    reduced, audit = reduce_stats_payload(
        _read_payload(args.input), tests_per_function=args.tests_per_function
    )
    _atomic_write_json(args.output, reduced)
    _atomic_write_json(args.audit_output, audit)
    print(
        "Reduced mutmut mapping monotonically: "
        f"{audit['original_mapping_edges']} -> {audit['selected_mapping_edges']} "
        "function/test edges"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
