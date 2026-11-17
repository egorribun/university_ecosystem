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


def _contradictory_report(*, strict=False):
    payload = {
        "jobs": [
            {
                "id": 7,
                "run_id": 42,
                "run_attempt": 1,
                "head_sha": "a" * 40,
                "name": "unexecuted",
                "status": "completed",
                "conclusion": "skipped",
                "created_at": "2026-11-17T01:39:10Z",
                "started_at": "2026-11-17T01:39:10Z",
                "completed_at": "2020-01-01T00:00:00Z",
                "steps": [],
                "runner_id": None,
                "runner_name": None,
                "labels": [],
            }
        ]
    }
    dag = {
        "schema_version": 1,
        "repository": "egorribun/university_ecosystem",
        "run_id": 42,
        "run_attempt": 1,
        "source_head_sha": "a" * 40,
        "tested_commit_sha": "b" * 40,
        "workflow_path": ".github/workflows/ci.yml",
        "workflow_ref": "egorribun/university_ecosystem/.github/workflows/ci.yml@refs/pull/1/merge",
        "workflow_sha": "c" * 40,
        "workflow_files_sha256": {".github/workflows/ci.yml": "d" * 64},
        "nodes": [
            {
                "job_id": 7,
                "logical_id": "unexecuted",
                "needs": [],
                "phase": "test",
                "core_role": "required",
                "skip_classification": "ordinary",
                "core_failure": False,
            }
        ],
    }
    dag["dag_sha256"] = hashlib.sha256(
        json.dumps(dag, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    trusted = {
        "selector": "select_same_run_artifact_cli",
        "repository": dag["repository"],
        "run_id": 42,
        "run_attempt": 1,
        "source_head_sha": dag["source_head_sha"],
        "tested_commit_sha": dag["tested_commit_sha"],
        "workflow_path": dag["workflow_path"],
        "workflow_ref": dag["workflow_ref"],
        "workflow_sha": dag["workflow_sha"],
        "workflow_files_sha256": dag["workflow_files_sha256"],
        "dag_sha256": dag["dag_sha256"],
        "artifact_id": 1,
        "artifact_name": "ci-critical-path-42-1",
        "artifact_digest": "e" * 64,
        "producer_attempt": 1,
    }
    return analyze_jobs(
        parse_jobs(payload),
        repository="egorribun/university_ecosystem",
        run_id=42,
        concurrency_cap=20,
        diagnostic_lower_bound=not strict,
        dag=dag if strict else None,
        trusted_provenance=trusted if strict else None,
    )


@pytest.mark.parametrize("strict", [False, True])
def test_contradictory_timing_caveat_cannot_be_hidden_by_skip_limit(strict):
    report = _contradictory_report(strict=strict)
    rendered = render_report(report, max_skipped=0)
    assert "Timing certification unavailable" in rendered
    assert "Affected job IDs: 7" in rendered
    assert "not measured elapsed time" in rendered
    assert "valid execution intervals only" in rendered
    assert "Wall clock observed: **— s**" in rendered
    assert ("CI health (strict)" if strict else "diagnostic lower bound") in rendered


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-summary",
        "missing-marker",
        "wrong-ids",
        "duplicate-ids",
        "boolean-id",
        "zero-id",
        "exact-path",
        "certified",
        "measured-duration",
        "measured-work-cost",
        "missing-validity",
        "invented-kind",
        "raw-time",
    ],
)
@pytest.mark.parametrize("strict", [False, True])
def test_renderer_rejects_inconsistent_timing_integrity(mutation, strict):
    report = _contradictory_report(strict=strict)
    summary = report["summary"]
    row = report["jobs"][0]
    integrity = summary["timing_integrity"]
    if mutation == "missing-summary":
        del summary["timing_integrity"]
    elif mutation == "missing-marker":
        del row["github_timing_evidence"]
    elif mutation == "wrong-ids":
        integrity["affected_job_ids"] = [8]
    elif mutation == "duplicate-ids":
        integrity["affected_job_ids"] = [7, 7]
    elif mutation == "boolean-id":
        integrity["affected_job_ids"] = [True]
    elif mutation == "zero-id":
        row["id"] = 0
        integrity["affected_job_ids"] = [0]
    elif mutation == "exact-path":
        summary["critical_path_kind"] = "exact"
    elif mutation == "certified":
        integrity["certification"] = "available"
    elif mutation == "measured-duration":
        row["duration_seconds"] = 0
    elif mutation == "measured-work-cost":
        row["dependency_work_cost_seconds"] = 1
    elif mutation == "missing-validity":
        del row["github_timing_evidence"]["timing_validity"]
    elif mutation == "invented-kind":
        row["github_timing_evidence"]["kind"] = "unknown"
    else:
        row["github_timing_evidence"]["completed_at"] = "invalid"
    with pytest.raises(HealthReportError):
        render_report(report, max_skipped=0)


def test_renderer_rejects_duplicate_row_identity_with_integrity():
    report = _contradictory_report()
    report["jobs"].append(dict(report["jobs"][0]))
    report["summary"]["job_count"] = 2
    report["summary"]["timing_integrity"]["affected_job_ids"] = [7, 7]
    with pytest.raises(HealthReportError, match="unique"):
        render_report(report)


def test_renderer_escapes_affected_name_and_keeps_caveat():
    report = _contradictory_report()
    report["jobs"][0]["name"] = "<script>|bad"
    rendered = render_report(report)
    assert "&lt;script&gt;" in rendered
    assert "<script>" not in rendered
    assert "Timing certification unavailable" in rendered


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize(
    "retained_marker",
    [
        "dependency_work_cost_seconds",
        "critical_path_end_basis",
        "execution_state",
        "duration_basis",
        "timing_validity",
    ],
)
def test_renderer_rejects_combined_marker_removal(strict, retained_marker):
    report = _contradictory_report(strict=strict)
    del report["summary"]["timing_integrity"]
    row = report["jobs"][0]
    row.pop("dependency_work_cost_seconds", None)
    row.pop("critical_path_end_basis", None)
    evidence = row["github_timing_evidence"]
    evidence["kind"] = "unknown"
    for field in ("execution_state", "duration_basis", "timing_validity"):
        evidence.pop(field, None)
    if retained_marker == "dependency_work_cost_seconds":
        row[retained_marker] = 0
    elif retained_marker == "critical_path_end_basis":
        row[retained_marker] = "dependency-work-cost"
    else:
        evidence[retained_marker] = {
            "execution_state": "not_executed",
            "duration_basis": "nonexecution_work_cost",
            "timing_validity": "contradictory",
        }[retained_marker]
    with pytest.raises(HealthReportError):
        render_report(report, max_skipped=0)


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize(
    "field",
    [
        "wall_clock_seconds",
        "peak_slot_utilization",
        "peak_concurrency",
        "average_slot_utilization",
    ],
)
def test_renderer_rejects_fabricated_all_nonexecution_measurements(strict, field):
    report = _contradictory_report(strict=strict)
    report["summary"][field] = 0
    with pytest.raises(HealthReportError, match="unavailable"):
        render_report(report)


def test_strict_renderer_rejects_missing_work_cost_basis():
    report = _contradictory_report(strict=True)
    del report["jobs"][0]["critical_path_end_basis"]
    with pytest.raises(HealthReportError, match="bases"):
        render_report(report)


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize(
    "retained_marker",
    ["critical_path_kind", "dependency_work_cost_path_seconds"],
)
def test_renderer_rejects_orphaned_summary_work_cost_markers(strict, retained_marker):
    report = _contradictory_report(strict=strict)
    summary = report["summary"]
    del summary["timing_integrity"]
    summary.pop("dependency_work_cost_path_seconds", None)
    summary["critical_path_kind"] = "exact" if strict else "lower-bound"
    row = report["jobs"][0]
    row.pop("dependency_work_cost_seconds", None)
    row.pop("critical_path_end_basis", None)
    del row["github_timing_evidence"]
    if retained_marker == "critical_path_kind":
        summary[retained_marker] = "dependency-work-cost"
    else:
        summary[retained_marker] = 0
    with pytest.raises(HealthReportError):
        render_report(report, max_skipped=0)
