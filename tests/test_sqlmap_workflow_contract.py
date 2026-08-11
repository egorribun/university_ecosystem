from __future__ import annotations

import shlex
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SQLMAP_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "sqlmap.yml"
OPENAPI_URL = "http://127.0.0.1:8000/api/openapi.json"
OPENAPI_BASE_URL = "http://127.0.0.1:8000"


def test_sqlmap_fails_closed_before_scanning_the_disposable_local_openapi_app() -> None:
    """SQLMap must pin and prove OpenAPI support before a local-only scan."""

    workflow = yaml.safe_load(SQLMAP_WORKFLOW_PATH.read_text(encoding="utf-8"))
    sqlmap_job = workflow["jobs"]["sqlmap"]
    assert sqlmap_job.get("continue-on-error", False) is False
    assert sqlmap_job["timeout-minutes"] == 20

    steps = sqlmap_job["steps"]
    indexes_and_steps = {
        step["name"]: (index, step) for index, step in enumerate(steps)
    }

    install_index, install = indexes_and_steps["Install SQLMap"]
    capability_index, capability = indexes_and_steps["Verify SQLMap OpenAPI support"]
    readiness_index, readiness = indexes_and_steps[
        "Start FastAPI Backend in Background"
    ]
    scan_index, scan = indexes_and_steps["Run SQLMap Scan on API"]

    assert install_index < capability_index < scan_index
    assert readiness_index < scan_index
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

    scan_script = scan["run"]
    assert f'--openapi="{OPENAPI_URL}"' in scan_script
    assert f'--openapi-base="{OPENAPI_BASE_URL}"' in scan_script
    for option in ("--batch", "--crawl=1", "--risk=1", "--level=1", "--threads=2"):
        assert option in scan_script

    scan_arguments = shlex.split(scan_script.replace("\\\n", ""), comments=True)
    assert scan_arguments == [
        "uv",
        "run",
        "sqlmap",
        f"--openapi={OPENAPI_URL}",
        f"--openapi-base={OPENAPI_BASE_URL}",
        "--batch",
        "--crawl=1",
        "--risk=1",
        "--level=1",
        "--threads=2",
        "--flush-session",
    ]

    for step in (capability, readiness, scan):
        assert step.get("continue-on-error", False) is False
        assert "|| true" not in step["run"]
