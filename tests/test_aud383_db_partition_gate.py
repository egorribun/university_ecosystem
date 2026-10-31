"""The DB performance gate must stop when partition preparation fails."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/db-perf-gate.yml"


def _run_step(
    tmp_path: Path, step_name: str, failure: str
) -> subprocess.CompletedProcess[str]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["explain-check"]["steps"]
    step = next(item for item in steps if item.get("name") == step_name)
    assert not step.get("continue-on-error", False)

    # The workflow sends a single SQL request via -c. PostgreSQL's psql
    # returns nonzero when that request fails, as it does for client errors.
    stub = r"""
psql() {
    local query="${*: -1}"
    if [[ "$query" == *"CREATE TABLE IF NOT EXISTS"* ]]; then
        printf '%s\n' "$query" >> "$CREATION_LOG"
        case "$FAILURE" in
            client) return 42 ;;
            sql) return 1 ;;
        esac
    else
        printf 'diagnostic\n' >> "$DIAGNOSTIC_LOG"
        if [[ "$FAILURE" == diagnostic_sql ]]; then
            return 1
        fi
    fi
    return 0
}
"""
    candidates = [
        Path("C:/Program Files/Git/bin/bash.exe"),
        Path(shutil.which("bash") or ""),
    ]
    bash = next((str(path.resolve()) for path in candidates if path.is_file()), None)
    assert bash is not None, "Bash is required to exercise the workflow step"
    command = [
        bash,
        "--noprofile",
        "--norc",
        "-e",
        "-o",
        "pipefail",
        "-c",
        stub + step["run"],
    ]
    env = os.environ.copy()
    env.update(
        CREATION_LOG=(tmp_path / "creation.log").as_posix(),
        DIAGNOSTIC_LOG=(tmp_path / "diagnostic.log").as_posix(),
        FAILURE=failure,
    )
    env.pop("BASH_ENV", None)

    async def run() -> subprocess.CompletedProcess[str]:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=tmp_path,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        assert process.returncode is not None
        return subprocess.CompletedProcess(
            command,
            process.returncode,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )

    return asyncio.run(run())


@pytest.mark.parametrize("failure", ["client", "sql"])
def test_partition_preparation_stops_on_client_or_sql_error(
    tmp_path: Path, failure: str
) -> None:
    result = _run_step(tmp_path, "Ensure RANGE partitions exist before pytest", failure)

    assert result.returncode != 0
    log = (tmp_path / "creation.log").read_text(encoding="utf-8")
    assert log.count("CREATE TABLE IF NOT EXISTS data_access_logs_default") == 1
    assert "notifications_default" not in log
    assert not (tmp_path / "diagnostic.log").exists()


@pytest.mark.parametrize(
    "step_name",
    [
        "Diagnose partition state post-migration",
        "Ensure RANGE partitions exist before pytest",
    ],
)
def test_partition_diagnostics_stop_on_sql_error(
    tmp_path: Path, step_name: str
) -> None:
    result = _run_step(tmp_path, step_name, "diagnostic_sql")

    assert result.returncode != 0
    assert (tmp_path / "diagnostic.log").read_text(encoding="utf-8").splitlines() == [
        "diagnostic"
    ]


def test_partition_preparation_success_visits_each_expected_table(
    tmp_path: Path,
) -> None:
    result = _run_step(tmp_path, "Ensure RANGE partitions exist before pytest", "none")

    assert result.returncode == 0, result.stderr
    log = (tmp_path / "creation.log").read_text(encoding="utf-8")
    assert re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)_default", log) == [
        "data_access_logs",
        "notifications",
        "notification_deliveries",
        "failed_login_attempts",
    ]
    assert (tmp_path / "diagnostic.log").read_text(encoding="utf-8").splitlines() == [
        "diagnostic"
    ]
