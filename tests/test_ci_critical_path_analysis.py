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
