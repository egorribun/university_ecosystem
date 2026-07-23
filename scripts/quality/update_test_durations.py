"""Update the historical pytest file-duration map from a JUnit XML report.

The sharding plugin deliberately assigns whole test files to shards.  Keeping
the measurements at file granularity makes the input deterministic and avoids
splitting fixtures or stateful tests across runners.  Existing entries are
preserved by default so a partial report cannot silently erase the historical
fallback map; CI's full-suite updater passes ``--replace`` when it has a
complete report.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path, PurePosixPath
from typing import Any

from defusedxml import ElementTree


def _normalise_path(value: str) -> str:
    path = value.replace("\\", "/").strip()
    if not path:
        raise ValueError("JUnit testcase file must not be empty")
    if path.startswith("./"):
        path = path[2:]
    if not path.startswith("tests/"):
        path = f"tests/{path}"
    return str(PurePosixPath(path))


def _testcase_path(testcase: ElementTree.Element) -> str:
    file_name = testcase.get("file")
    if file_name:
        return _normalise_path(file_name)

    classname = testcase.get("classname", "").replace("\\", ".").strip(".")
    if not classname:
        raise ValueError("JUnit testcase must provide either file or classname")
    module = classname.split("::", 1)[0]
    return _normalise_path(module.replace(".", "/") + ".py")


def _duration(testcase: ElementTree.Element) -> float:
    raw_value = testcase.get("time", "")
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"JUnit testcase time is not numeric: {raw_value!r}"
        ) from error
    if not math.isfinite(value) or value < 0:
        raise ValueError(
            f"JUnit testcase time must be finite and non-negative: {raw_value!r}"
        )
    return value


def _read_existing(existing: dict[str, Any] | None) -> dict[str, float]:
    if not existing:
        return {}
    durations = existing.get("durations", {})
    if not isinstance(durations, dict):
        raise ValueError(
            "existing duration payload must contain an object named durations"
        )
    result: dict[str, float] = {}
    for path, value in durations.items():
        if not isinstance(path, str) or not isinstance(value, (int, float)):
            raise ValueError("existing durations must map paths to numbers")
        if not math.isfinite(float(value)) or float(value) < 0:
            raise ValueError(f"existing duration is invalid for {path!r}")
        result[_normalise_path(path)] = float(value)
    return result


def build_duration_payload(
    report_path: Path,
    *,
    existing: dict[str, Any] | None = None,
    replace: bool = False,
) -> dict[str, Any]:
    """Return a versioned duration payload built from ``report_path``."""

    try:
        root = ElementTree.parse(report_path).getroot()
    except (ElementTree.ParseError, OSError) as error:
        raise ValueError(
            f"unable to read JUnit report {report_path}: {error}"
        ) from error

    measured: dict[str, float] = {}
    for testcase in root.iter("testcase"):
        path = _testcase_path(testcase)
        measured[path] = measured.get(path, 0.0) + _duration(testcase)

    durations = {} if replace else _read_existing(existing)
    durations.update(measured)
    values = list(measured.values())
    default_duration = (
        round(statistics.median(values), 3)
        if values
        else float((existing or {}).get("default_duration_seconds", 1.0))
    )
    if not math.isfinite(default_duration) or default_duration < 0:
        raise ValueError("default_duration_seconds must be finite and non-negative")

    return {
        "version": 1,
        "default_duration_seconds": default_duration,
        "durations": {
            path: round(value, 3) for path, value in sorted(durations.items())
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="pytest JUnit XML report")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("quality/test-durations.json"),
        help="duration map to update",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="replace the historical map instead of preserving missing entries",
    )
    return parser.parse_args()


def main() -> int:
    arguments = _parse_args()
    existing: dict[str, Any] | None = None
    if arguments.output.exists() and not arguments.replace:
        try:
            existing = json.loads(arguments.output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SystemExit(f"cannot read existing duration map: {error}") from error

    try:
        payload = build_duration_payload(
            arguments.report,
            existing=existing,
            replace=arguments.replace,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Updated {arguments.output} with {len(payload['durations'])} file durations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
