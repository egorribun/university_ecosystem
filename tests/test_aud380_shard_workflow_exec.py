from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
pytest_plugins = ("pytester",)


@pytest.mark.parametrize(
    ("filename", "job_id", "step_name", "shards", "program", "expected"),
    [
        (
            "reusable-frontend-tests.yml",
            "unit-tests-shard",
            "Run unit-test shard",
            [1, 2, 3, 4],
            "npm",
            [
                "run",
                "test:unit-ci",
                "--",
                "--shard={shard}/4",
                "--coverage.thresholds.lines=0",
                "--coverage.thresholds.branches=0",
                "--coverage.thresholds.functions=0",
                "--coverage.thresholds.statements=0",
            ],
        ),
        (
            "weekly-test-durations.yml",
            "refresh-shard",
            "Run the measurable test suite",
            [0, 1, 2, 3],
            "uv",
            [
                "run",
                "pytest",
                "tests/",
                "--no-cov",
                "--ignore=tests/performance",
                "--ignore=tests/chaos",
                "--ignore=tests/test_schemathesis_api.py",
                "--shard-id={shard}",
                "--num-shards=4",
                "--junitxml=pytest-report.xml",
            ],
        ),
    ],
)
def test_shard_commands_preserve_arguments_and_exit_status(
    filename: str,
    job_id: str,
    step_name: str,
    shards: list[int],
    program: str,
    expected: list[str],
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = yaml.safe_load((WORKFLOWS / filename).read_text(encoding="utf-8"))
    job = workflow["jobs"][job_id]
    assert job["strategy"]["matrix"]["shard"] == shards
    step = next(step for step in job["steps"] if step.get("name") == step_name)
    assert step["env"]["SHARD_ID"] == "${{ matrix.shard }}"
    assert "${{" not in step["run"]
    windows_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = (
        str(windows_bash)
        if os.name == "nt" and windows_bash.exists()
        else shutil.which("bash")
    )
    assert bash
    for shard in shards:
        for command_status in (0, 31):
            monkeypatch.delenv("BASH_ENV", raising=False)
            monkeypatch.delenv("ENV", raising=False)
            monkeypatch.setenv("SHARD_ID", str(shard))
            monkeypatch.setenv("MOCK_STATUS", str(command_status))
            script = (
                f'{program}() {{ printf "%s\\n" "$@"; return "$MOCK_STATUS"; }}\n'
                + step["run"]
            )
            completed = pytester.run(
                bash, "--noprofile", "--norc", "-e", "-c", script, timeout=20
            )
            assert completed.ret == command_status, completed.stderr.lines
            assert completed.outlines == [
                value.format(shard=shard) for value in expected
            ]
