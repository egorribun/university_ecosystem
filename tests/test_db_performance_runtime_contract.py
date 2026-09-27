"""Parsed contracts for the DB performance job's interpreter and safety gates."""

import ast
import shlex
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/db-perf-gate.yml"
SETUP_PYTHON = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"


def _job() -> dict[str, object]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return document["jobs"]["explain-check"]


def test_db_performance_job_pins_uv_python_for_all_consumers() -> None:
    job = _job()
    assert job.get("env", {}).get("UV_PYTHON") == "3.14"


def test_db_performance_installs_pinned_python_before_dependency_sync() -> None:
    steps = _job()["steps"]
    setup = [
        step
        for step in steps
        if step.get("uses", "").startswith("actions/setup-python@")
    ]
    assert len(setup) == 1
    assert setup[0]["uses"] == SETUP_PYTHON
    assert setup[0]["with"]["python-version"] == "3.14"
    assert "if" not in setup[0]
    assert "continue-on-error" not in setup[0]
    sync = next(step for step in steps if step.get("name") == "Install dependencies")
    assert sync["run"] == "uv sync --group dev"
    assert steps.index(setup[0]) < steps.index(sync)


def test_db_performance_reads_back_synced_runtime_before_database_work() -> None:
    steps = _job()["steps"]
    guards = [step for step in steps if step.get("name") == "Verify Python runtime"]
    assert len(guards) == 1
    guard = guards[0]
    assert "if" not in guard
    assert "continue-on-error" not in guard
    command = shlex.split(guard["run"])
    assert command[:6] == ["uv", "run", "--frozen", "--no-sync", "python", "-c"]
    assert len(command) == 7
    expected = ast.parse(
        "import sys; print(sys.version); "
        "assert sys.version_info[:2] == (3, 14), sys.version"
    )
    assert ast.dump(ast.parse(command[6])) == ast.dump(expected)
    sync_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Install dependencies"
    )
    assert steps.index(guard) == sync_index + 1
    migrations = next(
        step for step in steps if step.get("name") == "Run Alembic migrations"
    )
    assert steps.index(guard) < steps.index(migrations)


def test_db_performance_keeps_existing_database_and_explain_safety() -> None:
    job = _job()
    assert job["timeout-minutes"] == 30
    steps = {step.get("name"): step for step in job["steps"]}
    assert steps["Run Alembic migrations"]["run"] == "uv run alembic upgrade head 2>&1"
    pytest_step = steps["Run Pytest to capture query logs"]
    marker = "UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET"
    assert pytest_step["env"][marker] == "1"
    assert WORKFLOW.read_text(encoding="utf-8").count(marker) == 1
    assert '-k "not integration and not performance"' in pytest_step["run"]
    explain = shlex.split(steps["Run EXPLAIN checks"]["run"].replace("\\\n", ""))
    assert explain == [
        "uv",
        "run",
        "python",
        "scripts/db_explain_check.py",
        "--fail-on-seq-scan",
        "--tables",
        "news,events,users",
        "--max-cost",
        "500.0",
        "--log-dir",
        "tests",
    ]
