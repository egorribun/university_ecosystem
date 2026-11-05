"""Fail-closed gate for the SQLMap OpenAPI scan (AUD-381).

SQLMap can exit 0 after confirming an injection point or stopping early. This
gate therefore requires all of the following:

* the scan step succeeded (its ``outcome`` is ``success``);
* the console shows a nonempty OpenAPI target set and SQLMap's multi-target
  results message, which is emitted after the target loop, before its ending
  banner (the banner alone is emitted even on interruption);
* the console reports no interrupted or failed targets and proves that every
  input in the admitted operation was tested when no injection was found;
* the output directory holds a result ``log`` and a valid, empty results CSV;
* the scanned application executed a news database query during the scan;
* no output file records a confirmed (or resumed) injection point.

Any missing or unreadable evidence fails closed.
"""

from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import os
import re
import sys
from pathlib import Path

START_MARKER = re.compile(rb"\[\*\] starting @ \S")
END_MARKER = re.compile(rb"\[\*\] ending @ \S")
TARGET_MARKER = re.compile(
    rb"\[INFO\] derived ([0-9]+) target\(s\) from the OpenAPI/Swagger specification"
)
COMPLETION_MARKER = (
    b"[INFO] you can find results of scanning in multiple targets mode "
    b"inside the CSV file 'sqlmap-output/results.csv'"
)
TESTED_PARAMETERS = (
    b"GET parameter 'limit' does not seem to be injectable",
    b"GET parameter 'cursor' does not seem to be injectable",
    b"(custom) HEADER parameter 'if-none-match #1*' does not seem to be injectable",
)
ANSI_ESCAPE = re.compile(rb"\x1b\[[0-?]*[ -/]*[@-~]")
BLOCKING_HTTP_SUMMARY = re.compile(
    rb"\[WARNING\] HTTP error codes detected during run:\s*\r?\n"
    rb"[^\r\n]*\b(?:401|403|429) \("
)
INJECTION_MARKERS = (
    b"identified the following injection point",
    b"resumed the following injection point",
)
RESULT_LOG_NAME = "log"
RESULT_CSV_NAME = "results.csv"
RESULT_CSV_HEADER = ["Target URL", "Place", "Parameter", "Technique(s)", "Note(s)"]
FINDING_PARAMETER_IDS = {
    ("GET", "limit"): "limit",
    ("GET", "cursor"): "cursor",
    ("(custom) HEADER", "if-none-match #1*"): "if-none-match",
}
FINDING_TECHNIQUE_IDS = {"B": "boolean", "E": "error", "U": "union"}
VALID_TECHNIQUE_SETS = frozenset({"B", "E", "U", "BE", "BU", "EU", "BEU"})
QUERY_EVIDENCE_MARKER = b"SQLMAP SELECT news"
STEP_OUTCOMES = frozenset({"success", "failure", "cancelled", "skipped"})
MAX_RECEIPT_COUNT = 1_000_000
INCOMPLETE_WARNINGS = (
    b"user aborted",
    b"skipping OpenAPI operation",
    b"skipping external OpenAPI $ref",
    b"skipping dangling OpenAPI $ref",
    b"the web server responded with an HTTP error code",
)
SCOPE_PATH = "/api/v1/news"
SCOPE_ORIGIN = "http://127.0.0.1:8000"
SCOPE_OPERATION_ID = "news_list_api_v1_news_get"
SCOPE_PARAMETERS = {
    ("query", "limit"),
    ("query", "cursor"),
    ("header", "if-none-match"),
}


class ScanEvidenceError(ValueError):
    """Raised when the SQLMap evidence is missing or does not prove completion."""


def _contains_reference(value: object) -> bool:
    """Reject references in request inputs whose expansion could change the scope."""

    if isinstance(value, dict):
        return "$ref" in value or any(
            _contains_reference(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_reference(item) for item in value)
    return False


def scope_openapi(source: object) -> dict[str, object]:
    """Keep the versioned anonymous news-list operation from the real schema."""

    if not isinstance(source, dict):
        raise ScanEvidenceError("SQLMap's OpenAPI source must be an object")
    version = source.get("openapi")
    if (
        not isinstance(version, str)
        or not re.fullmatch(r"3\.\d+\.\d+", version)
        or "swagger" in source
    ):
        raise ScanEvidenceError("SQLMap requires an unambiguous OpenAPI 3 document")
    paths = source.get("paths")
    path_item = paths.get(SCOPE_PATH) if isinstance(paths, dict) else None
    operation = path_item.get("get") if isinstance(path_item, dict) else None
    parameters = operation.get("parameters") if isinstance(operation, dict) else None
    if not (
        isinstance(path_item, dict)
        and "$ref" not in path_item
        and "parameters" not in path_item
        and isinstance(operation, dict)
        and "$ref" not in operation
        and "requestBody" not in operation
        and operation.get("operationId") == SCOPE_OPERATION_ID
        and isinstance(parameters, list)
        and len(parameters) == len(SCOPE_PARAMETERS)
        and all(
            isinstance(parameter, dict)
            and isinstance(parameter.get("in"), str)
            and isinstance(parameter.get("name"), str)
            and (parameter.get("in"), parameter.get("name")) in SCOPE_PARAMETERS
            for parameter in parameters
        )
        and len({(parameter["in"], parameter["name"]) for parameter in parameters})
        == len(SCOPE_PARAMETERS)
        and not _contains_reference(parameters)
    ):
        raise ScanEvidenceError(
            "SQLMap's admitted OpenAPI operation is missing or changed"
        )
    return {
        "openapi": version,
        "info": {"title": "SQLMap scan scope", "version": "1"},
        "servers": [{"url": SCOPE_ORIGIN}],
        "paths": {
            SCOPE_PATH: {
                "get": {
                    "operationId": SCOPE_OPERATION_ID,
                    "parameters": copy.deepcopy(parameters),
                    "responses": {"200": {"description": "Scoped news list"}},
                }
            }
        },
        "x-sqlmap-scope": {
            "version": 1,
            "operations": [{"method": "GET", "path": SCOPE_PATH}],
        },
    }


def write_scoped_openapi(source_path: Path, output_path: Path) -> int:
    """Write a source-derived scope or fail without creating scan evidence."""

    try:
        source = json.loads(source_path.read_text(encoding="utf-8"))
        scoped = scope_openapi(source)
        output_path.write_text(json.dumps(scoped, ensure_ascii=True), encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as error:
        print(
            f"::error::Could not prepare SQLMap OpenAPI scope: {error}", file=sys.stderr
        )
        return 1
    return 0


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise ScanEvidenceError(
            f"SQLMap evidence is unreadable: {path.name}"
        ) from error


def check_completion(scan_outcome: str, console_log: Path, output_dir: Path) -> bytes:
    """Validate the target-loop completion evidence and return the console log."""

    if scan_outcome != "success":
        raise ScanEvidenceError(
            f"SQLMap scan step did not succeed (outcome: {scan_outcome or 'unknown'})"
        )
    if not console_log.is_file():
        raise ScanEvidenceError("SQLMap produced no console log")
    console = ANSI_ESCAPE.sub(b"", _read_bytes(console_log))
    starts = list(START_MARKER.finditer(console))
    targets = list(TARGET_MARKER.finditer(console))
    ends = list(END_MARKER.finditer(console))
    completion = console.find(COMPLETION_MARKER)
    if not (
        len(starts) == len(targets) == len(ends) == 1
        and int(targets[0].group(1)) == 1
        and starts[0].start() < targets[0].start() < completion < ends[0].start()
        and console.count(COMPLETION_MARKER) == 1
    ):
        raise ScanEvidenceError("SQLMap console log does not prove the run completed")
    for line in console.splitlines():
        if b"[CRITICAL]" in line:
            raise ScanEvidenceError("SQLMap reported a critical scan error")
        if b"[ERROR]" in line:
            message = line.split(b"[ERROR]", 1)[1].strip()
            # SQLMap logs a completed negative test as ERROR in multi-target mode.
            if not (
                message.startswith(
                    b"all tested parameters do not appear to be injectable."
                )
                and message.endswith(b", skipping to the next target")
            ):
                raise ScanEvidenceError("SQLMap reported a failed target")
        if b"[WARNING]" in line and any(
            marker in line for marker in INCOMPLETE_WARNINGS
        ):
            raise ScanEvidenceError("SQLMap reported an incomplete target")
    if BLOCKING_HTTP_SUMMARY.search(console):
        raise ScanEvidenceError("SQLMap requests were blocked or rate-limited")
    if not output_dir.is_dir() or not any(
        path.is_file() and path.name == RESULT_LOG_NAME
        for path in output_dir.rglob("*")
    ):
        raise ScanEvidenceError("SQLMap produced no result log")
    query_log = output_dir / "db-query-evidence.log"
    if not query_log.is_file():
        raise ScanEvidenceError("SQLMap scan produced no database query evidence")
    queries = _read_bytes(query_log).splitlines()
    if not queries or any(query != QUERY_EVIDENCE_MARKER for query in queries):
        raise ScanEvidenceError("SQLMap scan produced no database query evidence")
    return console


def _csv_findings(output_dir: Path) -> list[list[str]]:
    """Validate the native CSV and retain every result, including unconfirmed ones."""

    path = output_dir / RESULT_CSV_NAME
    if not path.is_file():
        raise ScanEvidenceError("SQLMap produced no results CSV")
    try:
        text = _read_bytes(path).decode("utf-8")
        rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except (UnicodeDecodeError, csv.Error) as error:
        raise ScanEvidenceError(
            "SQLMap results CSV is unreadable or malformed"
        ) from error
    if not rows or rows[0] != RESULT_CSV_HEADER:
        raise ScanEvidenceError("SQLMap results CSV has an invalid header")
    if any(len(row) != len(RESULT_CSV_HEADER) for row in rows[1:]):
        raise ScanEvidenceError("SQLMap results CSV has a malformed result")
    return rows[1:]


def csv_finding_count(output_dir: Path) -> int:
    """Count every result row, including unconfirmed results."""

    return len(_csv_findings(output_dir))


def csv_has_findings(output_dir: Path) -> bool:
    """Block every result row, including unconfirmed results."""

    return csv_finding_count(output_dir) > 0


def confirmed_injection_files(output_dir: Path, console_log: Path) -> list[str]:
    """Return the evidence files that record a confirmed or resumed injection."""

    def fail_on_walk_error(error: OSError) -> None:
        raise ScanEvidenceError("SQLMap evidence directory is unreadable") from error

    candidates = [console_log]
    for root, _directories, files in os.walk(output_dir, onerror=fail_on_walk_error):
        candidates.extend(Path(root) / name for name in files)
    flagged: list[str] = []
    for path in sorted(set(candidates)):
        content = ANSI_ESCAPE.sub(b"", _read_bytes(path))
        if any(marker in content for marker in INJECTION_MARKERS):
            flagged.append(path.name)
    return flagged


def _bounded_count(value: int) -> int | None:
    return value if 0 <= value <= MAX_RECEIPT_COUNT else None


def _console_counts(console_log: Path) -> tuple[int | None, int | None]:
    try:
        console = ANSI_ESCAPE.sub(b"", _read_bytes(console_log))
    except ScanEvidenceError:
        return None, None
    targets = list(TARGET_MARKER.finditer(console))
    target_count = None
    if len(targets) == 1 and len(targets[0].group(1)) <= 7:
        target_count = _bounded_count(int(targets[0].group(1)))
    if console.count(COMPLETION_MARKER) != 1:
        return target_count, None
    scan_section = console[: console.index(COMPLETION_MARKER)]
    return target_count, sum(marker in scan_section for marker in TESTED_PARAMETERS)


def _query_count(output_dir: Path) -> int | None:
    try:
        lines = _read_bytes(output_dir / "db-query-evidence.log").splitlines()
    except ScanEvidenceError:
        return None
    if any(line != QUERY_EVIDENCE_MARKER for line in lines):
        return None
    return _bounded_count(len(lines))


def _finding_categories(rows: list[list[str]]) -> tuple[list[str], list[str]]:
    parameters: set[str] = set()
    techniques: set[str] = set()
    for row in rows:
        parameters.add(FINDING_PARAMETER_IDS.get((row[1], row[2]), "unknown"))
        if row[3] in VALID_TECHNIQUE_SETS:
            techniques.update(FINDING_TECHNIQUE_IDS[code] for code in row[3])
        else:
            techniques.add("unknown")
    return sorted(parameters), sorted(techniques)


def publish_evidence(
    output_dir: Path,
    scan_outcome: str,
    gate_outcome: str,
    source_sha: str,
    receipt_path: Path,
) -> int:
    """Publish only source-bound statuses and counts, never native scan content."""

    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        print("::error::Invalid SQLMap evidence source SHA.", file=sys.stderr)
        return 1
    scan = scan_outcome if scan_outcome in STEP_OUTCOMES else "unknown"
    gate = gate_outcome if gate_outcome in STEP_OUTCOMES else "unknown"
    console_log = output_dir / "scan-console.log"
    targets, tested = _console_counts(console_log)
    try:
        findings = _csv_findings(output_dir)
        csv_findings = _bounded_count(len(findings))
        finding_parameters, finding_techniques = _finding_categories(findings)
    except ScanEvidenceError:
        csv_findings = None
        finding_parameters, finding_techniques = None, None
    try:
        confirmed = bool(confirmed_injection_files(output_dir, console_log))
    except ScanEvidenceError:
        confirmed = None
    query_count = _query_count(output_dir)
    claimed_success = scan == gate == "success"
    complete = False
    if claimed_success:
        try:
            console = check_completion(scan, console_log, output_dir)
        except ScanEvidenceError:
            pass
        else:
            targets = 1
            scan_section = console[: console.index(COMPLETION_MARKER)]
            tested = sum(marker in scan_section for marker in TESTED_PARAMETERS)
            if any(marker in console for marker in INJECTION_MARKERS):
                confirmed = True
            complete = True
    verified_success = (
        claimed_success
        and complete
        and targets == 1
        and tested == len(TESTED_PARAMETERS)
        and query_count is not None
        and query_count > 0
        and csv_findings == 0
        and confirmed is False
    )
    receipt = {
        "version": 1,
        "source_sha": source_sha,
        "scope": "anonymous-news-v1",
        "status": "passed" if verified_success else "failed",
        "scan_outcome": scan,
        "gate_outcome": gate,
        "targets": targets,
        "tested_parameters": tested,
        "sqlmap_request_news_selects": query_count,
        "csv_findings": csv_findings,
        "finding_parameters": finding_parameters,
        "finding_techniques": finding_techniques,
        "confirmed_injection": confirmed,
    }
    try:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError:
        print("::error::Could not write SQLMap evidence receipt.", file=sys.stderr)
        return 1
    if claimed_success and not verified_success:
        print("::error::SQLMap success lacks complete evidence.", file=sys.stderr)
        return 1
    return 0


def run_gate(
    scan_outcome: str,
    output_dir: Path,
    console_log: Path,
    summary_path: Path | None,
) -> int:
    try:
        console = check_completion(scan_outcome, console_log, output_dir)
        csv_findings = csv_has_findings(output_dir)
        flagged = confirmed_injection_files(output_dir, console_log)
        scan_section = console[: console.index(COMPLETION_MARKER)]
        if (
            not flagged
            and not csv_findings
            and not all(marker in scan_section for marker in TESTED_PARAMETERS)
        ):
            raise ScanEvidenceError(
                "SQLMap did not report testing every scoped parameter"
            )
    except ScanEvidenceError as error:
        print(f"::error::{error}; the scan result is unknown.", file=sys.stderr)
        return 1

    if summary_path is not None:
        status = (
            "injection evidence"
            if csv_findings and not flagged
            else ("confirmed injection" if flagged else "no confirmed injection")
        )
        with summary_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(
                f"### SQLMap scan\n\nScope v1: anonymous GET {SCOPE_PATH}.\n\n"
                f"Result: {status}. Run completed.\n"
            )

    if flagged:
        print(
            "::error::SQLMap confirmed SQL injection. "
            "Review the sanitized SQLMap evidence receipt.",
            file=sys.stderr,
        )
        return 1
    if csv_findings:
        print(
            "::error::SQLMap results CSV contains injection-related evidence. "
            "Review the sanitized SQLMap evidence receipt.",
            file=sys.stderr,
        )
        return 1
    print("SQLMap completed and reported no confirmed injection points.")
    return 0


def main(argv: list[str] | None = None) -> int:
    raw_arguments = sys.argv[1:] if argv is None else argv
    if raw_arguments[:1] == ["scope-openapi"]:
        scope_parser = argparse.ArgumentParser(description="Build SQLMap OpenAPI scope")
        scope_parser.add_argument("source", type=Path)
        scope_parser.add_argument("output", type=Path)
        scope = scope_parser.parse_args(raw_arguments[1:])
        return write_scoped_openapi(scope.source, scope.output)
    if raw_arguments[:1] == ["publish-evidence"]:
        receipt_parser = argparse.ArgumentParser(description="Publish SQLMap evidence")
        receipt_parser.add_argument("output_dir", type=Path)
        receipt_parser.add_argument("scan_outcome")
        receipt_parser.add_argument("gate_outcome")
        receipt_parser.add_argument("source_sha")
        receipt_parser.add_argument("receipt", type=Path)
        receipt = receipt_parser.parse_args(raw_arguments[1:])
        return publish_evidence(
            receipt.output_dir,
            receipt.scan_outcome,
            receipt.gate_outcome,
            receipt.source_sha,
            receipt.receipt,
        )

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scan-outcome", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--console-log", type=Path, required=True)
    parser.add_argument("--summary-file", type=Path, default=None)
    arguments = parser.parse_args(raw_arguments)
    return run_gate(
        arguments.scan_outcome,
        arguments.output_dir,
        arguments.console_log,
        arguments.summary_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())
