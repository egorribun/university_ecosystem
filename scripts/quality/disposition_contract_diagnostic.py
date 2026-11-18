"""Finite, source-bound reproduction of two disposition contract test modules.

This optional diagnostic never replaces required CI or certifies coverage.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

_TARGETS = {
    "tests/test_verify_secrets_baseline.py": (
        "baseline",
        bytes.fromhex(
            "b9 f3 73 08 41 30 ec b2 4e f2 c0 a6 4f 57 e5 ef "
            "42 72 90 8b de b9 26 7c cb 28 45 80 33 e8 e2 0f"
        ),
    ),
    "tests/test_coverage_snapshot_disposition_rebind.py": (
        "snapshot",
        bytes.fromhex(
            "9c 05 28 e9 78 d9 dc 5a bb 81 e9 e2 97 de 55 4c "
            "e8 4b 86 8f 0e c6 58 dd 5e d5 00 5a 49 4e 72 bd"
        ),
    ),
}
_PHASES = ("setup", "call", "teardown")
_OUTCOMES = ("passed", "failed", "skipped")
_MAX_SOURCE_BYTES = 16 * 1024 * 1024
_MAX_ITEMS = 30000
_MAX_FAILURE_IDS = 128
_MAX_OUTPUT_BYTES = 32768


def source_catalog(root: Path) -> dict[tuple[str, str], tuple[str, int]]:
    """Bind every emitted ID to a top-level function in an exact Git postimage."""
    result = {}
    for relative, (label, expected) in _TARGETS.items():
        path = root / relative
        if path.resolve(strict=True) != path or not path.is_file():
            raise ValueError("source unavailable")
        if path.stat().st_size > _MAX_SOURCE_BYTES:
            raise ValueError("source oversized")
        data = path.read_bytes()
        if len(data) > _MAX_SOURCE_BYTES:
            raise ValueError("source oversized")
        digest = hashlib.sha256(data).digest()
        if digest != expected:
            raise ValueError("source identity mismatch")
        tree = ast.parse(data.decode("utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("test_"):
                    continue
                key = (relative, node.name)
                if key in result or not 0 < node.lineno <= 100000:
                    raise ValueError("source identity ambiguous")
                result[key] = (label, node.lineno)
    return result


class Recorder:
    def __init__(
        self, root: Path, catalog: dict[tuple[str, str], tuple[str, int]]
    ) -> None:
        self.root = root
        self.catalog = catalog
        self.items: dict[str, tuple[str, int]] = {}
        self.ambiguous: set[str] = set()
        self.counts = {phase: dict.fromkeys(_OUTCOMES, 0) for phase in _PHASES}
        self.failures: set[tuple[str, int, str]] = set()
        self.unmapped = 0
        self.collection_failures = 0
        self.truncated = False

    def pytest_collection_modifyitems(self, items: list[Any]) -> None:
        for item in items:
            if len(self.items) >= _MAX_ITEMS:
                self.truncated = True
                break
            nodeid = item.nodeid
            if type(nodeid) is not str or len(nodeid) > 1024:
                continue
            try:
                relative = item.path.resolve().relative_to(self.root).as_posix()
            except (OSError, ValueError):
                continue
            # Parameter values and nodeid text never become output.
            name = item.originalname
            if type(name) is not str or item.cls is not None:
                continue
            identity = self.catalog.get((relative, name))
            if identity is not None:
                if nodeid in self.items or nodeid in self.ambiguous:
                    self.items.pop(nodeid, None)
                    self.ambiguous.add(nodeid)
                else:
                    self.items[nodeid] = identity

    def pytest_collectreport(self, report: Any) -> None:
        if report.failed:
            self.collection_failures += 1

    def pytest_runtest_logreport(self, report: Any) -> None:
        phase, outcome = report.when, report.outcome
        if (
            type(phase) is not str
            or type(outcome) is not str
            or phase not in _PHASES
            or outcome not in _OUTCOMES
        ):
            self.unmapped += 1
            return
        self.counts[phase][outcome] += 1
        nodeid = report.nodeid
        identity = self.items.get(nodeid) if type(nodeid) is str else None
        if identity is None:
            self.unmapped += 1
        elif outcome == "failed":
            if len(self.failures) < _MAX_FAILURE_IDS:
                self.failures.add((*identity, phase))
            else:
                self.truncated = True

    def summary(self, exit_code: int) -> dict[str, object]:
        return {
            "status": "completed",
            "pytest_exit_code": exit_code,
            "report_counts": self.counts,
            "failure_ids": [
                {"module": module, "line": line, "phase": phase}
                for module, line, phase in sorted(self.failures)
            ],
            "collection_failure_count": self.collection_failures,
            "unmapped_report_count": self.unmapped,
            "truncated": self.truncated,
        }


def reproduce(root: Path) -> tuple[int, dict[str, object]]:
    catalog = source_catalog(root)
    recorder = Recorder(root, catalog)
    os.chdir(root)
    sys.path.insert(0, str(root))
    import pytest

    # Keep repository pytest settings, assertions, markers and exit semantics.
    result = pytest.main(list(_TARGETS), plugins=[recorder])
    if type(result) is not int and not isinstance(result, pytest.ExitCode):
        raise ValueError("pytest result unavailable")
    code = int(result)
    if code not in range(7):
        raise ValueError("pytest result unavailable")
    return code, recorder.summary(code)


def encode_summary(summary: dict[str, object], exit_code: int) -> bytes:
    """Validate the closed schema; source-catalog membership is Recorder's job.

    This receipt limits accidental test output, not hostile in-process code.
    """
    if (
        type(summary) is not dict
        or type(exit_code) is not int
        or exit_code not in range(7)
    ):
        raise ValueError("summary invalid")
    if summary.get("status") == "unavailable":
        if (
            set(summary) != {"status", "stage"}
            or type(summary["stage"]) is not str
            or summary["stage"]
            not in {
                "admission",
                "execution",
                "output_bound",
                "summary",
            }
        ):
            raise ValueError("summary invalid")
    else:
        if (
            set(summary)
            != {
                "status",
                "pytest_exit_code",
                "report_counts",
                "failure_ids",
                "collection_failure_count",
                "unmapped_report_count",
                "truncated",
            }
            or summary["status"] != "completed"
        ):
            raise ValueError("summary invalid")
        if (
            type(summary["pytest_exit_code"]) is not int
            or summary["pytest_exit_code"] != exit_code
        ):
            raise ValueError("summary invalid")
        for key in ("collection_failure_count", "unmapped_report_count"):
            if type(summary[key]) is not int or not 0 <= summary[key] <= 1000000000:
                raise ValueError("summary invalid")
        if type(summary["truncated"]) is not bool:
            raise ValueError("summary invalid")
        counts = summary["report_counts"]
        if type(counts) is not dict or set(counts) != set(_PHASES):
            raise ValueError("summary invalid")
        for outcomes in counts.values():
            if type(outcomes) is not dict or set(outcomes) != set(_OUTCOMES):
                raise ValueError("summary invalid")
            for count in outcomes.values():
                if type(count) is not int or not 0 <= count <= 1000000000:
                    raise ValueError("summary invalid")
        failures = summary["failure_ids"]
        if type(failures) is not list or len(failures) > _MAX_FAILURE_IDS:
            raise ValueError("summary invalid")
        seen = set()
        for row in failures:
            if type(row) is not dict or set(row) != {"module", "line", "phase"}:
                raise ValueError("summary invalid")
            if (
                type(row["module"]) is not str
                or row["module"] not in {"baseline", "snapshot"}
                or type(row["phase"]) is not str
                or row["phase"] not in _PHASES
                or type(row["line"]) is not int
                or not 0 < row["line"] <= 100000
            ):
                raise ValueError("summary invalid")
            identity = (row["module"], row["line"], row["phase"])
            if identity in seen:
                raise ValueError("summary invalid")
            seen.add(identity)
    if type(summary["status"]) is not str:
        raise ValueError("summary invalid")
    encoded = json.dumps(summary, sort_keys=True, separators=(",", ":")).encode()
    if len(encoded) > _MAX_OUTPUT_BYTES:
        raise ValueError("summary oversized")
    return encoded + b"\n"


def main(argv: list[str] | None = None) -> int:
    # Keep fd1/2 muted through interpreter/atexit cleanup. Only the retained
    # descriptor receives the finite summary; no raw test output is retained.
    output = os.dup(1)
    try:
        os.set_inheritable(output, False)
        null = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(null, 1)
            os.dup2(null, 2)
        finally:
            os.close(null)
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
        code = 3
        summary: dict[str, object] = {"status": "unavailable", "stage": "admission"}
        try:
            arguments = sys.argv[1:] if argv is None else argv
            workspace = Path(os.environ["GITHUB_WORKSPACE"])
            if not workspace.is_absolute():
                raise ValueError("workspace unavailable")
            root = workspace / "subject"
            if arguments != ["--subject-root", str(root)]:
                raise ValueError("subject unavailable")
            if root.resolve(strict=True) != root or not root.is_dir():
                raise ValueError("subject unavailable")
            summary = {"status": "unavailable", "stage": "execution"}
            code, summary = reproduce(root)
        except BaseException:
            # Never expose exception names, messages, tracebacks or parameter values.
            code = 3
        try:
            try:
                encoded = encode_summary(summary, code)
            except (ValueError, TypeError):
                if code == 0:
                    code = 3
                encoded = b'{"status":"unavailable","stage":"summary"}\n'
            offset = 0
            while offset < len(encoded):
                written = os.write(output, encoded[offset:])
                if written <= 0:
                    raise OSError("output unavailable")
                offset += written
        except (OSError, ValueError, TypeError):
            if code == 0:
                code = 3
        return code
    finally:
        os.close(output)


def entrypoint() -> int:
    try:
        return main()
    except BaseException:
        return 3


if __name__ == "__main__":
    raise SystemExit(entrypoint())
