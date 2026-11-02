"""Execute the migration lint step with controlled external commands.

These tests do not run migrations or admit a database. They exercise the actual
workflow shell body; only Actions interpolation and the test scanner's checksum
are substituted to model the runner and an executable under test control.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
pytest_plugins = ("pytester",)


def _executable(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8", newline="\n")
    path.chmod(0o755)


def _bash_command(bash: str, script: Path) -> tuple[str, ...]:
    # Git for Windows may prefer its own git.exe over an extensionless PATH
    # entry. Explicit command-boundary functions keep the doubles portable.
    setup = (
        'git() { "$TEST_BIN/git" "$@"; }\nuv() { "$TEST_BIN/uv" "$@"; }\nsource "$1"'
    )
    return (
        bash,
        "--noprofile",
        "--norc",
        "-c",
        setup,
        "workflow-test",
        script.as_posix(),
    )


@pytest.fixture
def migration_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pytester):
    job = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )["jobs"]["alembic-migrations"]
    step = next(step for step in job["steps"] if step.get("id") == "migration-squawk")
    script = step["run"]

    binary_dir = tmp_path / "bin"
    runner_temp = tmp_path / "runner"
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    scan_log = tmp_path / "scanned"
    scanner = (
        runner_temp
        / "university-ecosystem-tools/squawk/v2.67.0/linux-x64/squawk-linux-x64"
    )
    _executable(
        scanner,
        """#!/usr/bin/env bash
set -eu
sql="${@: -1}"
name="${sql##*/}"
printf '%s\\n' "$name" >> "$TEST_SCAN_LOG"
if [[ "$name" == "${TEST_SCANNER_FAIL:-}" ]]; then exit 23; fi
""",
    )
    _executable(
        binary_dir / "git",
        """#!/usr/bin/env bash
set -eu
[[ "$1" == diff && "$2" == --name-only ]] || exit 91
printf '%s\\n' "$TEST_CHANGED_FILES"
exit "${TEST_GIT_EXIT:-0}"
""",
    )
    _executable(
        binary_dir / "uv",
        """#!/usr/bin/env bash
set -eu
if [[ "$1" == run && "$2" == python && "$3" == scripts/quality/read_alembic_revision.py ]]; then
  migration="$4"
  name="${migration##*/}"
  revision="${name%.py}"
  if [[ "$migration" == "${TEST_METADATA_FAIL:-}" && "${TEST_METADATA_MODE:-}" == before ]]; then exit 19; fi
  printf '%s parent\\n' "$revision"
  if [[ "$migration" == "${TEST_METADATA_FAIL:-}" ]]; then exit 19; fi
elif [[ "$1" == run && "$2" == python && "$3" == -m && "$4" == scripts.quality.render_live_alembic_sql ]]; then
  migration="$5"
  if [[ "$migration" == "${TEST_RENDER_FAIL:-}" ]]; then exit 29; fi
  printf 'SELECT 1;\\n' > "$6"
else
  exit 92
fi
""",
    )

    digest = hashlib.sha256(scanner.read_bytes()).hexdigest()
    script, substitutions = re.subn(
        r'(?m)^expected_sha256="[0-9a-f]{64}"$',
        f'expected_sha256="{digest}"',
        script,
    )
    assert substitutions == 1
    expression = "${{ github.event.pull_request.base.sha }}"
    assert script.count(expression) == 1
    script = script.replace(expression, "controlled-base")
    script_path = tmp_path / "actual-workflow-step.sh"
    script_path.write_text(script, encoding="utf-8", newline="\n")

    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = (
        str(git_bash) if os.name == "nt" and git_bash.exists() else shutil.which("bash")
    )
    assert bash, "Bash is required to execute the workflow step"
    monkeypatch.setenv("PATH", str(binary_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("TEST_BIN", binary_dir.as_posix())
    monkeypatch.setenv("RUNNER_TEMP", runner_temp.as_posix())
    monkeypatch.setenv("TMPDIR", temp_dir.as_posix())
    monkeypatch.setenv("GITHUB_OUTPUT", (tmp_path / "github-output").as_posix())
    monkeypatch.setenv("TEST_SCAN_LOG", scan_log.as_posix())
    for name in (
        "TEST_GIT_EXIT",
        "TEST_SCANNER_FAIL",
        "TEST_METADATA_FAIL",
        "TEST_METADATA_MODE",
        "TEST_RENDER_FAIL",
    ):
        monkeypatch.delenv(name, raising=False)

    def run(changed_files: list[str]):
        monkeypatch.setenv("TEST_CHANGED_FILES", "\n".join(changed_files))
        result = pytester.run(*_bash_command(bash, script_path), timeout=20)
        scans = (
            scan_log.read_text(encoding="utf-8").splitlines()
            if scan_log.exists()
            else []
        )
        return result.ret, scans

    return run


FIRST = "alembic/versions/first.py"
SECOND = "alembic/versions/second.py"


def test_lint_step_scans_every_changed_migration_when_all_succeed(
    migration_gate,
) -> None:
    status, scans = migration_gate([FIRST, SECOND])
    assert status == 0
    assert scans == ["first.sql", "second.sql"]


def test_lint_step_does_not_erase_an_earlier_scanner_failure(
    migration_gate, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_SCANNER_FAIL", "first.sql")
    status, scans = migration_gate([FIRST, SECOND])
    assert status == 23
    assert scans == ["first.sql"]


def test_lint_step_stops_when_renderer_fails(
    migration_gate, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_RENDER_FAIL", SECOND)
    status, scans = migration_gate([FIRST, SECOND])
    assert status == 29
    assert scans == ["first.sql"]


def test_lint_step_stops_when_git_emits_a_list_then_fails(
    migration_gate, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_GIT_EXIT", "17")
    status, scans = migration_gate([FIRST])
    assert status == 17
    assert scans == []


@pytest.mark.parametrize("mode", ["before", "after"])
def test_lint_step_stops_when_metadata_producer_fails(
    migration_gate, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("TEST_METADATA_FAIL", FIRST)
    monkeypatch.setenv("TEST_METADATA_MODE", mode)
    status, scans = migration_gate([FIRST])
    assert status != 0
    assert scans == []


def test_current_baseline_lint_has_no_retired_admission_or_failure_bypass() -> None:
    job = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )["jobs"]["alembic-migrations"]
    lint = next(step for step in job["steps"] if step.get("id") == "migration-squawk")
    run = lint["run"]
    invocation = '"$squawk_binary_path" "${squawk_args[@]}" "$sql_file"'
    assert run.rstrip().endswith(invocation + '\ndone <<< "$changed_files"')
    assert run.count(invocation) == 1
    assert "|| true" not in run
    assert "continue-on-error" not in job
    assert "continue-on-error" not in lint
    for step in job["steps"]:
        assert step.get("id") not in {
            "migration-squawk-148-ordinary",
            "migration-ddl-evidence",
        }
        assert "scripts.quality.historical148_squawk_admission" not in step.get(
            "run", ""
        )
