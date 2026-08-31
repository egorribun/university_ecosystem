"""Tests for the read-only CI critical-path timing analyzer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.quality.analyze_ci_critical_path import (
    AnalysisError,
    analyze_jobs,
    parse_jobs,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "quality" / "github-actions-jobs.json"


def _payload() -> object:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_analyzer_reports_dependency_wait_utilization_and_duplicates() -> None:
    report = analyze_jobs(
        parse_jobs(_payload()),
        repository="egorribun/university_ecosystem",
        run_id=33349026009,
        concurrency_cap=20,
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
    rows = {row["name"]: row for row in report["jobs"]}
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
            "missing dependency",
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
    with pytest.raises(AnalysisError, match=message):
        analyze_jobs(
            parse_jobs(payload),
            repository="egorribun/university_ecosystem",
            run_id=1,
            concurrency_cap=20,
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
