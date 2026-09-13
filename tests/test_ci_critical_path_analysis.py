"""Tests for the read-only CI critical-path timing analyzer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from scripts.quality import analyze_ci_critical_path as analyzer
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
        record.setdefault("status", "completed")
        record.setdefault("conclusion", "success")
        record.setdefault("started_at", "2026-08-31T10:00:00Z")
        record.setdefault("completed_at", "2026-08-31T10:00:01Z")
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


def _trusted_provenance(dag: dict[str, object]) -> dict[str, object]:
    return {
        "selector": "select_same_run_artifact_cli",
        "repository": dag["repository"],
        "run_id": dag["run_id"],
        "run_attempt": dag["run_attempt"],
        "source_head_sha": dag["source_head_sha"],
        "tested_commit_sha": dag["tested_commit_sha"],
        "workflow_path": dag["workflow_path"],
        "workflow_ref": dag["workflow_ref"],
        "workflow_sha": dag["workflow_sha"],
        "workflow_files_sha256": dag["workflow_files_sha256"],
        "artifact_id": 1,
        "artifact_name": f"ci-critical-path-{dag['run_id']}-{dag['run_attempt']}",
        "artifact_digest": "e" * 64,
        "producer_attempt": dag["run_attempt"],
        "dag_sha256": dag["dag_sha256"],
    }


def test_analyzer_reports_dependency_wait_utilization_and_duplicates() -> None:
    payload = _bound_payload(_payload())
    dag = _dag_payload(payload)
    report = analyze_jobs(
        parse_jobs(payload),
        repository="egorribun/university_ecosystem",
        run_id=33349026009,
        concurrency_cap=20,
        dag=dag,
        trusted_provenance=_trusted_provenance(dag),
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
        "authentication": "same-run-artifact-selector",
        "artifact_id": 1,
        "artifact_name": "ci-critical-path-33349026009-1",
        "artifact_digest": "e" * 64,
        "producer_attempt": 1,
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
    dag = _dag_payload(payload, run_id=1)
    with pytest.raises(AnalysisError, match=message):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=1,
            concurrency_cap=20,
            dag=dag,
            trusted_provenance=_trusted_provenance(dag),
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
    dag = _dag_payload(payload)
    report = analyze_jobs(
        parse_jobs(payload),
        repository="egorribun/university_ecosystem",
        run_id=33349026009,
        concurrency_cap=20,
        dag=dag,
        trusted_provenance=_trusted_provenance(dag),
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
    trusted = _trusted_provenance(dag)
    dag["nodes"][0]["phase"] = "tampered"  # type: ignore[index]

    with pytest.raises(AnalysisError, match="dag_sha256"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
            dag=dag,
            trusted_provenance=trusted,
        )


def test_strict_analysis_rejects_dag_identity_mismatch() -> None:
    payload = _bound_payload(_payload())
    dag = _dag_payload(payload)
    trusted = _trusted_provenance(dag)
    dag["run_id"] = 999

    with pytest.raises(AnalysisError, match="run_id"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
            dag=dag,
            trusted_provenance=trusted,
        )


def test_strict_analysis_rejects_job_identity_mismatch() -> None:
    payload = _bound_payload(_payload())
    payload["jobs"][0]["run_id"] = 999  # type: ignore[index]
    dag = _dag_payload(payload)

    with pytest.raises(AnalysisError, match="job 101 run_id"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
            dag=dag,
            trusted_provenance=_trusted_provenance(dag),
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
    dag = _dag_payload(payload)

    with pytest.raises(AnalysisError, match="terminal"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
            dag=dag,
            trusted_provenance=_trusted_provenance(dag),
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
    dag = _dag_payload(payload)

    with pytest.raises(AnalysisError, match="identity"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
            dag=dag,
            trusted_provenance=_trusted_provenance(dag),
        )


def test_strict_analysis_rejects_completed_job_without_timing() -> None:
    payload = _bound_payload(_payload())
    first = cast(dict[str, object], payload["jobs"][0])
    first["started_at"] = None
    first["completed_at"] = None
    first["steps"] = []
    dag = _dag_payload(payload)

    with pytest.raises(AnalysisError, match="complete job timing"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
            dag=dag,
            trusted_provenance=_trusted_provenance(dag),
        )


def test_diagnostic_analysis_rejects_mixed_run_attempts() -> None:
    payload = _payload()
    assert isinstance(payload, dict)
    records = cast(list[dict[str, object]], payload["jobs"])
    for record in records:
        record.update(run_id=1, run_attempt=1, head_sha="a" * 40)
    records[1]["run_attempt"] = 2

    with pytest.raises(AnalysisError, match="mix run_attempt"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=1,
            concurrency_cap=20,
            diagnostic_lower_bound=True,
        )


def test_diagnostic_analysis_rejects_mixed_source_heads() -> None:
    payload = _payload()
    assert isinstance(payload, dict)
    records = cast(list[dict[str, object]], payload["jobs"])
    for record in records:
        record.update(run_id=1, run_attempt=1, head_sha="a" * 40)
    records[1]["head_sha"] = "b" * 40

    with pytest.raises(AnalysisError, match="mix source head"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=1,
            concurrency_cap=20,
            diagnostic_lower_bound=True,
        )


def test_strict_analysis_rejects_boolean_schema_version() -> None:
    payload = _bound_payload(_payload())
    dag = _dag_payload(payload)
    dag["schema_version"] = True
    canonical = dict(dag)
    canonical.pop("dag_sha256")
    dag["dag_sha256"] = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    with pytest.raises(AnalysisError, match="schema_version"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
            dag=dag,
        )


def test_strict_analysis_rejects_non_integer_dag_run_id() -> None:
    payload = _bound_payload(_payload())
    dag = _dag_payload(payload)
    dag["run_id"] = 33349026009.0
    canonical = dict(dag)
    canonical.pop("dag_sha256")
    dag["dag_sha256"] = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    with pytest.raises(AnalysisError, match="run_id"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
            dag=dag,
        )


def test_strict_analysis_rejects_structurally_valid_but_untrusted_sidecar() -> None:
    payload = _bound_payload(_payload())
    dag = _dag_payload(payload)

    with pytest.raises(AnalysisError, match="authenticated provenance"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
            dag=dag,
        )


def test_strict_analysis_rejects_sidecar_tampering_against_trusted_record() -> None:
    payload = _bound_payload(_payload())
    dag = _dag_payload(payload)
    trusted = _trusted_provenance(dag)
    dag["tested_commit_sha"] = "f" * 40
    canonical = dict(dag)
    canonical.pop("dag_sha256")
    dag["dag_sha256"] = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    with pytest.raises(AnalysisError, match="trusted provenance"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
            dag=dag,
            trusted_provenance=trusted,
        )


@pytest.mark.parametrize("field", ["run_id", "run_attempt"])
def test_strict_analysis_rejects_float_trusted_identity(field: str) -> None:
    payload = _bound_payload(_payload())
    dag = _dag_payload(payload)
    trusted = _trusted_provenance(dag)
    trusted[field] = float(cast(int, dag[field]))

    with pytest.raises(AnalysisError, match="trusted provenance"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
            dag=dag,
            trusted_provenance=trusted,
        )


def test_strict_analysis_rejects_completed_job_without_conclusion() -> None:
    payload = _bound_payload(_payload())
    first = cast(dict[str, object], payload["jobs"][0])
    first["conclusion"] = None
    dag = _dag_payload(payload)

    with pytest.raises(AnalysisError, match="terminal conclusions"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
            dag=dag,
            trusted_provenance=_trusted_provenance(dag),
        )


def test_strict_analysis_rejects_incomplete_step_timing() -> None:
    payload = _bound_payload(_payload())
    first = cast(dict[str, object], payload["jobs"][0])
    first["steps"] = [{"name": "partially-recorded-step"}]
    dag = _dag_payload(payload)

    with pytest.raises(AnalysisError, match="complete step timing"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
            dag=dag,
            trusted_provenance=_trusted_provenance(dag),
        )


def test_strict_analysis_rejects_step_outside_job_interval() -> None:
    payload = _bound_payload(_payload())
    first = cast(dict[str, object], payload["jobs"][0])
    first["steps"] = [
        {
            "name": "outside-job",
            "started_at": "2026-08-31T09:59:59Z",
            "completed_at": "2026-08-31T10:00:31Z",
        }
    ]
    dag = _dag_payload(payload)

    with pytest.raises(AnalysisError, match="within job bounds"):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=33349026009,
            concurrency_cap=20,
            dag=dag,
            trusted_provenance=_trusted_provenance(dag),
        )


def test_parser_rejects_large_cancelled_timestamp_inversion() -> None:
    with pytest.raises(AnalysisError, match="ends before"):
        parse_jobs(
            {
                "jobs": [
                    {
                        "id": 1,
                        "name": "cancelled-empty-job",
                        "status": "completed",
                        "conclusion": "cancelled",
                        "started_at": "2030-01-01T00:00:00Z",
                        "completed_at": "1970-01-01T00:00:00Z",
                        "steps": [],
                    }
                ]
            }
        )


def test_timing_ledger_omits_unmeasured_step_buckets() -> None:
    report = analyze_jobs(
        parse_jobs(
            {
                "jobs": [
                    {
                        "id": 1,
                        "name": "job-without-step-timing",
                        "status": "completed",
                        "conclusion": "success",
                        "created_at": "2026-08-31T10:00:00Z",
                        "started_at": "2026-08-31T10:00:10Z",
                        "completed_at": "2026-08-31T10:01:10Z",
                        "steps": [],
                    }
                ]
            }
        ),
        repository="egorribun/university_ecosystem",
        run_id=1,
        concurrency_cap=20,
        diagnostic_lower_bound=True,
    )
    timing = cast(
        dict[str, dict[str, object]],
        cast(dict[str, object], report["summary"])["timing_seconds"],
    )
    assert timing["queue"]["count"] == 1
    assert timing["setup"]["count"] == 0
    assert timing["test"]["count"] == 0
    assert timing["artifact"]["count"] == 0


def test_strict_json_rejects_duplicate_keys_and_non_finite_values(
    tmp_path: Path,
) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"jobs": [], "jobs": []}', encoding="utf-8")
    with pytest.raises(AnalysisError, match="duplicate JSON key"):
        analyzer._load_json(duplicate)

    non_finite = tmp_path / "non-finite.json"
    non_finite.write_text('{"value": NaN}', encoding="utf-8")
    with pytest.raises(AnalysisError, match="non-finite"):
        analyzer._load_json(non_finite)


def test_parser_rejects_control_characters_in_job_names() -> None:
    with pytest.raises(AnalysisError, match="control character"):
        parse_jobs({"jobs": [{"id": 1, "name": "bad\x1b"}]})


def test_parser_rejects_incomplete_paginated_payload() -> None:
    with pytest.raises(AnalysisError, match="pagination is incomplete"):
        parse_jobs(
            [
                {
                    "total_count": 2,
                    "jobs": [{"id": 1, "name": "one"}],
                }
            ]
        )


def test_cli_report_contains_canonical_integrity_digest(tmp_path: Path) -> None:
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
    digest = report.pop("report_sha256")
    canonical = json.dumps(
        report, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    assert digest == hashlib.sha256(canonical.encode()).hexdigest()


def test_cli_strict_mode_loads_detached_trusted_provenance(
    tmp_path: Path,
) -> None:
    payload = _bound_payload(_payload())
    dag = _dag_payload(payload)
    jobs_path = tmp_path / "jobs.json"
    dag_path = tmp_path / "dag.json"
    trusted_path = tmp_path / "trusted-provenance.json"
    output = tmp_path / "critical-path.json"
    jobs_path.write_text(json.dumps(payload), encoding="utf-8")
    dag_path.write_text(json.dumps(dag), encoding="utf-8")
    trusted_path.write_text(json.dumps(_trusted_provenance(dag)), encoding="utf-8")

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
                str(jobs_path),
                "--dag-json",
                str(dag_path),
                "--trusted-provenance-json",
                str(trusted_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["provenance"]["authentication"] == ("same-run-artifact-selector")
    assert report["provenance"]["artifact_id"] == 1


@pytest.mark.parametrize("repository", ["owner/repo/extra", "owner/repo/../../secret"])
def test_cli_rejects_invalid_repository_before_fetch(
    monkeypatch: pytest.MonkeyPatch, repository: str, tmp_path: Path
) -> None:
    def fail_fetch(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("gh must not be invoked for an invalid repository")

    monkeypatch.setattr(analyzer, "_fetch_jobs", fail_fetch)
    with pytest.raises(SystemExit):
        main(
            [
                "--repository",
                repository,
                "--run-id",
                "1",
                "--concurrency-cap",
                "20",
                "--output",
                str(tmp_path / "report.json"),
                "--diagnostic-lower-bound",
            ]
        )


def test_fetch_jobs_bounds_and_sanitizes_helper_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*_args: object, **_kwargs: object) -> object:
        stderr = _kwargs["stderr"]
        assert hasattr(stderr, "write")
        stderr.write(b"secret\x1b[31m" + (b"x" * 5000))
        return analyzer.subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout=None,
            stderr=None,
        )

    monkeypatch.setattr(analyzer.subprocess, "run", fake_run)
    with pytest.raises(AnalysisError) as error:
        analyzer._fetch_jobs("owner/repo", 1)
    message = str(error.value)
    assert "secret" in message
    assert "\x1b" not in message
    assert len(message) <= analyzer.MAX_ERROR_CHARS


def test_fetch_jobs_times_out_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout_run(*_args: object, **_kwargs: object) -> object:
        raise analyzer.subprocess.TimeoutExpired(
            cmd="gh", timeout=analyzer.MAX_FETCH_SECONDS
        )

    monkeypatch.setattr(analyzer.subprocess, "run", timeout_run)
    with pytest.raises(AnalysisError, match="timed out"):
        analyzer._fetch_jobs("owner/repo", 1)


def test_parser_rejects_non_boolean_core_failure() -> None:
    with pytest.raises(AnalysisError, match="core_failure must be boolean"):
        parse_jobs(
            {
                "jobs": [
                    {
                        "id": 1,
                        "name": "typed-core-failure",
                        "core_failure": "false",
                    }
                ]
            }
        )


def test_parser_rejects_oversized_job_and_step_collections() -> None:
    with pytest.raises(AnalysisError, match="maximum of"):
        parse_jobs(
            {
                "jobs": [
                    {
                        "id": 1,
                        "name": "too-many-steps",
                        "steps": [
                            {"name": "step"}
                            for _ in range(analyzer.MAX_STEPS_PER_JOB + 1)
                        ],
                    }
                ]
            }
        )
    with pytest.raises(AnalysisError, match="maximum of"):
        parse_jobs(
            {
                "jobs": [
                    {
                        "id": index + 1,
                        "name": f"job-{index}",
                    }
                    for index in range(analyzer.MAX_JOBS + 1)
                ]
            }
        )
