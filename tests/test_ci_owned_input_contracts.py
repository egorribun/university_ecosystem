"""Regression contracts for CI-owned mutation and timing inputs."""

import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_mutmut_copies_live_sources_used_during_collection() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "frontend/tests/e2e-live" in config["tool"]["mutmut"]["also_copy"]
    assert (ROOT / "frontend/tests/e2e-live/auth-roles.live.spec.ts").is_file()


def test_weekly_duration_shards_keep_owned_postgres_prerequisites() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/weekly-test-durations.yml").read_text(
            encoding="utf-8"
        )
    )
    job = workflow["jobs"]["refresh-shard"]
    assert job["env"]["RUN_INTEGRATION_TESTS"] == "1"
    steps = job["steps"]
    setup = next(
        index
        for index, step in enumerate(steps)
        if "backend-prepull-owned-postgres.ps1" in step.get("run", "")
    )
    execution = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Run the measurable test suite"
    )
    assert setup < execution
    command = steps[execution]["run"]
    assert "--timeout-disable-debugger-detection" in command
    assert "pytest tests/ --no-cov" in command
    assert "--num-shards=4" in command
    assert command.count("--ignore=") == 3
