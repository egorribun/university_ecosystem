"""Fail-closed gate for the two blocking SQLMap scans (AUD-381).

The workflow runs two anonymous scans against the disposable backend:

* scope v1: the ``/api/v1/news`` list, which must also prove that the scanned
  application executed the seeded news query;
* scope v2: the complete OpenAPI document, which must test every operation it
  derives.

SQLMap can exit 0 after confirming an injection point or stopping early. For
each scan the gate therefore requires all of the following:

* the scan step succeeded (its ``outcome`` is ``success``);
* the console shows exactly one start marker, one target declaration matching
  the expected target count, SQLMap's multi-target results message and one
  ending banner, in that order (the banner alone is emitted even on
  interruption);
* the console reports no interrupted, timed-out, unreachable or failed targets;
* the output directory holds a result ``log`` and a valid, empty results CSV;
* no output file records a confirmed (or resumed) injection point.

The news scan additionally requires the seeded news query evidence and every
admitted parameter's negative result. The OpenAPI scan requires one negative
result per derived operation. Any missing or unreadable evidence fails closed.
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
from urllib.parse import urlsplit

START_MARKER = re.compile(rb"\[\*\] starting @ \S")
END_MARKER = re.compile(rb"\[\*\] ending @ \S")
TARGET_MARKER = re.compile(
    rb"\[INFO\] derived ([0-9]+) target\(s\) from the OpenAPI/Swagger specification"
)
TESTING_URL_MARKER = re.compile(rb"testing URL '([^']+)'")
PER_RESPONSE_HTTP_ERROR = re.compile(
    rb"the web server responded with an HTTP error code \(([0-9]{3})\)"
)
HTTP_ERROR_SUMMARY = re.compile(
    rb"\[WARNING\] HTTP error codes detected during run:\r?\n([^\r\n]*)"
)
HTTP_ERROR_SUMMARY_ENTRY = re.compile(rb"([0-9]{3}) \([^)]*\) - [0-9]+ times")
# Quoted text (target URLs, option values) and bare URLs are not message text.
MESSAGE_TEXT_ONLY_STRIP = re.compile(rb"'[^']*'|https?://\S+")
# Anonymous answers that are correct for a probe of a protected or absent
# operation: 401/403 protected, 404 absent, 405 method not allowed, 422 probe
# values that fail validation. Passed as --ignore-code on the full scan only.
FULL_SCAN_IGNORED_CODES = frozenset({401, 403, 404, 405, 422})
# Reviewed exception: /healthz answers 503 on the disposable stand because its
# SpiceDB subsystem is not running (the reviewed readiness route /health/ready
# returns 200). No other target may produce a 503.
FULL_SCAN_PATH_CODES = {"/healthz": frozenset({503})}
# Reviewed exception (owner decision 2026-11-08): this operation answers 204 with
# no body, so SQLMap's stability check cannot run and it tests no parameter. Its
# handler only logs and counts, with no database access, which
# tests/test_sqlmap_scan_gate.py enforces against the handler source.
FULL_SCAN_UNTESTABLE_PATHS = frozenset({"/api/v1/csp-report"})
UNTESTABLE_STABILITY_ERROR = (
    b"there was an error checking the stability of page because of lack of content."
)
RESULTS_MARKER_PREFIX = (
    b"[INFO] you can find results of scanning in multiple targets mode "
    b"inside the CSV file '"
)
OPENAPI_OUTPUT_DIR = "sqlmap-openapi-output"
SCOPED_OPENAPI_NAME = "scoped-openapi.json"
COMPLETION_MARKER = RESULTS_MARKER_PREFIX + b"sqlmap-output/results.csv'"
OPENAPI_COMPLETION_MARKER = (
    RESULTS_MARKER_PREFIX + f"{OPENAPI_OUTPUT_DIR}/results.csv'".encode("ascii")
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
MAX_DECLARED_TARGET_DIGITS = 7
INCOMPLETE_WARNINGS = (
    b"user aborted",
    b"skipping OpenAPI operation",
    b"skipping external OpenAPI $ref",
    b"skipping dangling OpenAPI $ref",
    b"the web server responded with an HTTP error code",
    b"time out",
    b"timed out",
    b"timeout",
    b"time-out",
    b"retry",
    b"unable to connect",
    b"connection refused",
)
NEGATIVE_RESULT_START = b"all tested parameters do not appear to be injectable."
NEGATIVE_RESULT_END = b", skipping to the next target"
HTTP_OPERATION_METHODS = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
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


def _contains_external_reference(value: object) -> bool:
    """Reject any reference that does not resolve inside the same document."""

    if isinstance(value, dict):
        if "$ref" in value:
            reference = value["$ref"]
            if not (isinstance(reference, str) and reference.startswith("#/")):
                return True
        return any(_contains_external_reference(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_external_reference(item) for item in value)
    return False


def _require_openapi_three(source: dict[str, object]) -> str:
    """Return the OpenAPI 3 version, rejecting Swagger or ambiguous documents."""

    version = source.get("openapi")
    if (
        not isinstance(version, str)
        or not re.fullmatch(r"3\.\d+\.\d+", version)
        or "swagger" in source
    ):
        raise ScanEvidenceError("SQLMap requires an unambiguous OpenAPI 3 document")
    return version


def scope_openapi(source: object) -> dict[str, object]:
    """Keep the versioned anonymous news-list operation from the real schema."""

    if not isinstance(source, dict):
        raise ScanEvidenceError("SQLMap's OpenAPI source must be an object")
    version = _require_openapi_three(source)
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


def scope_full_openapi(source: object) -> dict[str, object]:
    """Keep every operation of the real schema, pinned to the disposable origin."""

    if not isinstance(source, dict):
        raise ScanEvidenceError("SQLMap's OpenAPI source must be an object")
    version = _require_openapi_three(source)
    paths = source.get("paths")
    components = source.get("components", {})
    if not isinstance(paths, dict) or not isinstance(components, dict):
        raise ScanEvidenceError("SQLMap's OpenAPI source has malformed sections")
    scoped_paths: dict[str, object] = {}
    for path, item in paths.items():
        if not (
            isinstance(path, str)
            and path.startswith("/")
            and not path.startswith("//")
            and "\\" not in path
            and "?" not in path
            and "#" not in path
            and isinstance(item, dict)
            and "$ref" not in item
        ):
            raise ScanEvidenceError("SQLMap's OpenAPI path items must be inline")
        scoped_item: dict[str, object] = {}
        for key, value in item.items():
            if key in HTTP_OPERATION_METHODS:
                if not isinstance(value, dict):
                    raise ScanEvidenceError("SQLMap's OpenAPI operation is malformed")
                scoped_item[key] = {
                    name: copy.deepcopy(member)
                    for name, member in value.items()
                    # Destination overrides can redirect scanning off the loopback.
                    if name not in {"servers", "callbacks"}
                }
            elif key == "parameters":
                scoped_item[key] = copy.deepcopy(value)
        scoped_paths[path] = scoped_item
    if count_operations(scoped_paths) == 0:
        raise ScanEvidenceError("SQLMap's OpenAPI source declares no operations")
    if _contains_external_reference(scoped_paths) or _contains_external_reference(
        components
    ):
        raise ScanEvidenceError("SQLMap's OpenAPI source has an external reference")
    return {
        "openapi": version,
        "info": {"title": "SQLMap full scan scope", "version": "2"},
        "servers": [{"url": SCOPE_ORIGIN}],
        "paths": scoped_paths,
        "components": copy.deepcopy(components),
        "x-sqlmap-scope": {"version": 2},
    }


def count_operations(paths: dict[object, object]) -> int:
    """Count HTTP operations in a path map."""

    return sum(
        1
        for item in paths.values()
        if isinstance(item, dict)
        for method in item
        if method in HTTP_OPERATION_METHODS
    )


def count_scoped_operations(path: Path) -> int:
    """Return how many operations the workflow handed to SQLMap."""

    try:
        document = json.loads(_read_bytes(path).decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise ScanEvidenceError(
            "SQLMap scoped OpenAPI document is unreadable"
        ) from error
    paths = document.get("paths") if isinstance(document, dict) else None
    if not isinstance(paths, dict):
        raise ScanEvidenceError("SQLMap scoped OpenAPI document has no paths")
    return count_operations(paths)


def _write_scope(source_path: Path, output_path: Path, build) -> int:
    """Write a source-derived scope or fail without creating scan evidence."""

    try:
        source = json.loads(source_path.read_text(encoding="utf-8"))
        scoped = build(source)
        output_path.write_text(json.dumps(scoped, ensure_ascii=True), encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as error:
        print(
            f"::error::Could not prepare SQLMap OpenAPI scope: {error}", file=sys.stderr
        )
        return 1
    return 0


def write_scoped_openapi(source_path: Path, output_path: Path) -> int:
    """Write the news-only scope (scope v1)."""

    return _write_scope(source_path, output_path, scope_openapi)


def write_full_scope(source_path: Path, output_path: Path) -> int:
    """Write the complete-document scope (scope v2)."""

    return _write_scope(source_path, output_path, scope_full_openapi)


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise ScanEvidenceError(
            f"SQLMap evidence is unreadable: {path.name}"
        ) from error


def _is_negative_result(line: bytes) -> bool:
    """SQLMap logs a completed negative target as ERROR in multi-target mode."""

    message = line.split(b"[ERROR]", 1)[1].strip()
    return message.startswith(NEGATIVE_RESULT_START) and message.endswith(
        NEGATIVE_RESULT_END
    )


def _declared_targets(console: bytes) -> int | None:
    """Return the single declared target count, or None when it is ambiguous."""

    targets = list(TARGET_MARKER.finditer(console))
    if len(targets) != 1 or len(targets[0].group(1)) > MAX_DECLARED_TARGET_DIGITS:
        return None
    return int(targets[0].group(1))


def _validate_target_loop(
    scan_outcome: str,
    console_log: Path,
    output_dir: Path,
    *,
    completion_marker: bytes,
    expected_targets: int,
) -> bytes:
    """Validate the shared target-loop evidence and return the console log."""

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
    completion = console.find(completion_marker)
    if not (
        len(starts) == len(targets) == len(ends) == 1
        and _declared_targets(console) == expected_targets
        and starts[0].start() < targets[0].start() < completion < ends[0].start()
        and console.count(completion_marker) == 1
    ):
        raise ScanEvidenceError("SQLMap console log does not prove the run completed")
    for line in console.splitlines():
        if b"[CRITICAL]" in line:
            raise ScanEvidenceError("SQLMap reported a critical scan error")
        if b"[ERROR]" in line and not _is_negative_result(line):
            raise ScanEvidenceError("SQLMap reported a failed target")
        lowered = line.lower()
        if any(marker.lower() in lowered for marker in INCOMPLETE_WARNINGS):
            raise ScanEvidenceError("SQLMap reported an incomplete target")
    if BLOCKING_HTTP_SUMMARY.search(console):
        raise ScanEvidenceError("SQLMap requests were blocked or rate-limited")
    if not output_dir.is_dir() or not any(
        path.is_file() and path.name == RESULT_LOG_NAME
        for path in output_dir.rglob("*")
    ):
        raise ScanEvidenceError("SQLMap produced no result log")
    return console


def check_completion(scan_outcome: str, console_log: Path, output_dir: Path) -> bytes:
    """Validate the news scan's completion and seeded query evidence."""

    console = _validate_target_loop(
        scan_outcome,
        console_log,
        output_dir,
        completion_marker=COMPLETION_MARKER,
        expected_targets=1,
    )
    query_log = output_dir / "db-query-evidence.log"
    if not query_log.is_file():
        raise ScanEvidenceError("SQLMap scan produced no database query evidence")
    queries = _read_bytes(query_log).splitlines()
    if not queries or any(query != QUERY_EVIDENCE_MARKER for query in queries):
        raise ScanEvidenceError("SQLMap scan produced no database query evidence")
    return console


def _is_untestable_stability_error(line: bytes) -> bool:
    """Match only the exact stability error for an operation with an empty answer."""

    message = line.split(b"[ERROR]", 1)[1].strip()
    return message.startswith(UNTESTABLE_STABILITY_ERROR)


def _full_scan_allowed_codes(url: bytes) -> frozenset[int]:
    """Codes a target may return: the anonymous answers plus its reviewed ones."""

    path = urlsplit(url.decode("ascii", "replace")).path
    return FULL_SCAN_IGNORED_CODES | FULL_SCAN_PATH_CODES.get(path, frozenset())


def _validate_full_scan_targets(console: bytes, operations: int) -> None:
    """Bind every operation to its own block: one testing URL, one negative.

    SQLMap 1.10.10 in --batch mode prints "testing URL" per target and no
    indexed header, so the target block is the unit of proof. HTTP error codes
    are judged per block: sqlmap resets its counters for each target, so the
    summary printed at the end of a block belongs to that block alone.
    """

    if b"[CRITICAL]" in console:
        raise ScanEvidenceError("SQLMap reported a critical scan error")
    completion = console.index(OPENAPI_COMPLETION_MARKER)
    targets = list(TARGET_MARKER.finditer(console))
    blocks: list[tuple[bytes, bytes]] = []
    matches = list(TESTING_URL_MARKER.finditer(console, targets[0].end(), completion))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else completion
        blocks.append((match.group(1), console[match.end() : end]))
    if len(blocks) != operations:
        raise ScanEvidenceError("SQLMap did not test every scoped OpenAPI operation")
    block_codes = 0
    block_summaries = 0
    reviewed_errors = 0
    for url, body in blocks:
        path = urlsplit(url.decode("ascii", "replace")).path
        for line in body.splitlines():
            if b"[ERROR]" in line and not _is_negative_result(line):
                if path in FULL_SCAN_UNTESTABLE_PATHS and (
                    _is_untestable_stability_error(line)
                ):
                    reviewed_errors += 1
                    continue
                raise ScanEvidenceError(
                    f"SQLMap reported a failed OpenAPI target at {path}"
                )
        negatives = sum(
            1
            for line in body.splitlines()
            if b"[ERROR]" in line and _is_negative_result(line)
        )
        if negatives != 1:
            raise ScanEvidenceError(
                f"SQLMap did not complete exactly one negative result at {path}"
            )
        allowed = _full_scan_allowed_codes(url)
        for match in PER_RESPONSE_HTTP_ERROR.finditer(body):
            block_codes += 1
            if int(match.group(1)) not in allowed:
                raise ScanEvidenceError(
                    f"SQLMap received HTTP {int(match.group(1))} at {path}"
                )
        for match in HTTP_ERROR_SUMMARY.finditer(body):
            block_summaries += 1
            for entry in HTTP_ERROR_SUMMARY_ENTRY.finditer(match.group(1)):
                if int(entry.group(1)) not in allowed:
                    raise ScanEvidenceError(
                        f"SQLMap received HTTP {int(entry.group(1))} at {path}"
                    )
    for line in console.splitlines():
        if b"[ERROR]" in line and not _is_negative_result(line):
            # Each reviewed line was attributed to its own target block above.
            if reviewed_errors and _is_untestable_stability_error(line):
                reviewed_errors -= 1
                continue
            raise ScanEvidenceError("SQLMap reported a failed OpenAPI target")
        # HTTP error lines are judged per target above, not as incomplete words.
        if PER_RESPONSE_HTTP_ERROR.search(line) or HTTP_ERROR_SUMMARY.search(line):
            continue
        message = MESSAGE_TEXT_ONLY_STRIP.sub(b"", line).lower()
        if any(marker.lower() in message for marker in INCOMPLETE_WARNINGS):
            raise ScanEvidenceError("SQLMap reported an incomplete target")
    # Any HTTP error line outside a target block would escape the per-block rule.
    if (
        len(PER_RESPONSE_HTTP_ERROR.findall(console)) != block_codes
        or len(HTTP_ERROR_SUMMARY.findall(console)) != block_summaries
    ):
        raise ScanEvidenceError("SQLMap reported HTTP errors outside a target")


def check_openapi_completion(
    scan_outcome: str, console_log: Path, output_dir: Path
) -> tuple[bytes, int]:
    """Validate that every derived OpenAPI operation completed a negative result."""

    operations = count_scoped_operations(output_dir / SCOPED_OPENAPI_NAME)
    if operations == 0:
        raise ScanEvidenceError("SQLMap OpenAPI scope declares no operations")
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
    completion = console.find(OPENAPI_COMPLETION_MARKER)
    if not (
        len(starts) == len(targets) == len(ends) == 1
        and _declared_targets(console) == operations
        and starts[0].start() < targets[0].start() < completion < ends[0].start()
        and console.count(OPENAPI_COMPLETION_MARKER) == 1
    ):
        raise ScanEvidenceError("SQLMap console log does not prove the run completed")
    if not output_dir.is_dir() or not any(
        path.is_file() and path.name == RESULT_LOG_NAME
        for path in output_dir.rglob("*")
    ):
        raise ScanEvidenceError("SQLMap produced no result log")
    _validate_full_scan_targets(console, operations)
    return console, operations


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
    target_count = _declared_targets(console)
    if target_count is not None:
        target_count = _bounded_count(target_count)
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


def _openapi_receipt(
    output_dir: Path | None, scan_outcome: str, gate_outcome: str
) -> tuple[dict[str, object], bool]:
    """Summarize the full-document scan as counts only and report whether it passed."""

    scan = scan_outcome if scan_outcome in STEP_OUTCOMES else "unknown"
    receipt: dict[str, object] = {
        "scope": "anonymous-openapi-v2",
        "scan_outcome": scan,
        "gate_outcome": gate_outcome if gate_outcome in STEP_OUTCOMES else "unknown",
        "operations": None,
        "targets": None,
        "negative_results": None,
        "csv_findings": None,
        "confirmed_injection": None,
    }
    if output_dir is None:
        receipt["status"] = "failed"
        return receipt, False
    console_log = output_dir / "scan-console.log"
    try:
        receipt["operations"] = _bounded_count(
            count_scoped_operations(output_dir / SCOPED_OPENAPI_NAME)
        )
    except ScanEvidenceError:
        pass
    try:
        receipt["csv_findings"] = _bounded_count(csv_finding_count(output_dir))
    except ScanEvidenceError:
        pass
    try:
        receipt["confirmed_injection"] = bool(
            confirmed_injection_files(output_dir, console_log)
        )
    except ScanEvidenceError:
        pass
    verified = False
    if scan == gate_outcome == "success":
        try:
            console, operations = check_openapi_completion(
                scan, console_log, output_dir
            )
        except ScanEvidenceError:
            pass
        else:
            receipt["targets"] = operations
            receipt["negative_results"] = operations
            if any(marker in console for marker in INJECTION_MARKERS):
                receipt["confirmed_injection"] = True
            verified = (
                receipt["csv_findings"] == 0 and receipt["confirmed_injection"] is False
            )
    receipt["status"] = "passed" if verified else "failed"
    return receipt, verified


def publish_evidence(
    output_dir: Path,
    scan_outcome: str,
    gate_outcome: str,
    source_sha: str,
    receipt_path: Path,
    openapi_output_dir: Path | None = None,
    openapi_scan_outcome: str = "skipped",
    openapi_gate_outcome: str | None = None,
) -> int:
    """Publish only source-bound statuses and counts, never native scan content."""

    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        print("::error::Invalid SQLMap evidence source SHA.", file=sys.stderr)
        return 1
    scan = scan_outcome if scan_outcome in STEP_OUTCOMES else "unknown"
    gate = gate_outcome if gate_outcome in STEP_OUTCOMES else "unknown"
    openapi_gate = (
        openapi_gate_outcome
        if openapi_gate_outcome in STEP_OUTCOMES
        else (gate if openapi_gate_outcome is None else "unknown")
    )
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
    news_verified = (
        claimed_success
        and complete
        and targets == 1
        and tested == len(TESTED_PARAMETERS)
        and query_count is not None
        and query_count > 0
        and csv_findings == 0
        and confirmed is False
    )
    openapi_receipt, openapi_verified = _openapi_receipt(
        openapi_output_dir, openapi_scan_outcome, openapi_gate
    )
    openapi_claimed = openapi_scan_outcome == "success" and openapi_gate == "success"
    verified_success = news_verified and openapi_verified
    receipt = {
        "version": 2,
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
        "openapi": openapi_receipt,
    }
    try:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError:
        print("::error::Could not write SQLMap evidence receipt.", file=sys.stderr)
        return 1
    if (claimed_success and not news_verified) or (
        openapi_claimed and not openapi_verified
    ):
        print("::error::SQLMap success lacks complete evidence.", file=sys.stderr)
        return 1
    return 0


def _summary(summary_path: Path | None, section: str) -> None:
    if summary_path is None:
        return
    with summary_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(section)


def run_gate(
    scan_outcome: str,
    output_dir: Path,
    console_log: Path,
    summary_path: Path | None,
) -> int:
    """Gate the news scan (scope v1)."""

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

    status = (
        "injection evidence"
        if csv_findings and not flagged
        else ("confirmed injection" if flagged else "no confirmed injection")
    )
    _summary(
        summary_path,
        f"### SQLMap scan\n\nScope v1: anonymous GET {SCOPE_PATH}.\n\n"
        f"Result: {status}. Run completed.\n",
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


def run_openapi_gate(
    scan_outcome: str,
    output_dir: Path,
    console_log: Path,
    summary_path: Path | None,
) -> int:
    """Gate the complete-document scan (scope v2)."""

    try:
        _console, operations = check_openapi_completion(
            scan_outcome, console_log, output_dir
        )
        csv_findings = csv_has_findings(output_dir)
        flagged = confirmed_injection_files(output_dir, console_log)
    except ScanEvidenceError as error:
        print(f"::error::{error}; the OpenAPI scan result is unknown.", file=sys.stderr)
        return 1

    status = (
        "confirmed injection"
        if flagged
        else ("injection evidence" if csv_findings else "no confirmed injection")
    )
    _summary(
        summary_path,
        f"### SQLMap OpenAPI scan\n\nScope v2: anonymous complete OpenAPI document, "
        f"{operations} operation(s).\n\nResult: {status}. Run completed.\n",
    )
    if flagged:
        print(
            "::error::SQLMap confirmed SQL injection in the OpenAPI scan. "
            "Review the sanitized SQLMap evidence receipt.",
            file=sys.stderr,
        )
        return 1
    if csv_findings:
        print(
            "::error::SQLMap OpenAPI results CSV contains injection-related evidence. "
            "Review the sanitized SQLMap evidence receipt.",
            file=sys.stderr,
        )
        return 1
    print(
        "SQLMap OpenAPI scan tested every operation and reported no confirmed "
        "injection points."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    raw_arguments = sys.argv[1:] if argv is None else argv
    if raw_arguments[:1] == ["scope-openapi"]:
        scope_parser = argparse.ArgumentParser(description="Build SQLMap OpenAPI scope")
        scope_parser.add_argument("source", type=Path)
        scope_parser.add_argument("output", type=Path)
        scope = scope_parser.parse_args(raw_arguments[1:])
        return write_scoped_openapi(scope.source, scope.output)
    if raw_arguments[:1] == ["scope-full-openapi"]:
        full_parser = argparse.ArgumentParser(
            description="Build the complete SQLMap OpenAPI scope"
        )
        full_parser.add_argument("source", type=Path)
        full_parser.add_argument("output", type=Path)
        full = full_parser.parse_args(raw_arguments[1:])
        return write_full_scope(full.source, full.output)
    if raw_arguments[:1] == ["publish-evidence"]:
        receipt_parser = argparse.ArgumentParser(description="Publish SQLMap evidence")
        receipt_parser.add_argument("output_dir", type=Path)
        receipt_parser.add_argument("scan_outcome")
        receipt_parser.add_argument("gate_outcome")
        receipt_parser.add_argument("source_sha")
        receipt_parser.add_argument("receipt", type=Path)
        receipt_parser.add_argument("--openapi-output-dir", type=Path, default=None)
        receipt_parser.add_argument("--openapi-scan-outcome", default="skipped")
        receipt_parser.add_argument("--openapi-gate-outcome", default=None)
        receipt = receipt_parser.parse_args(raw_arguments[1:])
        return publish_evidence(
            receipt.output_dir,
            receipt.scan_outcome,
            receipt.gate_outcome,
            receipt.source_sha,
            receipt.receipt,
            receipt.openapi_output_dir,
            receipt.openapi_scan_outcome,
            receipt.openapi_gate_outcome,
        )

    if raw_arguments[:1] == ["gate-news"]:
        news_parser = argparse.ArgumentParser(description="Gate the seeded news scan")
        news_parser.add_argument("--scan-outcome", required=True)
        news_parser.add_argument("--output-dir", type=Path, required=True)
        news_parser.add_argument("--console-log", type=Path, required=True)
        news_parser.add_argument("--summary-file", type=Path, default=None)
        news = news_parser.parse_args(raw_arguments[1:])
        return run_gate(
            news.scan_outcome,
            news.output_dir,
            news.console_log,
            news.summary_file,
        )

    if raw_arguments[:1] == ["gate-openapi"]:
        openapi_parser = argparse.ArgumentParser(
            description="Gate the complete anonymous OpenAPI scan"
        )
        openapi_parser.add_argument("--scan-outcome", required=True)
        openapi_parser.add_argument("--output-dir", type=Path, required=True)
        openapi_parser.add_argument("--console-log", type=Path, required=True)
        openapi_parser.add_argument("--summary-file", type=Path, default=None)
        openapi = openapi_parser.parse_args(raw_arguments[1:])
        return run_openapi_gate(
            openapi.scan_outcome,
            openapi.output_dir,
            openapi.console_log,
            openapi.summary_file,
        )

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scan-outcome", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--console-log", type=Path, required=True)
    parser.add_argument("--openapi-scan-outcome", required=True)
    parser.add_argument("--openapi-output-dir", type=Path, required=True)
    parser.add_argument("--openapi-console-log", type=Path, required=True)
    parser.add_argument("--summary-file", type=Path, default=None)
    arguments = parser.parse_args(raw_arguments)
    news_status = run_gate(
        arguments.scan_outcome,
        arguments.output_dir,
        arguments.console_log,
        arguments.summary_file,
    )
    openapi_status = run_openapi_gate(
        arguments.openapi_scan_outcome,
        arguments.openapi_output_dir,
        arguments.openapi_console_log,
        arguments.summary_file,
    )
    return 1 if news_status or openapi_status else 0


if __name__ == "__main__":
    raise SystemExit(main())
