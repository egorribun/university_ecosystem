"""Strict, supplemental coverage gate for the AUD-346 helper and this checker.

This report is independent of normalized aggregate coverage and its source scope.
The exact current source statements and branch arcs must all have been executed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from coverage.parser import PythonParser

ROOT = Path(__file__).resolve().parents[2]
SOURCES = (
    "scripts/chaos/aud346_failure_diagnostics.py",
    "scripts/quality/verify_aud346_diagnostic_coverage.py",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate coverage JSON key")
        result[key] = value
    return result


def verify(report: Path) -> None:
    document = json.loads(report.read_text(), object_pairs_hook=unique_object)
    require(type(document) is dict, "coverage root must be an object")
    require(
        document.get("meta", {}).get("branch_coverage") is True, "branches unmeasured"
    )
    files = document.get("files")
    require(type(files) is dict, "coverage files must be an object")
    require(
        set(files) == set(SOURCES), "coverage must contain the exact canonical sources"
    )
    total_lines = total_branches = 0
    for source in SOURCES:
        path = ROOT / source
        require(path.resolve() == path, "source must be canonical")
        parser = PythonParser(filename=str(path))
        parser.parse_source()
        lines = sorted(parser.statements)
        counts = parser.exit_counts()
        branches = sorted([a, b] for a, b in parser.arcs() if counts.get(a, 0) > 1)
        require(bool(lines) and bool(branches), "empty source denominator")
        record = files[source]
        require(type(record) is dict, "coverage file record must be an object")
        require(record.get("missing_lines") == [], "uncovered statements")
        require(record.get("missing_branches") == [], "uncovered branches")
        require(record.get("excluded_lines") == [], "excluded statements")
        require(
            json.dumps(record.get("executed_lines")) == json.dumps(lines),
            "statement inventory differs from source",
        )
        require(
            json.dumps(record.get("executed_branches")) == json.dumps(branches),
            "branch inventory differs from source",
        )
        summary = record.get("summary")
        verify_summary(summary, len(lines), len(branches))
        total_lines += len(lines)
        total_branches += len(branches)
    verify_summary(document.get("totals"), total_lines, total_branches)
    print(
        f"AUD346 strict coverage: {total_lines} statements, {total_branches} branches, 100%"
    )


def verify_summary(summary: object, lines: int, branches: int) -> None:
    require(type(summary) is dict, "coverage summary must be an object")
    expected = {
        "covered_lines": lines,
        "num_statements": lines,
        "missing_lines": 0,
        "excluded_lines": 0,
        "covered_branches": branches,
        "num_branches": branches,
        "missing_branches": 0,
        "num_partial_branches": 0,
    }
    for key, value in expected.items():
        require(type(summary.get(key)) is int, "coverage count must be an integer")
        require(
            summary[key] == value, "coverage count differs from exact source inventory"
        )


if __name__ == "__main__":
    verify(Path(sys.argv[1]))
