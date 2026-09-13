#!/usr/bin/env python3
"""Render a compact, fail-closed Markdown summary for CI timing evidence.

The timing analyzer is intentionally verbose so it can be audited and
reprocessed.  This renderer is the human-facing projection used in the
existing CI finalizer.  It accepts only an analyzer report, validates the
identity and summary shape, escapes API-controlled text, and never turns
missing or pending evidence into a successful claim.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_SKIPPED_JOBS = 200
MAX_JOB_NAME_CHARS = 512
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
VALID_MODES = frozenset({"strict", "diagnostic-lower-bound"})
VALID_STATUSES = frozenset({"queued", "in_progress", "completed"})
TIMING_BUCKETS = ("queue", "setup", "test", "artifact")
OUTCOME_ORDER = (
    "success",
    "failure",
    "cancelled",
    "timed_out",
    "skipped",
    "pending",
    "unknown",
)


class HealthReportError(ValueError):
    """Raised when a report cannot safely support a human-facing summary."""


def _duplicate_key_guard(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise HealthReportError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> object:
    raise HealthReportError(f"non-finite JSON constant {value!r} is not allowed")


def _load_json(path: Path) -> object:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise HealthReportError(f"unable to read report {path}: {error}") from error
    if len(raw) > MAX_INPUT_BYTES:
        raise HealthReportError(
            f"report exceeds maximum size of {MAX_INPUT_BYTES} bytes"
        )
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_duplicate_key_guard,
            parse_constant=_reject_non_finite,
        )
    except HealthReportError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise HealthReportError(f"report contains invalid JSON: {error}") from error


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise HealthReportError(f"{field} must be an object")
    return value


def _non_empty_text(value: object, field: str, *, max_chars: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HealthReportError(f"{field} must be a non-empty string")
    if len(value) > max_chars:
        raise HealthReportError(f"{field} exceeds {max_chars} characters")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise HealthReportError(f"{field} contains a control character")
    return value


def _non_negative_number(
    value: object, field: str, *, allow_none: bool = True
) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HealthReportError(f"{field} must be a non-negative number or null")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise HealthReportError(f"{field} must be a finite non-negative number")
    return number


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HealthReportError(f"{field} must be a non-negative integer")
    return value


def _validate_report_identity(report: Mapping[str, object]) -> tuple[int, str, str]:
    schema_version = report.get("schema_version")
    if schema_version != 1:
        raise HealthReportError("schema_version must be 1")
    run_id = report.get("run_id")
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id <= 0:
        raise HealthReportError("run_id must be a positive integer")
    mode = report.get("analysis_mode")
    if mode not in VALID_MODES:
        raise HealthReportError("analysis_mode is unsupported")
    repository = _non_empty_text(report.get("repository"), "repository")
    provenance = _mapping(report.get("provenance"), "provenance")
    if provenance.get("repository") != repository:
        raise HealthReportError("provenance.repository does not match repository")
    if provenance.get("run_id") != run_id:
        raise HealthReportError("provenance.run_id does not match run_id")
    return run_id, repository, mode


def _validate_report_hash(report: Mapping[str, object]) -> str | None:
    value = report.get("report_sha256")
    if value is None:
        return None
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise HealthReportError("report_sha256 must be a 64-character hex digest")
    body = dict(report)
    body.pop("report_sha256", None)
    canonical = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    expected = hashlib.sha256(canonical).hexdigest()
    if value.lower() != expected:
        raise HealthReportError("report_sha256 does not match report contents")
    return value.lower()


def _validate_timing(summary: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    raw_timing = _mapping(summary.get("timing_seconds"), "summary.timing_seconds")
    timing: dict[str, Mapping[str, object]] = {}
    for bucket in TIMING_BUCKETS:
        values = _mapping(raw_timing.get(bucket), f"summary.timing_seconds.{bucket}")
        count = _non_negative_int(values.get("count"), f"{bucket}.count")
        for metric in ("total_seconds", "p50_seconds", "p95_seconds", "max_seconds"):
            _non_negative_number(values.get(metric), f"{bucket}.{metric}")
        p50 = _non_negative_number(values.get("p50_seconds"), f"{bucket}.p50_seconds")
        p95 = _non_negative_number(values.get("p95_seconds"), f"{bucket}.p95_seconds")
        maximum = _non_negative_number(
            values.get("max_seconds"), f"{bucket}.max_seconds"
        )
        if p50 is not None and p95 is not None and p50 > p95:
            raise HealthReportError(f"{bucket} p50 exceeds p95")
        if p95 is not None and maximum is not None and p95 > maximum:
            raise HealthReportError(f"{bucket} p95 exceeds max")
        if count == 0 and any(metric is not None for metric in (p50, p95, maximum)):
            raise HealthReportError(f"{bucket} has statistics but no samples")
        timing[bucket] = values
    return timing


def _validate_jobs(
    report: Mapping[str, object], expected_count: int
) -> list[Mapping[str, object]]:
    raw_jobs = report.get("jobs")
    if not isinstance(raw_jobs, list):
        raise HealthReportError("jobs must be an array")
    if len(raw_jobs) != expected_count:
        raise HealthReportError("summary.job_count does not match jobs length")
    jobs: list[Mapping[str, object]] = []
    for index, raw_job in enumerate(raw_jobs):
        job = _mapping(raw_job, f"jobs[{index}]")
        _non_empty_text(
            job.get("name"), f"jobs[{index}].name", max_chars=MAX_JOB_NAME_CHARS
        )
        status = job.get("status")
        if status not in VALID_STATUSES:
            raise HealthReportError(f"jobs[{index}].status is unsupported")
        conclusion = job.get("conclusion")
        if conclusion is not None:
            _non_empty_text(conclusion, f"jobs[{index}].conclusion", max_chars=64)
        jobs.append(job)
    return jobs


def _validated_parts(
    report: object,
) -> tuple[
    Mapping[str, object],
    Mapping[str, object],
    list[Mapping[str, object]],
    dict[str, Mapping[str, object]],
    str | None,
]:
    root = _mapping(report, "report")
    _validate_report_identity(root)
    digest = _validate_report_hash(root)
    summary = _mapping(root.get("summary"), "summary")
    job_count = _non_negative_int(summary.get("job_count"), "summary.job_count")
    if job_count <= 0:
        raise HealthReportError("summary.job_count must be positive")
    if summary.get("analysis_mode") != root.get("analysis_mode"):
        raise HealthReportError("summary.analysis_mode does not match report")
    timing = _validate_timing(summary)
    jobs = _validate_jobs(root, job_count)
    return root, summary, jobs, timing, digest


def _outcome(job: Mapping[str, object]) -> str:
    conclusion = job.get("conclusion")
    if isinstance(conclusion, str) and conclusion in OUTCOME_ORDER:
        return conclusion
    if job.get("status") in {"queued", "in_progress"}:
        return "pending"
    return "unknown"


def _safe_cell(value: object) -> str:
    text = "—" if value is None else str(value)
    return html.escape(text.replace("\r", " ").replace("\n", " "), quote=False).replace(
        "|", "\\|"
    )


def _seconds(value: object) -> str:
    number = _non_negative_number(value, "timing value")
    return "—" if number is None else f"{number:.1f}"


def render_report(report: object, *, max_skipped: int = 20) -> str:
    """Validate and render an analyzer report as compact Markdown."""

    if (
        isinstance(max_skipped, bool)
        or not isinstance(max_skipped, int)
        or not (0 <= max_skipped <= MAX_SKIPPED_JOBS)
    ):
        raise HealthReportError(f"max_skipped must be between 0 and {MAX_SKIPPED_JOBS}")
    root, summary, jobs, timing, digest = _validated_parts(report)
    run_id, repository, mode = _validate_report_identity(root)

    outcomes = {outcome: 0 for outcome in OUTCOME_ORDER}
    for job in jobs:
        outcomes[_outcome(job)] += 1
    skipped = [job for job in jobs if _outcome(job) == "skipped"]

    title = "strict" if mode == "strict" else "diagnostic lower bound"
    provenance = _mapping(root.get("provenance"), "provenance")
    source_sha = provenance.get("source_head_sha")
    if not isinstance(source_sha, str) or not source_sha:
        source_sha = "unknown"
    wall_clock = summary.get("wall_clock_seconds")
    peak = summary.get("peak_concurrency")
    cap = root.get("concurrency_cap")
    average = summary.get("average_slot_utilization")

    lines = [
        f"## CI health ({title})",
        "",
        f"- Repository: `{_safe_cell(repository)}`",
        f"- Run: `{run_id}`",
        f"- Source SHA: `{_safe_cell(source_sha)}`",
        f"- Jobs observed: **{len(jobs)}**",
        f"- Wall clock observed: **{_seconds(wall_clock)} s**",
        f"- Peak concurrency: **{_safe_cell(peak)} / {_safe_cell(cap)}**; average slot utilization: **{_safe_cell(average)}**",
        "",
        "| Outcome | Count |",
        "|---|---:|",
    ]
    lines.extend(
        f"| {_safe_cell(outcome)} | {count} |"
        for outcome, count in outcomes.items()
        if count
    )
    lines.extend(
        [
            "",
            "| Timing bucket | Samples | Total (s) | p50 (s) | p95 (s) | Max (s) |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for bucket in TIMING_BUCKETS:
        values = timing[bucket]
        lines.append(
            "| "
            + " | ".join(
                (
                    bucket,
                    _safe_cell(values.get("count")),
                    _seconds(values.get("total_seconds")),
                    _seconds(values.get("p50_seconds")),
                    _seconds(values.get("p95_seconds")),
                    _seconds(values.get("max_seconds")),
                )
            )
            + " |"
        )
    lines.extend(["", "### Skipped jobs", ""])
    if not skipped:
        lines.append("None observed.")
    else:
        for job in skipped[:max_skipped]:
            lines.append(f"- `{_safe_cell(job.get('name'))}`")
        omitted = len(skipped) - min(len(skipped), max_skipped)
        if omitted:
            lines.append(f"- _{omitted} additional skipped jobs omitted._")
    if mode == "diagnostic-lower-bound":
        lines.extend(
            [
                "",
                "> This report is diagnostic-only: API timing is a lower bound and does not prove the dependency DAG or release provenance.",
            ]
        )
    if outcomes["pending"] or outcomes["unknown"]:
        lines.extend(
            [
                "",
                "> **Warning:** pending or unknown outcomes are present; this summary is not a green release signal.",
            ]
        )
    if digest is not None:
        lines.extend(["", f"Report SHA-256: `{digest}`"])
    return "\n".join(lines) + "\n"


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as error:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise HealthReportError(f"unable to write report {path}: {error}") from error


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-skipped", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        report = _load_json(args.input)
        rendered = render_report(report, max_skipped=args.max_skipped)
        _write_atomic(args.output, rendered)
    except (HealthReportError, OSError, UnicodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
