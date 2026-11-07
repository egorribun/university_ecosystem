"""Execute the migration lint step with controlled external commands.

These tests do not run migrations or admit a database. They exercise the actual
workflow shell body; only runner-provided environment values and the test
scanner's checksum are controlled to model the runner and an executable under
test control.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
pytest_plugins = ("pytester",)
DIFF_FILTER = "--diff-filter=ACMR "
MigrationGate = Callable[..., tuple[int, list[str]]]


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


def _lint_step_script() -> str:
    job = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )["jobs"]["alembic-migrations"]
    step = next(step for step in job["steps"] if step.get("id") == "migration-squawk")
    return str(step["run"])


@pytest.fixture
def migration_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pytester: pytest.Pytester
) -> MigrationGate:
    job = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )["jobs"]["alembic-migrations"]
    lint_step = next(
        step for step in job["steps"] if step.get("id") == "migration-squawk"
    )
    assert (
        lint_step["env"]["PR_BASE_SHA"] == "${{ github.event.pull_request.base.sha }}"
    )
    script = str(lint_step["run"])

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
arguments=("$@")
unset 'arguments[-1]'
expected=()
if [[ "$name" == "202611020000_mvp_baseline.sql" ]]; then
  expected=(--exclude require-concurrent-index-creation
            --exclude constraint-missing-not-valid
            --exclude adding-foreign-key-constraint
            --exclude prefer-text-field
            --exclude prefer-bigint-over-int)
fi
[[ "${arguments[*]}" == "${expected[*]}" ]] || exit 93
printf '%s\\n' "$name" >> "$TEST_SCAN_LOG"
if [[ "$name" == "${TEST_SCANNER_FAIL:-}" ]]; then exit 23; fi
""",
    )
    # Models `git diff --name-only [--diff-filter=X] BASE...HEAD`: each status
    # class is emitted only when the filter selects it, as real git does.
    _executable(
        binary_dir / "git",
        """#!/usr/bin/env bash
set -eu
if [[ "$1" == ls-tree ]]; then
  path="${@: -1}"
  if [[ "$2" == "-r" ]]; then
    printf '%s\\n' "${TEST_ALL_MODES:-100644}"
  elif [[ "$path" == "alembic/versions" ]]; then
    printf '%s\\n' "${TEST_VERSIONS_MODE:-040000}"
  elif [[ "$path" == "${TEST_BAD_MODE_PATH:-}" ]]; then
    printf '%s\\n' "${TEST_BAD_MODE:-120000}"
  else
    printf '100644\\n'
  fi
  exit "${TEST_LS_TREE_EXIT:-0}"
fi
[[ "$1" == diff && "$2" == --name-only ]] || exit 91
filter=""
for argument in "$@"; do
  case "$argument" in
    --diff-filter=*) filter="${argument#--diff-filter=}" ;;
  esac
done
if [[ -z "$filter" || "$filter" == *[ACMR]* ]]; then
  if [[ -n "$TEST_CHANGED_FILES" ]]; then printf '%s\\n' "$TEST_CHANGED_FILES"; fi
fi
if [[ -z "$filter" || "$filter" == *D* ]]; then
  if [[ -n "$TEST_DELETED_FILES" ]]; then printf '%s\\n' "$TEST_DELETED_FILES"; fi
fi
if [[ -z "$filter" || "$filter" == *T* ]]; then
  if [[ -n "$TEST_TYPE_CHANGED_FILES" ]]; then printf '%s\\n' "$TEST_TYPE_CHANGED_FILES"; fi
fi
exit "${TEST_GIT_EXIT:-0}"
""",
    )
    _executable(
        binary_dir / "uv",
        """#!/usr/bin/env bash
set -eu
if [[ "${TEST_FORBID_UV:-0}" == 1 ]]; then exit 99; fi
if [[ "$1" == run && "$2" == python && "$3" == scripts/quality/read_alembic_revision.py ]]; then
  migration="$4"
  name="${migration##*/}"
  revision="${name%.py}"
  # A deleted revision has no file to read; the real reader exits 2 for it.
  if [[ $'\\n'"$TEST_DELETED_FILES"$'\\n' == *$'\\n'"$migration"$'\\n'* ]]; then
    echo "error: cannot read $migration" >&2
    exit 2
  fi
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
    monkeypatch.setenv("PR_BASE_SHA", "controlled-base")
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
        "TEST_DELETED_FILES",
        "TEST_TYPE_CHANGED_FILES",
        "TEST_BAD_MODE_PATH",
        "TEST_BAD_MODE",
        "TEST_FORBID_UV",
        "TEST_VERSIONS_MODE",
        "TEST_LS_TREE_EXIT",
        "TEST_ALL_MODES",
    ):
        monkeypatch.delenv(name, raising=False)

    def run(
        changed_files: Sequence[str],
        deleted_files: Sequence[str] = (),
        *,
        type_changed_files: Sequence[str] = (),
        symlink_files: Sequence[str] = (),
        mutate: Callable[[str], str] | None = None,
    ) -> tuple[int, list[str]]:
        monkeypatch.setenv("TEST_CHANGED_FILES", "\n".join(changed_files))
        monkeypatch.setenv("TEST_DELETED_FILES", "\n".join(deleted_files))
        monkeypatch.setenv("TEST_TYPE_CHANGED_FILES", "\n".join(type_changed_files))
        (pytester.path / "alembic/versions").mkdir(parents=True, exist_ok=True)
        for migration in changed_files:
            file = pytester.path / migration
            file.parent.mkdir(parents=True, exist_ok=True)
            if migration in symlink_files:
                target = file.with_suffix(".target")
                target.write_text("revision = 'fixture'\n", encoding="utf-8")
                file.symlink_to(target.name)
            else:
                file.write_text("revision = 'fixture'\n", encoding="utf-8")
        text = script if mutate is None else mutate(script)
        step_path = tmp_path / "mutated-workflow-step.sh"
        step_path.write_text(text, encoding="utf-8", newline="\n")
        result = pytester.run(*_bash_command(bash, step_path), timeout=20)
        scans = (
            scan_log.read_text(encoding="utf-8").splitlines()
            if scan_log.exists()
            else []
        )
        return result.ret, scans

    return run


FIRST = "alembic/versions/first.py"
SECOND = "alembic/versions/second.py"
DELETED = "alembic/versions/deleted.py"


def test_type_changed_migration_is_rejected_before_metadata_or_render(
    migration_gate: MigrationGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_FORBID_UV", "1")
    status, scans = migration_gate([], type_changed_files=[FIRST])
    assert status not in (0, 99)
    assert scans == []


def test_non_regular_git_object_is_rejected_before_metadata_or_render(
    migration_gate: MigrationGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_BAD_MODE_PATH", FIRST)
    monkeypatch.setenv("TEST_FORBID_UV", "1")
    status, scans = migration_gate([FIRST])
    assert status not in (0, 99)
    assert scans == []


def test_checkout_symlink_is_rejected_before_metadata_or_render(
    migration_gate: MigrationGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_FORBID_UV", "1")
    status, scans = migration_gate([FIRST], symlink_files=[FIRST])
    assert status not in (0, 99)
    assert scans == []


def test_versions_path_must_be_a_git_tree_even_without_changed_migrations(
    migration_gate: MigrationGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_VERSIONS_MODE", "120000")
    monkeypatch.setenv("TEST_FORBID_UV", "1")
    status, scans = migration_gate([])
    assert status not in (0, 99)
    assert scans == []


def test_git_mode_lookup_failure_stops_before_metadata_or_render(
    migration_gate: MigrationGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_LS_TREE_EXIT", "17")
    monkeypatch.setenv("TEST_FORBID_UV", "1")
    status, scans = migration_gate([FIRST])
    assert status == 17
    assert scans == []


def test_nonregular_unchanged_entry_cannot_bypass_the_gate(
    migration_gate: MigrationGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_ALL_MODES", "120000")
    monkeypatch.setenv("TEST_FORBID_UV", "1")
    status, scans = migration_gate([])
    assert status not in (0, 99)
    assert scans == []


def test_lint_step_scans_every_changed_migration_when_all_succeed(
    migration_gate: MigrationGate,
) -> None:
    status, scans = migration_gate([FIRST, SECOND])
    assert status == 0
    assert scans == ["first.sql", "second.sql"]


def test_lint_step_skips_deleted_revisions_and_still_lints_added_ones(
    migration_gate: MigrationGate,
) -> None:
    status, scans = migration_gate([FIRST], deleted_files=[DELETED])
    assert status == 0
    assert scans == ["first.sql"]


def test_lint_step_is_a_no_op_when_only_revisions_were_deleted(
    migration_gate: MigrationGate,
) -> None:
    status, scans = migration_gate([], deleted_files=[DELETED])
    assert status == 0
    assert scans == []


def test_deleted_revision_would_fail_the_lint_without_the_diff_filter(
    migration_gate: MigrationGate,
) -> None:
    """Counterfactual: the filter, not luck, is what keeps deleted files out."""
    script = _lint_step_script()
    assert script.count(DIFF_FILTER) == 1

    status, scans = migration_gate(
        [FIRST],
        deleted_files=[DELETED],
        mutate=lambda text: text.replace(DIFF_FILTER, "", 1),
    )
    # The deleted path is rejected as missing before metadata is read.
    assert status == 1
    assert "first.sql" in scans


def test_lint_step_does_not_erase_an_earlier_scanner_failure(
    migration_gate: MigrationGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_SCANNER_FAIL", "first.sql")
    status, scans = migration_gate([FIRST, SECOND])
    assert status == 23
    assert scans == ["first.sql"]


def test_lint_step_stops_when_renderer_fails(
    migration_gate: MigrationGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_RENDER_FAIL", SECOND)
    status, scans = migration_gate([FIRST, SECOND])
    assert status == 29
    assert scans == ["first.sql"]


def test_lint_step_stops_when_git_emits_a_list_then_fails(
    migration_gate: MigrationGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_GIT_EXIT", "17")
    status, scans = migration_gate([FIRST])
    assert status == 17
    assert scans == []


@pytest.mark.parametrize("mode", ["before", "after"])
def test_lint_step_stops_when_metadata_producer_fails(
    migration_gate: MigrationGate, monkeypatch: pytest.MonkeyPatch, mode: str
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


BASELINE = "alembic/versions/202611020000_mvp_baseline.py"


def test_baseline_exception_is_reset_before_the_next_migration(
    migration_gate: MigrationGate,
) -> None:
    status, scans = migration_gate([BASELINE, SECOND])
    assert status == 0
    assert scans == ["202611020000_mvp_baseline.sql", "second.sql"]


def test_baseline_exception_cannot_be_widened_to_another_path(
    migration_gate: MigrationGate,
) -> None:
    status, scans = migration_gate(
        [SECOND], mutate=lambda text: text.replace(BASELINE, SECOND)
    )
    assert status == 93
    assert scans == []


def test_baseline_exception_cannot_add_an_unapproved_rule(
    migration_gate: MigrationGate,
) -> None:
    status, scans = migration_gate(
        [BASELINE],
        mutate=lambda text: text.replace(
            "--exclude adding-foreign-key-constraint",
            "--exclude adding-foreign-key-constraint --exclude ban-drop-table",
        ),
    )
    assert status == 93
    assert scans == []


def test_global_squawk_configuration_has_no_exclusions() -> None:
    import tomllib

    config = tomllib.loads((ROOT / ".squawk.toml").read_text(encoding="utf-8"))
    assert config == {"excluded_rules": []}


def _run_readiness_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pytester: pytest.Pytester,
    *,
    ready_after: int,
    failure_exit: int,
    silent: bool,
) -> tuple[dict, dict]:
    """Run the actual Actions body against a fake native PostgreSQL probe."""
    import json
    import sys

    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["alembic-migrations"]
    steps = [step for step in job["steps"] if step.get("name") == "Wait for PostgreSQL"]
    assert len(steps) == 1
    assert steps[0]["shell"] == "pwsh"
    assert steps[0]["run"].strip() == (
        "pwsh -NoProfile -File .github/scripts/ci/wait_for_postgres.ps1"
    )
    step_path = tmp_path / "workflow-readiness.ps1"
    readiness_script = (ROOT / ".github/scripts/ci/wait_for_postgres.ps1").read_text(
        encoding="utf-8"
    )
    step_path.write_text(readiness_script, encoding="utf-8", newline="\n")

    state_path = tmp_path / "readiness-state.json"
    state_path.write_text(
        json.dumps(
            {
                "ready_after": ready_after,
                "failure_exit": failure_exit,
                "silent": silent,
                "calls": [],
            }
        ),
        encoding="utf-8",
    )
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "path = Path(os.environ['READINESS_STATE'])\n"
        "state = json.loads(path.read_text(encoding='utf-8'))\n"
        "number = len(state['calls']) + 1\n"
        "ready = state['ready_after'] > 0 and number >= state['ready_after']\n"
        "status = 0 if ready else state['failure_exit']\n"
        "state['calls'].append({'arguments': sys.argv[1:], 'exit': status})\n"
        "path.write_text(json.dumps(state), encoding='utf-8')\n"
        "if not state['silent']:\n"
        "    print('localhost:5432 - accepting connections' if ready else "
        "'localhost:5432 - rejecting connections')\n"
        "sys.exit(status)\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        stub = tmp_path / "pg-isready.cmd"
        stub.write_text(
            '@echo off\n"%READINESS_PYTHON%" "%READINESS_PROBE%" %*\n'
            "exit /b %ERRORLEVEL%\n",
            encoding="utf-8",
        )
    else:
        stub = tmp_path / "pg-isready"
        _executable(
            stub,
            '#!/bin/sh\nexec "$READINESS_PYTHON" "$READINESS_PROBE" "$@"\n',
        )

    harness = tmp_path / "harness.ps1"
    harness.write_text(
        """$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$global:readinessSleeps = [Collections.Generic.List[int]]::new()
function global:pg_isready { & $env:READINESS_STUB @args }
function global:Start-Sleep { param([int]$Seconds) $global:readinessSleeps.Add($Seconds) }
try {
  & $env:READINESS_STEP
  $outcome = 'success'
  $message = ''
} catch {
  $outcome = 'failure'
  $message = $_.Exception.Message
}
$result = [PSCustomObject]@{ outcome=$outcome; message=$message; sleeps=@($global:readinessSleeps) }
Write-Output ('READINESS_RESULT=' + ($result | ConvertTo-Json -Compress -Depth 8))
""",
        encoding="utf-8",
    )
    for name, value in {
        "READINESS_STATE": str(state_path),
        "READINESS_PYTHON": sys.executable,
        "READINESS_PROBE": str(probe),
        "READINESS_STUB": str(stub),
        "READINESS_STEP": str(step_path),
        "XDG_CACHE_HOME": str(tmp_path / "powershell-cache"),
    }.items():
        monkeypatch.setenv(name, value)
    pwsh = shutil.which("pwsh")
    assert pwsh, "PowerShell 7 is required to execute the workflow step"
    result = pytester.run(
        pwsh, "-NoProfile", "-NonInteractive", "-File", str(harness), timeout=40
    )
    assert result.ret == 0, result.outlines + result.errlines
    lines = [line for line in result.outlines if line.startswith("READINESS_RESULT=")]
    assert len(lines) == 1, result.outlines
    return (
        json.loads(lines[0].split("=", 1)[1]),
        json.loads(state_path.read_text(encoding="utf-8")),
    )


@pytest.mark.parametrize(
    ("ready_after", "failure_exit", "silent", "outcome", "calls", "sleeps"),
    [
        pytest.param(1, 2, False, "success", 1, 0, id="ready-first"),
        pytest.param(2, 1, False, "success", 2, 1, id="refused-then-ready"),
        pytest.param(30, 2, False, "success", 30, 29, id="ready-last"),
        pytest.param(0, 1, False, "failure", 30, 30, id="refused-with-stdout"),
        pytest.param(0, 2, False, "failure", 30, 30, id="no-response"),
        pytest.param(0, 3, False, "failure", 30, 30, id="no-attempt"),
        pytest.param(1, 1, True, "success", 1, 0, id="ready-without-stdout"),
    ],
)
def test_postgres_readiness_uses_native_exit_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pytester: pytest.Pytester,
    ready_after: int,
    failure_exit: int,
    silent: bool,
    outcome: str,
    calls: int,
    sleeps: int,
) -> None:
    observed, state = _run_readiness_step(
        tmp_path,
        monkeypatch,
        pytester,
        ready_after=ready_after,
        failure_exit=failure_exit,
        silent=silent,
    )
    assert observed["outcome"] == outcome
    assert len(state["calls"]) == calls
    assert observed["sleeps"] == [1] * sleeps
    assert all(
        call["arguments"] == ["-h", "localhost", "-p", "5432", "-U", "test"]
        for call in state["calls"]
    )
    if outcome == "failure":
        assert observed["message"] == "PostgreSQL was not ready in 30 seconds"
