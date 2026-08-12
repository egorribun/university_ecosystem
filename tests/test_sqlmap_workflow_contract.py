from __future__ import annotations

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


def test_sqlmap_workflow_is_a_fail_closed_main_pr_smoke_gate() -> None:
    """The SQLMap job must stay bounded, pinned, and non-optional."""

    workflow = yaml.safe_load(SQLMAP_WORKFLOW_PATH.read_text(encoding="utf-8"))
    triggers = _workflow_triggers(workflow)
    assert triggers == {
        "push": {"branches": ["main"]},
        "pull_request": {"branches": ["main"]},
    }

    job = workflow["jobs"]["sqlmap"]
    assert job.get("continue-on-error", False) is False
    assert job["timeout-minutes"] == 20

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
    scan = steps[indexes["Run SQLMap Scan on API"]]

    assert indexes["Install SQLMap"] < indexes["Verify SQLMap OpenAPI support"]
    assert (
        indexes["Verify SQLMap OpenAPI support"]
        < indexes["Start FastAPI Backend in Background"]
    )
    assert (
        indexes["Start FastAPI Backend in Background"]
        < indexes["Run SQLMap Scan on API"]
    )
    assert install["run"].strip() == 'uv pip install "sqlmap==1.10.8"'

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

    for step in (capability, readiness, scan):
        assert step.get("continue-on-error", False) is False
        assert "|| true" not in step["run"]


def test_sqlmap_scan_uses_the_bounded_openapi_boolean_error_union_profile() -> None:
    """The smoke scan must avoid crawling/time probes and remain deterministic."""

    workflow = yaml.safe_load(SQLMAP_WORKFLOW_PATH.read_text(encoding="utf-8"))
    scan = next(
        step
        for step in workflow["jobs"]["sqlmap"]["steps"]
        if step.get("name") == "Run SQLMap Scan on API"
    )
    script = scan["run"]

    assert f'--openapi="{OPENAPI_URL}"' in script
    assert f'--openapi-base="{OPENAPI_BASE_URL}"' in script
    for option in (
        "--batch",
        "--crawl=0",
        "--technique=BEU",
        "--risk=1",
        "--level=1",
        "--threads=2",
        "--timeout=5",
        "--retries=0",
        "--flush-session",
    ):
        assert option in script

    assert "--crawl=1" not in script
    assert "--technique=BEUSTQ" not in script
