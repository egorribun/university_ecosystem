"""Parsed contracts for the canonical Chaos app-lane runtime and safety gates."""

import ast
import shlex
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"
SETUP_PYTHON = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"


def _job() -> dict[str, object]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return document["jobs"]["chaos-tests"]


def test_chaos_job_pins_uv_python_for_all_consumers() -> None:
    assert _job().get("env", {}).get("UV_PYTHON") == "3.14"


def test_chaos_installs_pinned_python_before_dependency_sync() -> None:
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
    assert sync["run"] == "uv sync --frozen"
    assert steps.index(setup[0]) < steps.index(sync)


def test_chaos_reads_back_synced_runtime_before_tests() -> None:
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
    tests = next(step for step in steps if step.get("name") == "Run chaos tests")
    assert steps.index(guard) < steps.index(tests)


def test_chaos_keeps_existing_services_tests_and_explicit_reset_safety() -> None:
    job = _job()
    assert job["needs"] == ["backend-tests"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["timeout-minutes"] == 15
    assert "if" not in job
    assert "continue-on-error" not in job
    assert set(job["services"]) == {"postgres", "redis", "nats", "minio", "toxiproxy"}
    tests = next(step for step in job["steps"] if step.get("name") == "Run chaos tests")
    assert shlex.split(tests["run"]) == [
        "uv",
        "run",
        "pytest",
        "tests/chaos/",
        "-v",
        "-m",
        "chaos",
        "--tb=short",
    ]
    assert tests["env"]["UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET"] == "1"
    assert "if" not in tests
    assert "continue-on-error" not in tests
