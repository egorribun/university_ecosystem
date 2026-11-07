"""Keep AUD241 row-lock proofs in the PostgreSQL lane, never a SQLite pass."""

from __future__ import annotations

import ast
from pathlib import Path

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
    assert unit_pytest["run"].strip() == ". ./scripts/ci/backend-run-pytest.ps1"
    pytest_runner = BACKEND_PYTEST_RUNNER.read_text(encoding="utf-8")
    assert pytest_runner.count(f'"--ignore={RESERVATION_SELECTOR}"') == 1

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
    assert integration_step["run"].strip() == (
        ". ./scripts/ci/backend-run-integration-tests.ps1"
    )
    integration_runner = BACKEND_INTEGRATION_RUNNER.read_text(encoding="utf-8")
    assert "$env:INTEGRATION_TEST_PATTERN" in integration_runner
