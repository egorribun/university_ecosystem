"""Tests for the read-only CI critical-path timing analyzer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from scripts.quality.analyze_ci_critical_path import (
    AnalysisError,
    analyze_jobs,
    main,
    parse_jobs,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "quality" / "github-actions-jobs.json"


def _payload() -> object:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _bound_payload(payload: object, *, run_id: int = 33349026009) -> dict[str, object]:
    assert isinstance(payload, dict)
    records = cast(list[dict[str, object]], payload["jobs"])
    for record in records:
        record.update(run_id=run_id, run_attempt=1, head_sha="a" * 40)
    return payload


def _dag_payload(payload: object, *, run_id: int = 33349026009) -> dict[str, object]:
    assert isinstance(payload, dict)
    records = payload["jobs"]
    assert isinstance(records, list)
    by_id = {record["name"]: record["id"] for record in records}
    nodes = []
    for record in records:
        dependencies = []
        for dependency_name in record.get("needs", []):
            dependencies.append(by_id.get(dependency_name, 999999))
        nodes.append(
            {
                "job_id": record["id"],
                "logical_id": record["name"],
                "needs": dependencies,
                "phase": "test",
                "core_role": "required",
                "skip_classification": "ordinary",
                "core_failure": bool(record.get("core_failure", False)),
            }
        )
    envelope: dict[str, object] = {
        "schema_version": 1,
        "repository": "egorribun/university_ecosystem",
        "run_id": run_id,
        "run_attempt": 1,
        "source_head_sha": "a" * 40,
        "tested_commit_sha": "b" * 40,
        "workflow_path": ".github/workflows/ci.yml",
        "workflow_ref": "egorribun/university_ecosystem/.github/workflows/ci.yml@refs/pull/1/merge",
        "workflow_sha": "c" * 40,
        "workflow_files_sha256": {".github/workflows/ci.yml": "d" * 64},
        "nodes": nodes,
    }
    canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    envelope["dag_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return envelope


def test_analyzer_reports_dependency_wait_utilization_and_duplicates() -> None:
    payload = _bound_payload(_payload())
    report = analyze_jobs(
        parse_jobs(payload),
        repository="egorribun/university_ecosystem",
        run_id=33349026009,
        concurrency_cap=20,
        dag=_dag_payload(payload),
    )

    assert report["schema_version"] == 1
    summary = report["summary"]
    assert isinstance(summary, dict)
    assert summary["job_count"] == 3
    assert summary["critical_path_seconds"] == 180.0
    assert summary["peak_slot_utilization"] == 1
    assert 0 < summary["average_slot_utilization"] < 1
    assert summary["upstream_failure_blocked_jobs"] == [103]
    assert summary["jobs_continued_after_core_failure"] == [102]
    duplicate_steps = {
        item["step"] for item in summary["duplicate_setup_download_work"]
    }
    assert "checkout" in duplicate_steps
    report_jobs = cast(list[dict[str, object]], report["jobs"])
    rows = {row["name"]: row for row in report_jobs}
    assert rows["frontend-tests"]["dependency_wait_seconds"] == 60.0
    assert rows["frontend-tests"]["github_queue_wait_seconds"] == 90.0
    assert rows["frontend-tests"]["setup_install_seconds"] == 40.0
    assert rows["frontend-tests"]["artifact_seconds"] == 20.0

    assert summary["peak_concurrency"] == 1
    assert summary["retry_classification"] == {
        "state": "initial_workflow_attempt",
        "run_attempts": [1],
    }
    timeout_summary = summary["timeout_classification"]
    assert isinstance(timeout_summary, dict)
    assert timeout_summary["counts"] == {
        "cancelled": 0,
        "not_timed_out": 3,
        "timed_out": 0,
        "unknown": 0,
    }
    assert rows["frontend-tests"]["retry_classification"] == (
        "initial_workflow_attempt"
    )
    assert rows["frontend-tests"]["timeout_classification"] == "not_timed_out"
    provenance = report["provenance"]
    assert provenance == {
        "evidence_scope": "strict",
        "repository": "egorribun/university_ecosystem",
        "run_id": 33349026009,
        "run_attempt": 1,
        "source_head_sha": "a" * 40,
        "tested_commit_sha": "b" * 40,
        "workflow_path": ".github/workflows/ci.yml",
        "workflow_ref": "egorribun/university_ecosystem/.github/workflows/ci.yml@refs/pull/1/merge",
        "workflow_sha": "c" * 40,
        "workflow_files_sha256": {".github/workflows/ci.yml": "d" * 64},
        "dag_sha256": _dag_payload(payload)["dag_sha256"],
    }

    timing = summary["timing_seconds"]
    assert isinstance(timing, dict)
    assert timing["queue"] == {
        "count": 2,
        "total_seconds": 120.0,
        "p50_seconds": 30.0,
        "p95_seconds": 90.0,
        "max_seconds": 90.0,
    }
    assert timing["setup"] == {
        "count": 2,
        "total_seconds": 70.0,
        "p50_seconds": 30.0,
        "p95_seconds": 40.0,
        "max_seconds": 40.0,
    }
    assert timing["test"] == {
        "count": 2,
        "total_seconds": 90.0,
        "p50_seconds": 30.0,
        "p95_seconds": 60.0,
        "max_seconds": 60.0,
    }
    assert timing["artifact"] == {
        "count": 2,
        "total_seconds": 20.0,
        "p50_seconds": 0.0,
        "p95_seconds": 20.0,
        "max_seconds": 20.0,
    }


def test_diagnostic_timing_classifies_workflow_rerun_and_timeout() -> None:
    payload = _payload()
    assert isinstance(payload, dict)
    records = payload["jobs"]
    assert isinstance(records, list)
    for record in records:
        assert isinstance(record, dict)
        record.update(run_id=1, run_attempt=2, head_sha="a" * 40)
    first = records[0]
    assert isinstance(first, dict)
    first["conclusion"] = "failure"
    first_steps = first["steps"]
    assert isinstance(first_steps, list)
    first_step = first_steps[-1]
    assert isinstance(first_step, dict)
    first_step["conclusion"] = "timed_out"

    report = analyze_jobs(
        parse_jobs(payload),
        repository="egorribun/university_ecosystem",
        run_id=1,
        concurrency_cap=20,
        diagnostic_lower_bound=True,
    )
    summary = report["summary"]
    assert isinstance(summary, dict)
    assert summary["peak_concurrency"] == 1
    assert summary["retry_classification"] == {
        "state": "workflow_rerun",
        "run_attempts": [2],
    }
    timeout_summary = summary["timeout_classification"]
    assert isinstance(timeout_summary, dict)
    assert timeout_summary["counts"]["timed_out"] == 1
    assert timeout_summary["timed_out_job_ids"] == [101]
    report_jobs = cast(list[dict[str, object]], report["jobs"])
    rows = {row["id"]: row for row in report_jobs}
    assert rows[101]["retry_classification"] == "workflow_rerun"
    assert rows[101]["timeout_classification"] == "timed_out"
    provenance = report["provenance"]
    assert isinstance(provenance, dict)
    assert provenance["evidence_scope"] == "diagnostic-only"
    assert provenance["run_id"] == 1
    assert provenance["run_attempt"] == 2
    assert provenance["source_head_sha"] == "a" * 40
    assert provenance["tested_commit_sha"] is None
    assert provenance["identity_complete"] is True


def test_unknown_timeout_conclusion_and_incomplete_timed_out_step_fail_closed() -> None:
    payload = _payload()
    assert isinstance(payload, dict)
    records = payload["jobs"]
    assert isinstance(records, list)
    first = records[0]
    assert isinstance(first, dict)
    first["conclusion"] = "brand_new_api_state"
    first_steps = first["steps"]
    assert isinstance(first_steps, list)
    first_steps.append(
        {
            "name": "Run timed-out command",
            "started_at": None,
            "completed_at": None,
            "conclusion": "timed_out",
        }
    )

    report = analyze_jobs(
        parse_jobs(payload),
        repository="egorribun/university_ecosystem",
        run_id=1,
        concurrency_cap=20,
        diagnostic_lower_bound=True,
    )
    report_jobs = cast(list[dict[str, object]], report["jobs"])
    first_row = next(row for row in report_jobs if row["id"] == 101)
    assert first_row["timeout_classification"] == "timed_out"
    timeout_summary = cast(dict[str, object], report["summary"])[
        "timeout_classification"
    ]
    assert isinstance(timeout_summary, dict)
    assert timeout_summary["counts"]["timed_out"] == 1

    first["steps"] = [
        {
            "name": "Run command",
            "started_at": "2026-08-31T10:00:30Z",
            "completed_at": "2026-08-31T10:01:30Z",
        }
    ]
    report = analyze_jobs(
        parse_jobs(payload),
        repository="egorribun/university_ecosystem",
        run_id=1,
        concurrency_cap=20,
        diagnostic_lower_bound=True,
    )
    first_row = next(
        row for row in cast(list[dict[str, object]], report["jobs"]) if row["id"] == 101
    )
    assert first_row["timeout_classification"] == "unknown"


def test_parser_rejects_queue_timestamp_after_job_start() -> None:
    with pytest.raises(AnalysisError, match="created_at is after it starts"):
        parse_jobs(
            {
                "jobs": [
                    {
                        "id": 1,
                        "name": "queue-inversion",
                        "status": "completed",
                        "conclusion": "success",
                        "created_at": "2026-08-31T10:02:00Z",
                        "started_at": "2026-08-31T10:01:00Z",
                        "completed_at": "2026-08-31T10:02:00Z",
                    }
                ]
            }
        )


def test_diagnostic_analysis_rejects_job_from_a_different_run() -> None:
    payload = _payload()
    assert isinstance(payload, dict)
    records = payload["jobs"]
    assert isinstance(records, list)
    first = records[0]
    assert isinstance(first, dict)
    first["run_id"] = 2
    with pytest.raises(AnalysisError, match="job 101 run_id"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=1,
            concurrency_cap=20,
            diagnostic_lower_bound=True,
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {"jobs": [{"id": 1, "name": "a"}, {"id": 1, "name": "b"}]},
            "duplicate job id",
        ),
        (
            {"jobs": [{"id": 1, "name": "a", "needs": ["missing"]}]},
            "unknown dependency",
        ),
        (
            {
                "jobs": [
                    {"id": 1, "name": "a", "needs": ["b"]},
                    {"id": 2, "name": "b", "needs": ["a"]},
                ]
            },
            "dependency cycle",
        ),
    ],
)
def test_analyzer_rejects_ambiguous_or_incomplete_evidence(
    payload: object, message: str
) -> None:
    payload = _bound_payload(payload, run_id=1)
    with pytest.raises(AnalysisError, match=message):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=1,
            concurrency_cap=20,
            dag=_dag_payload(payload, run_id=1),
        )


def test_parser_rejects_naive_timestamps_and_negative_duration() -> None:
    with pytest.raises(AnalysisError, match="timezone"):
        parse_jobs(
            {
                "jobs": [
                    {
                        "id": 1,
                        "name": "bad",
                        "started_at": "2026-08-31T10:00:00",
                        "completed_at": "2026-08-31T10:01:00Z",
                    }
                ]
            }
        )
    with pytest.raises(AnalysisError, match="ends before"):
        parse_jobs(
            {
                "jobs": [
                    {
                        "id": 1,
                        "name": "bad",
                        "started_at": "2026-08-31T10:01:00Z",
                        "completed_at": "2026-08-31T10:00:00Z",
                    }
                ]
            }
        )


def test_parser_flattens_slurped_github_api_pages() -> None:
    payload = [
        {"total_count": 2, "jobs": [{"id": 1, "name": "a"}]},
        {"total_count": 2, "jobs": [{"id": 2, "name": "b"}]},
    ]

    parsed = parse_jobs(payload)

    assert [job.job_id for job in parsed] == [1, 2]


def test_parser_uses_created_at_when_live_jobs_omit_queued_at() -> None:
    parsed = parse_jobs(
        {
            "jobs": [
                {
                    "id": 1,
                    "name": "live-job",
                    "status": "completed",
                    "conclusion": "success",
                    "created_at": "2026-08-31T10:00:00Z",
                    "started_at": "2026-08-31T10:00:45Z",
                    "completed_at": "2026-08-31T10:01:00Z",
                }
            ]
        }
    )

    assert parsed[0].queue_wait_seconds == 45.0


def test_parser_accepts_github_cancelled_empty_job_timestamp_sentinel() -> None:
    """GitHub can invert timestamps by one second while cancelling an empty job."""
    parsed = parse_jobs(
        {
            "jobs": [
                {
                    "id": 1,
                    "name": "cancelled-empty-job",
                    "status": "completed",
                    "conclusion": "cancelled",
                    "created_at": "2026-08-31T10:00:00Z",
                    "started_at": "2026-08-31T10:00:01Z",
                    "completed_at": "2026-08-31T10:00:00Z",
                    "steps": [],
                }
            ]
        }
    )

    assert parsed[0].duration_seconds == 0.0


def test_parser_rejects_inverted_cancelled_job_with_steps() -> None:
    with pytest.raises(AnalysisError, match="ends before"):
        parse_jobs(
            {
                "jobs": [
                    {
                        "id": 1,
                        "name": "cancelled-with-work",
                        "status": "completed",
                        "conclusion": "cancelled",
                        "started_at": "2026-08-31T10:00:01Z",
                        "completed_at": "2026-08-31T10:00:00Z",
                        "steps": [
                            {
                                "name": "work",
                                "started_at": "2026-08-31T10:00:01Z",
                                "completed_at": "2026-08-31T10:00:01Z",
                            }
                        ],
                    }
                ]
            }
        )


def test_strict_analysis_requires_a_bound_dag_sidecar() -> None:
    with pytest.raises(AnalysisError, match="requires a DAG sidecar"):
        analyze_jobs(
            parse_jobs(_payload()),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
        )


def test_diagnostic_mode_labels_api_only_path_as_a_lower_bound() -> None:
    report = analyze_jobs(
        parse_jobs(_payload()),
        repository="egorribun/university_ecosystem",
        run_id=33349026009,
        concurrency_cap=20,
        diagnostic_lower_bound=True,
    )

    summary = report["summary"]
    assert isinstance(summary, dict)
    assert summary["analysis_mode"] == "diagnostic-lower-bound"
    assert summary["critical_path_kind"] == "lower-bound"
    assert "critical_path_seconds" not in summary
    assert "critical_path_lower_bound_seconds" in summary
    assert summary["upstream_failure_blocked_jobs"] == "unknown"
    assert summary["jobs_continued_after_core_failure"] == "unknown"
    report_jobs = cast(list[dict[str, object]], report["jobs"])
    assert all(row["needs"] == "unknown" for row in report_jobs)


def test_cli_diagnostic_mode_writes_a_lower_bound_report(tmp_path: Path) -> None:
    output = tmp_path / "critical-path.json"

    assert (
        main(
            [
                "--repository",
                "egorribun/university_ecosystem",
                "--run-id",
                "33349026009",
                "--concurrency-cap",
                "20",
                "--jobs-json",
                str(FIXTURE),
                "--output",
                str(output),
                "--diagnostic-lower-bound",
            ]
        )
        == 0
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["summary"]["critical_path_kind"] == "lower-bound"
    assert "critical_path_seconds" not in report["summary"]


def test_diagnostic_mode_does_not_treat_queued_timestamp_sentinel_as_started() -> None:
    report = analyze_jobs(
        parse_jobs(
            {
                "jobs": [
                    {
                        "id": 1,
                        "name": "queued-job",
                        "status": "queued",
                        "created_at": "2026-08-31T10:00:00Z",
                        "started_at": "2026-08-31T10:00:00Z",
                        "completed_at": None,
                    }
                ]
            }
        ),
        repository="egorribun/university_ecosystem",
        run_id=1,
        concurrency_cap=20,
        diagnostic_lower_bound=True,
    )

    report_jobs = cast(list[dict[str, object]], report["jobs"])
    assert report_jobs[0]["github_queue_wait_seconds"] is None


def test_strict_analysis_uses_numeric_sidecar_dependencies() -> None:
    payload = _bound_payload(_payload())
    report = analyze_jobs(
        parse_jobs(payload),
        repository="egorribun/university_ecosystem",
        run_id=33349026009,
        concurrency_cap=20,
        dag=_dag_payload(payload),
    )

    summary = report["summary"]
    assert isinstance(summary, dict)
    assert summary["analysis_mode"] == "strict"
    assert summary["critical_path_kind"] == "exact"
    assert summary["critical_path_seconds"] == 180.0
    report_jobs = cast(list[dict[str, object]], report["jobs"])
    assert report_jobs[1]["needs"] == ["pre-commit-check"]


def test_strict_analysis_rejects_dag_digest_tampering() -> None:
    payload = _bound_payload(_payload())
    dag = _dag_payload(payload)
    dag["nodes"][0]["phase"] = "tampered"  # type: ignore[index]

    with pytest.raises(AnalysisError, match="dag_sha256"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
            dag=dag,
        )


def test_strict_analysis_rejects_dag_identity_mismatch() -> None:
    payload = _bound_payload(_payload())
    dag = _dag_payload(payload)
    dag["run_id"] = 999

    with pytest.raises(AnalysisError, match="run_id"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
            dag=dag,
        )


def test_strict_analysis_rejects_job_identity_mismatch() -> None:
    payload = _bound_payload(_payload())
    payload["jobs"][0]["run_id"] = 999  # type: ignore[index]

    with pytest.raises(AnalysisError, match="job 101 run_id"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
            dag=_dag_payload(payload),
        )


def test_strict_analysis_rejects_nonterminal_jobs() -> None:
    payload = {
        "jobs": [
            {
                "id": 1,
                "name": "still-running",
                "status": "in_progress",
                "created_at": "2026-08-31T10:00:00Z",
                "started_at": "2026-08-31T10:00:01Z",
                "completed_at": None,
            }
        ]
    }

    with pytest.raises(AnalysisError, match="terminal"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
            dag=_dag_payload(payload),
        )


def test_strict_analysis_requires_api_identity_fields() -> None:
    payload = {
        "jobs": [
            {
                "id": 1,
                "name": "identity-less",
                "status": "completed",
                "conclusion": "success",
                "created_at": "2026-08-31T10:00:00Z",
                "started_at": "2026-08-31T10:00:01Z",
                "completed_at": "2026-08-31T10:00:02Z",
            }
        ]
    }

    with pytest.raises(AnalysisError, match="identity"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
            dag=_dag_payload(payload),
        )
