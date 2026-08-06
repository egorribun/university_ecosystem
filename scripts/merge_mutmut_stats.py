"""Merge disjoint mutmut pytest-stats artifacts without weakening evidence."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-root",
        type=Path,
        default=Path("mutmut-stats"),
        help="Directory containing downloaded mutmut-stats.json artifacts",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("mutants/mutmut-stats.json"),
    )
    args = parser.parse_args()
    if not args.input_root.exists():
        parser.error(f"input directory does not exist: {args.input_root}")
    return args


def _read_stats(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {"tests_by_mangled_function_name", "duration_by_test", "stats_time"}
    missing = required - payload.keys()
    if missing:
        raise ValueError(f"{path} is missing mutmut stats keys: {sorted(missing)}")
    if not isinstance(payload["tests_by_mangled_function_name"], dict):
        raise ValueError(f"{path} has an invalid mutant-to-test mapping")
    if not isinstance(payload["duration_by_test"], dict):
        raise ValueError(f"{path} has an invalid test-duration mapping")
    return payload


def merge_stats(paths: list[Path]) -> dict[str, Any]:
    """Union mutant-to-test mappings and durations from disjoint shards.

    Duplicate test IDs are rejected: the stats matrix is intended to be a
    partition, and silently accepting overlap would hide a sharding defect.
    Conflicting durations are also rejected because they indicate that the
    artifacts were produced from different test populations or commits.
    """

    if not paths:
        raise ValueError("no mutmut stats artifacts were found")

    tests_by_mutant: dict[str, set[str]] = defaultdict(set)
    duration_by_test: dict[str, float] = {}
    test_owner: dict[str, Path] = {}
    stats_time = 0.0

    for path in sorted(paths):
        payload = _read_stats(path)
        stats_time += float(payload["stats_time"] or 0.0)

        for test_name, duration in payload["duration_by_test"].items():
            if test_name in duration_by_test:
                previous = test_owner[test_name]
                if not math.isclose(
                    duration_by_test[test_name],
                    float(duration),
                    rel_tol=1e-9,
                    abs_tol=1e-9,
                ):
                    raise ValueError(
                        f"test {test_name!r} has conflicting durations in "
                        f"{previous} and {path}"
                    )
                raise ValueError(
                    f"test {test_name!r} appears in multiple stats shards: "
                    f"{previous} and {path}"
                )
            duration_by_test[test_name] = float(duration)
            test_owner[test_name] = path

        for mutant_name, test_names in payload[
            "tests_by_mangled_function_name"
        ].items():
            if not isinstance(test_names, list):
                raise ValueError(
                    f"{path} has non-list tests for mutant {mutant_name!r}"
                )
            tests_by_mutant[mutant_name].update(test_names)

    if not duration_by_test:
        raise ValueError("merged mutmut stats contain no active tests")
    if not any(tests_by_mutant.values()):
        raise ValueError("merged mutmut stats contain no mutant-to-test associations")

    return {
        "tests_by_mangled_function_name": {
            mutant: sorted(test_names)
            for mutant, test_names in sorted(tests_by_mutant.items())
        },
        "duration_by_test": dict(sorted(duration_by_test.items())),
        "stats_time": stats_time,
    }


def main() -> None:
    args = _parse_args()
    paths = sorted(args.input_root.rglob("mutmut-stats.json"))
    merged = merge_stats(paths)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(merged, indent=4, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"Merged {len(paths)} mutmut stats shards: "
        f"{len(merged['duration_by_test'])} tests, "
        f"{len(merged['tests_by_mangled_function_name'])} mutant functions"
    )


if __name__ == "__main__":
    main()
