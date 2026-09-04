"""Update the historical pytest file-duration map from a JUnit XML report.

The sharding plugin deliberately assigns whole test files to shards.  Keeping
the measurements at file granularity makes the input deterministic and avoids
splitting fixtures or stateful tests across runners.  Existing entries are
preserved by default so a partial report cannot silently erase the historical
fallback map; CI's full-suite updater passes ``--replace`` when it has a
  complete report.  Replacement mode retains a positive historical value when
  a file contains skipped test cases: a partial or zero-second sample is not
  evidence that the file is cheap when some of its real tests were not run.
  Newly observed files whose cases are all skipped are omitted until a real
  duration is measured, so the planner falls back to its conservative default.
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
    # Pytest's JUnit writer uses the fully-qualified class name as the
    # ``classname`` when a test class is present (for example,
    # ``tests.test_auth.TestLogin``).  The historical map is keyed by whole
    # test files, so retaining that final class component creates a path which
    # can never be collected and silently forces the shard planner to use its
    # default duration.  Python test modules are conventionally lowercase,
    # while test classes are PascalCase; strip only the trailing PascalCase
    # components and leave ordinary module-only classnames unchanged.
    module_parts = module.split(".")
    while len(module_parts) > 1 and module_parts[-1][:1].isupper():
        module_parts.pop()
    module = ".".join(module_parts)
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
    executed_measured: dict[str, float] = {}
    skipped: dict[str, bool] = {}
    executed: dict[str, bool] = {}
    for testcase in root.iter("testcase"):
        path = _testcase_path(testcase)
        duration = _duration(testcase)
        measured[path] = measured.get(path, 0.0) + duration
        # Pytest records a small positive bookkeeping time for skipped tests,
        # so ``value == 0`` is not sufficient to identify an unmeasured file.
        # Keep a separate skip bit and never replace a historical estimate with
        # a report that did not execute every testcase in that file.
        is_skipped = testcase.find("skipped") is not None
        skipped[path] = skipped.get(path, False) or is_skipped
        executed[path] = executed.get(path, False) or not is_skipped
        if not is_skipped:
            executed_measured[path] = executed_measured.get(path, 0.0) + duration

    existing_durations = _read_existing(existing)
    durations = {} if replace else dict(existing_durations)
    for path, value in measured.items():
        if skipped.get(path, False):
            historical = existing_durations.get(path, 0.0)
            if historical > 0:
                durations[path] = historical
            elif executed.get(path, False) and executed_measured.get(path, 0.0) > 0:
                # A partial file still has an observed execution cost.  It is
                # safer to retain that lower bound than to collapse a large
                # file to the global default merely because one optional case
                # was skipped in this environment.
                durations[path] = executed_measured[path]
            elif replace:
                # An all-skipped replacement report provides no useful
                # estimate.  Leave the path absent so collection uses the
                # conservative default rather than a misleading 0.001 s.
                durations.pop(path, None)
            else:
                durations[path] = value
            continue
        durations[path] = value
    values = [value for path, value in measured.items() if not skipped.get(path, False)]
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
    if arguments.output.exists():
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
