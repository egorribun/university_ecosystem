"""Deployment keeps its gates while proving the irreversible MVP boundary."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SELECTOR = (
    "tests/integration/test_migration_roundtrip.py::"
    "test_baseline_upgrades_an_empty_database_and_refuses_its_downgrade"
)


def _workflow():
    return yaml.safe_load((ROOT / ".github/workflows/deploy.yml").read_text())


def _boundary_step(job):
    steps = [
        step
        for step in job["steps"]
        if step.get("name") == "Verify MVP migration boundary"
    ]
    assert len(steps) == 1
    return steps[0]


def _assert_boundary_job(job):
    step = _boundary_step(job)
    assert job["timeout-minutes"] == 30
    assert step["timeout-minutes"] == 10
    assert "continue-on-error" not in job
    assert "continue-on-error" not in step
    assert "if" not in step
    run = step["run"]
    assert run.startswith("set -euo pipefail\n")
    assert "alembic downgrade" not in run
    assert run.count("alembic upgrade head") == 2
    assert run.count("alembic current --check-heads") == 2
    assert run.count(SELECTOR) == 1
    assert "DATABASE_URL=sqlite+aiosqlite:///:memory:" in run
    assert "MIGRATION_ROUNDTRIP_DATABASE_URL='' RUN_INTEGRATION_TESTS=1" in run
    assert "timeout --signal=TERM --kill-after=10s 480s" in run
    assert "pytest -n 0 -q --tb=short --timeout=420" in run
    assert '--junitxml="$receipt_root/junit.xml"' in run
    assert "PY_BOUNDARY_RECEIPT" in run
    assert "|| true" not in run


def test_both_deploy_gates_prove_boundary_without_deployed_database_downgrade():
    workflow = _workflow()
    assert set(workflow.get("on", workflow.get(True))) == {"workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] is False
    jobs = workflow["jobs"]
    for name in ("validate", "rollback"):
        _assert_boundary_job(jobs[name])
    assert jobs["validate"]["if"] == "${{ github.ref == 'refs/heads/main' }}"
    assert jobs["rollback"]["needs"] == ["deploy"]
    assert jobs["rollback"]["if"] == "${{ inputs.environment == 'staging' }}"
    assert jobs["rollback"]["name"] == "Database rollback capability test"
    assert "rollback" in jobs["notify"]["needs"]


@pytest.mark.parametrize("defect", ["advisory", "omitted", "unbounded", "external"])
def test_boundary_dispatch_rejects_bypasses(defect):
    job = _workflow()["jobs"]["validate"]
    _assert_boundary_job(job)
    step = _boundary_step(job)
    if defect == "advisory":
        step["continue-on-error"] = True
    elif defect == "omitted":
        step["run"] = step["run"].replace(SELECTOR, "")
    elif defect == "unbounded":
        del step["timeout-minutes"]
    else:
        step["run"] = step["run"].replace("MIGRATION_ROUNDTRIP_DATABASE_URL='' ", "")
    with pytest.raises((AssertionError, KeyError)):
        _assert_boundary_job(job)


@pytest.mark.parametrize(
    "defect", ["failure", "error", "skipped", "identity", "empty", "duplicate"]
)
def test_boundary_receipt_requires_one_actual_success(
    tmp_path, monkeypatch, capsys, defect
):
    run = _boundary_step(_workflow()["jobs"]["validate"])["run"]
    body = run.split("<<'PY_BOUNDARY_RECEIPT'\n", 1)[1].split(
        "\nPY_BOUNDARY_RECEIPT", 1
    )[0]
    script = tmp_path / "receipt.py"
    script.write_text(body)
    report = tmp_path / "junit.xml"
    monkeypatch.setattr(sys, "argv", [str(script), str(report)])
    case = (
        '<testcase classname="tests.integration.test_migration_roundtrip" '
        'name="test_baseline_upgrades_an_empty_database_and_refuses_its_downgrade"/>'
    )
    start = '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0">'
    end = "</testsuite></testsuites>"
    report.write_text(start + case + end)
    runpy.run_path(str(script), run_name="__main__")
    assert capsys.readouterr().out == "MVP_BASELINE_BOUNDARY_VERIFIED_PASS 1\n"
    if defect in {"failure", "error", "skipped"}:
        case = case.replace("/>", f"><{defect}/></testcase>")
    elif defect == "identity":
        case = case.replace("test_baseline_upgrades_", "test_foreign_upgrades_")
    elif defect == "empty":
        case = ""
    else:
        case += case
    report.write_text(start + case + end)
    with pytest.raises(SystemExit):
        runpy.run_path(str(script), run_name="__main__")
    assert "VERIFIED_PASS" not in capsys.readouterr().out
