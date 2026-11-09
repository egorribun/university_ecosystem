from __future__ import annotations

import re
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SQLMAP_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "sqlmap.yml"
OPENAPI_URL = "http://127.0.0.1:8000/api/openapi.json"
OPENAPI_BASE_URL = "http://127.0.0.1:8000"


def _workflow_triggers(workflow: dict[str, object]) -> dict[str, object]:
    """PyYAML parses the YAML 1.1 key ``on`` as boolean True."""

    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict)
    return triggers


def test_sqlmap_workflow_is_scheduled_manual_default_branch_evidence() -> None:
    """SQLMap remains bounded and fail-closed on trusted scheduled/manual runs."""

    workflow = yaml.safe_load(SQLMAP_WORKFLOW_PATH.read_text(encoding="utf-8"))
    triggers = _workflow_triggers(workflow)
    assert triggers == {
        "schedule": [{"cron": "0 4 * * 1"}],
        "workflow_dispatch": {},
    }

    job = workflow["jobs"]["sqlmap"]
    assert (
        job["if"]
        == "${{ always() && github.ref == 'refs/heads/main' && (github.event_name != 'workflow_dispatch' || needs.verify-default-branch-dispatch.result == 'success') }}"
    )
    assert job["needs"] == "verify-default-branch-dispatch"
    assert job.get("continue-on-error", False) is False
    assert job["timeout-minutes"] == 20

    verify = workflow["jobs"]["verify-default-branch-dispatch"]
    assert verify["if"] == "${{ github.event_name == 'workflow_dispatch' }}"
    assert "refs/heads/main" in verify["steps"][0]["run"]

    checkout = next(
        step for step in job["steps"] if step.get("name") == "Checkout repository"
    )
    assert checkout["with"]["persist-credentials"] is False


def test_sqlmap_proves_openapi_capability_and_backend_readiness_before_scan() -> None:
    """A missing SQLMap feature or backend document must stop the job early."""

    workflow = yaml.safe_load(SQLMAP_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["sqlmap"]["steps"]
    indexes = {step["name"]: index for index, step in enumerate(steps)}

    install = steps[indexes["Install SQLMap"]]
    capability = steps[indexes["Verify SQLMap OpenAPI support"]]
    readiness = steps[indexes["Start FastAPI Backend in Background"]]
    full_scan = steps[indexes["Run SQLMap scan for every anonymous OpenAPI operation"]]
    news_scan = steps[indexes["Run SQLMap Scan on API"]]

    assert indexes["Install SQLMap"] < indexes["Verify SQLMap OpenAPI support"]
    assert (
        indexes["Verify SQLMap OpenAPI support"]
        < indexes["Start FastAPI Backend in Background"]
    )
    assert indexes["Start FastAPI Backend in Background"] < indexes[full_scan["name"]]
    assert indexes[news_scan["name"]] < indexes[full_scan["name"]]
    assert re.fullmatch(
        r'uv pip install "sqlmap==\d+\.\d+\.\d+"', install["run"].strip()
    )

    capability_script = capability["run"]
    assert "uv run sqlmap -hh" in capability_script
    assert 'grep -Fq -- "--openapi="' in capability_script
    assert "exit 1" in capability_script

    readiness_script = readiness["run"]
    assert OPENAPI_URL in readiness_script
    assert "http://127.0.0.1:8000/openapi.json" not in readiness_script
    assert "curl --fail --silent --show-error" in readiness_script
    assert "test -s" in readiness_script
    assert "for i in {1..30}; do" in readiness_script
    assert "exit 1" in readiness_script

    assert "scope-full-openapi" in readiness_script
    assert "sqlmap-openapi-output/scoped-openapi.json" in readiness_script

    for step in (capability, readiness):
        assert step.get("continue-on-error", False) is False
        assert "|| true" not in step["run"]
    for step in (full_scan, news_scan):
        assert step["continue-on-error"] is True
        assert "|| true" not in step["run"]


def test_sqlmap_full_openapi_scan_covers_every_anonymous_operation() -> None:
    """The blocking full scan keeps its bounded boolean/error-union settings."""

    workflow = yaml.safe_load(SQLMAP_WORKFLOW_PATH.read_text(encoding="utf-8"))
    scan = next(
        step
        for step in workflow["jobs"]["sqlmap"]["steps"]
        if step.get("name") == "Run SQLMap scan for every anonymous OpenAPI operation"
    )
    script = scan["run"]

    assert '--openapi="sqlmap-openapi-output/scoped-openapi.json"' in script
    assert f'--openapi-base="{OPENAPI_BASE_URL}"' in script
    assert "--scope='^http://127[.]0[.]0[.]1:8000/'" in script
    assert "Authorization:" not in script
    for option in (
        "--batch",
        "--crawl=0",
        "--technique=BEU",
        "--risk=1",
        "--level=1",
        "--threads=2",
        "--timeout=5",
        "--retries=0",
        "--output-dir=sqlmap-openapi-output",
        "--results-file=sqlmap-openapi-output/results.csv",
        "--flush-session",
    ):
        assert option in script

    assert "--crawl=1" not in script
    assert "--technique=BEUSTQ" not in script


def test_sqlmap_seeded_news_scan_keeps_the_anonymous_query_proof() -> None:
    workflow = yaml.safe_load(SQLMAP_WORKFLOW_PATH.read_text(encoding="utf-8"))
    scan = next(
        step
        for step in workflow["jobs"]["sqlmap"]["steps"]
        if step.get("name") == "Run SQLMap Scan on API"
    )
    script = scan["run"]
    assert '--openapi="sqlmap-output/scoped-openapi.json"' in script
    assert f'--openapi-base="{OPENAPI_BASE_URL}"' in script
    assert "--scope='^http://127[.]0[.]0[.]1:8000/api/v1/news([?]|$)'" in script
    assert ": > sqlmap-output/db-query-evidence.log" in script
    assert "--results-file=sqlmap-output/results.csv" in script


def test_sqlmap_gates_both_scans_and_retains_the_raw_reports() -> None:
    workflow = yaml.safe_load(SQLMAP_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["sqlmap"]["steps"]
    gates = {
        step["id"]: step
        for step in steps
        if step.get("id") in {"sqlmap-openapi-gate", "sqlmap-news-gate"}
    }
    assert set(gates) == {"sqlmap-openapi-gate", "sqlmap-news-gate"}
    assert gates["sqlmap-openapi-gate"]["if"] == "${{ always() }}"
    assert gates["sqlmap-news-gate"]["if"] == "${{ always() }}"
    assert all("continue-on-error" not in gate for gate in gates.values())
    assert "gate-openapi" in gates["sqlmap-openapi-gate"]["run"]
    assert "gate-news" in gates["sqlmap-news-gate"]["run"]
    assert "steps.sqlmap-openapi-scan.outcome" in str(
        gates["sqlmap-openapi-gate"]["env"]
    )
    assert "steps.sqlmap-news-scan.outcome" in str(gates["sqlmap-news-gate"]["env"])

    upload = next(
        step
        for step in steps
        if step.get("name") == "Upload SQLMap reports and evidence receipt"
    )
    assert upload["if"] == "${{ always() }}"
    assert upload["with"]["retention-days"] == 90
    assert upload["with"]["path"].splitlines() == [
        "sqlmap-output/",
        "sqlmap-openapi-output/",
        "sqlmap-evidence/receipt.json",
    ]
