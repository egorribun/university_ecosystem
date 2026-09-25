"""Fail-closed tests for the compact CI health report renderer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from scripts.quality.analyze_ci_critical_path import analyze_jobs, parse_jobs
from scripts.quality.render_ci_health_report import (
    HealthReportError,
    main,
    render_report,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "quality" / "github-actions-jobs.json"


def _diagnostic_report() -> dict[str, object]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    records = payload["jobs"]
    assert isinstance(records, list)
    for record in records:
        assert isinstance(record, dict)
        record.update(
            run_id=42,
            run_attempt=1,
            head_sha="a" * 40,
        )
    return cast(
        dict[str, object],
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=42,
            concurrency_cap=20,
            diagnostic_lower_bound=True,
        ),
    )


def test_render_report_includes_safe_summary_and_timing_table() -> None:
    report = _diagnostic_report()

    rendered = render_report(report)

    assert "## CI health (diagnostic lower bound)" in rendered
    assert "Run: `42`" in rendered
    assert "Jobs observed: **3**" in rendered
    assert "| queue | 2 | 120.0 | 30.0 | 90.0 | 90.0 |" in rendered
    assert "| success | 1 |" in rendered
    assert "| failure | 1 |" in rendered
    assert "### Retry and timeout reasons" in rendered
    assert "| retry | initial_workflow_attempt | 3 |" in rendered
    assert "| timeout | not_timed_out | 3 |" in rendered
    assert "### Runner resource telemetry" in rendered
    assert "CPU seconds: **—**" in rendered
    assert "Peak RSS bytes: **—**" in rendered
    assert "This report is diagnostic-only" in rendered


def test_render_report_escapes_untrusted_job_names_and_lists_skips() -> None:
    report = _diagnostic_report()
    jobs = cast(list[dict[str, object]], report["jobs"])
    jobs[2]["name"] = "bad|name<script>"

    rendered = render_report(report)

    assert "bad\\|name&lt;script&gt;" in rendered
    assert "| skipped | 1 |" in rendered
    assert "condition_not_exposed_by_jobs_api" in rendered
    assert "Skipped jobs" in rendered


def test_cli_writes_report_and_rejects_tampered_digest(tmp_path: Path) -> None:
    report = _diagnostic_report()
    canonical = json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    report["report_sha256"] = hashlib.sha256(canonical).hexdigest()
    source = tmp_path / "health.json"
    destination = tmp_path / "health.md"
    source.write_text(json.dumps(report), encoding="utf-8")

    assert main(["--input", str(source), "--output", str(destination)]) == 0
    assert "Report SHA-256:" in destination.read_text(encoding="utf-8")

    report["summary"]["job_count"] = 99  # type: ignore[index]
    source.write_text(json.dumps(report), encoding="utf-8")
    assert main(["--input", str(source), "--output", str(destination)]) == 1


def test_cli_rejects_analyzer_report_without_digest(tmp_path: Path) -> None:
    report = _diagnostic_report()
    source = tmp_path / "health.json"
    destination = tmp_path / "health.md"
    source.write_text(json.dumps(report), encoding="utf-8")

    assert main(["--input", str(source), "--output", str(destination)]) == 1
    assert not destination.exists()


@pytest.mark.parametrize(
    "mutator",
    [
        lambda report: report.pop("summary"),
        lambda report: cast(dict[str, object], report["summary"]).pop("timing_seconds"),
        lambda report: cast(dict[str, object], report["summary"]).__setitem__(
            "job_count", 0
        ),
    ],
)
def test_render_report_rejects_incomplete_or_invalid_evidence(mutator) -> None:
    report = _diagnostic_report()
    mutator(report)

    with pytest.raises(HealthReportError):
        render_report(report)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda report: cast(dict[str, object], report["summary"])[
            "resource_usage"
        ].__setitem__("status", "unsupported-but-measured"),
        lambda report: cast(dict[str, object], report["summary"])[
            "resource_usage"
        ].__setitem__("status", []),
        lambda report: cast(dict[str, object], report["summary"])[
            "resource_usage"
        ].__setitem__("cpu_seconds", 1.0),
        lambda report: cast(list[dict[str, object]], report["jobs"])[0].__setitem__(
            "timeout_reason", "guessed_from_duration"
        ),
        lambda report: cast(list[dict[str, object]], report["jobs"])[0].__setitem__(
            "retry_reason", []
        ),
        lambda report: cast(list[dict[str, object]], report["jobs"])[2].__setitem__(
            "skip_reason", None
        ),
    ],
)
def test_render_report_rejects_untrusted_reason_or_resource_claims(mutator) -> None:
    report = _diagnostic_report()
    mutator(report)

    with pytest.raises(HealthReportError):
        render_report(report)
