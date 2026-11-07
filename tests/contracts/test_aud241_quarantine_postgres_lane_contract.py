"""Keep AUD241 row-lock proofs in the PostgreSQL lane, never a SQLite pass."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "reusable-backend-tests.yml"
BACKEND_PYTEST_RUNNER = ROOT / "scripts" / "ci" / "backend-run-pytest.ps1"
BACKEND_INTEGRATION_RUNNER = (
    ROOT / "scripts" / "ci" / "backend-run-integration-tests.ps1"
)
RESERVATION_TEST = (
    ROOT / "tests" / "integration" / "test_quarantine_reservations_postgres.py"
)
RESERVATION_SELECTOR = "tests/integration/test_quarantine_reservations_postgres.py"


def _step(steps: list[dict[str, object]], name: str) -> dict[str, object]:
    return next(step for step in steps if step.get("name") == name)


def test_quarantine_concurrency_cases_fail_closed_outside_postgresql() -> None:
    source = RESERVATION_TEST.read_text(encoding="utf-8")
    module = ast.parse(source)
    test_names = {
        node.name
        for node in module.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("test_")
    }
    assert test_names == {
        "test_independent_workers_cannot_overbook_one_storage_scope",
        "test_pending_reservation_survives_absence_observation_and_late_put",
        "test_quarantine_ledger_baseline_has_complete_irreversible_schema",
    }
    markers = [
        node.value
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "pytestmark"
            for target in node.targets
        )
    ]
    expected_markers = ast.parse(
        "[pytest.mark.integration, pytest.mark.asyncio, "
        'pytest.mark.timeout(300, method="signal", func_only=False)]',
        mode="eval",
    ).body
    assert [ast.dump(node) for node in markers] == [ast.dump(expected_markers)]

    postgres_factory = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "_postgres_factory"
    )
    expected_guards = ast.parse(
        'assert engine.dialect.name == "postgresql"\n'
        'assert engine.url.drivername == "postgresql+asyncpg"'
    ).body
    assert [ast.dump(node) for node in postgres_factory.body[:2]] == [
        ast.dump(node) for node in expected_guards
    ]
    calls = [node for node in ast.walk(module) if isinstance(node, ast.Call)]
    assert not any(
        isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "pytest"
        and node.func.attr == "skip"
        for node in calls
    )


def test_backend_lanes_exclude_from_unit_and_include_in_postgresql() -> None:
    reusable = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    triggers = reusable.get("on", reusable.get(True))
    inputs = triggers["workflow_call"]["inputs"]
    assert inputs["test-pattern"]["default"] == "tests/"
    integration_pattern = inputs["integration-test-pattern"]["default"]
    assert integration_pattern == "tests/integration/"
    assert RESERVATION_TEST.is_relative_to(ROOT / integration_pattern)

    unit_steps = reusable["jobs"]["unit-tests"]["steps"]
    unit_pytest = _step(unit_steps, "Run pytest")
    assert unit_pytest["env"]["TEST_PATTERN"] == "${{ inputs.test-pattern }}"
    assert unit_pytest["shell"] == "pwsh"
    assert unit_pytest["run"] == ". ./scripts/ci/backend-run-pytest.ps1\n"
    unit_source = BACKEND_PYTEST_RUNNER.read_text(encoding="utf-8")
    reservation_arg = f'"--ignore={RESERVATION_SELECTOR}"'
    assert unit_source.count(reservation_arg) == 1

    integration_job = reusable["jobs"]["integration-tests"]
    assert integration_job["if"] == "${{ inputs.run-integration-tests }}"
    assert integration_job["env"]["RUN_INTEGRATION_TESTS"] == "1"
    assert integration_job["env"]["DATABASE_URL"].startswith("postgresql+asyncpg://")
    integration_step = _step(integration_job["steps"], "Run integration tests")
    assert (
        integration_step["env"]["INTEGRATION_TEST_PATTERN"]
        == "${{ inputs.integration-test-pattern }}"
    )
    assert integration_step["shell"] == "pwsh"
    assert (
        integration_step["run"] == ". ./scripts/ci/backend-run-integration-tests.ps1\n"
    )
    for owner in (reusable, reusable["jobs"]["unit-tests"], integration_job):
        assert "working-directory" not in (owner.get("defaults") or {}).get("run", {})
    assert "working-directory" not in unit_pytest
    assert "working-directory" not in integration_step
    integration_source = BACKEND_INTEGRATION_RUNNER.read_text(encoding="utf-8")
    assert "$env:INTEGRATION_TEST_PATTERN" in integration_source
    assert reservation_arg not in integration_source


@pytest.mark.parametrize(
    "mutation",
    [
        "unchanged",
        "unit-invocation",
        "integration-invocation",
        "unit-shell",
        "integration-shell",
        "workflow-directory",
        "unit-job-directory",
        "integration-job-directory",
        "unit-step-directory",
        "integration-step-directory",
        "missing-unit-exclusion",
        "duplicate-unit-exclusion",
        "missing-integration-pattern",
        "integration-exclusion",
    ],
)
def test_quarantine_lane_contract_rejects_extracted_runner_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    unit = workflow["jobs"]["unit-tests"]
    integration = workflow["jobs"]["integration-tests"]
    unit_step = _step(unit["steps"], "Run pytest")
    integration_step = _step(integration["steps"], "Run integration tests")
    unit_source = BACKEND_PYTEST_RUNNER.read_text(encoding="utf-8")
    integration_source = BACKEND_INTEGRATION_RUNNER.read_text(encoding="utf-8")
    ignore = f'"--ignore={RESERVATION_SELECTOR}"'
    if mutation == "unchanged":
        pass
    elif mutation.endswith("-invocation"):
        step = unit_step if mutation.startswith("unit-") else integration_step
        step["run"] = ". ./scripts/ci/unreviewed-runner.ps1\n"
    elif mutation.endswith("-shell"):
        step = unit_step if mutation.startswith("unit-") else integration_step
        step["shell"] = "bash"
    elif mutation.endswith("-directory"):
        owner = {
            "workflow-directory": workflow,
            "unit-job-directory": unit,
            "integration-job-directory": integration,
        }.get(mutation)
        if owner is None:
            step = unit_step if mutation.startswith("unit-") else integration_step
            step["working-directory"] = "elsewhere"
        else:
            owner["defaults"] = {"run": {"working-directory": "elsewhere"}}
    elif mutation == "missing-unit-exclusion":
        assert unit_source.count(ignore) == 1
        unit_source = unit_source.replace(ignore, "")
    elif mutation == "duplicate-unit-exclusion":
        unit_source += f"\n$pytestArgs += @({ignore})\n"
    elif mutation == "missing-integration-pattern":
        assert "$env:INTEGRATION_TEST_PATTERN" in integration_source
        integration_source = integration_source.replace(
            "$env:INTEGRATION_TEST_PATTERN", ""
        )
    else:
        integration_source += f"\n$pytestArgs += @({ignore})\n"
    helper_dir = tmp_path / "scripts/ci"
    helper_dir.mkdir(parents=True)
    unit_runner_path = helper_dir / "backend-run-pytest.ps1"
    unit_runner_path.write_text(unit_source, encoding="utf-8")
    integration_runner_path = helper_dir / "backend-run-integration-tests.ps1"
    integration_runner_path.write_text(integration_source, encoding="utf-8")
    workflow_path = tmp_path / "reusable-backend-tests.yml"
    workflow_path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    module = sys.modules[__name__]
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "WORKFLOW", workflow_path)
    monkeypatch.setattr(module, "BACKEND_PYTEST_RUNNER", unit_runner_path)
    monkeypatch.setattr(module, "BACKEND_INTEGRATION_RUNNER", integration_runner_path)
    monkeypatch.setattr(module, "RESERVATION_TEST", tmp_path / RESERVATION_SELECTOR)
    if mutation == "unchanged":
        test_backend_lanes_exclude_from_unit_and_include_in_postgresql()
    else:
        with pytest.raises(AssertionError):
            test_backend_lanes_exclude_from_unit_and_include_in_postgresql()
