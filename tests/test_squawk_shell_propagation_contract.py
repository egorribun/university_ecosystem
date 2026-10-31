"""Execute the migration lint step with controlled external commands.

These tests do not run migrations or admit a database. They exercise the actual
workflow shell body; only Actions interpolation and the test scanner's checksum
are substituted to model the runner and an executable under test control.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import runpy
import secrets
import shutil
import subprocess
import sys
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


@pytest.fixture
def diagnostic_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pytester):
    job = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )["jobs"]["alembic-migrations"]
    step = next(
        step for step in job["steps"] if step.get("id") == "migration-ddl-evidence"
    )
    script = step["run"]

    binary_dir = tmp_path / "bin"
    runner_temp = tmp_path / "runner"
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    scanner = (
        runner_temp
        / "university-ecosystem-tools/squawk/v2.67.0/linux-x64/squawk-linux-x64"
    )
    _executable(
        scanner,
        """#!/usr/bin/env bash
set -eu
if [[ "${1:-}" == --version ]]; then
  printf 'squawk 2.67.0\\n'
  exit 0
fi
printf 'RAW_SCANNER_RAN\\n'
if [[ -n "${TEST_SCANNER_TEXT:-}" ]]; then printf '%s\\n' "$TEST_SCANNER_TEXT"; fi
exit "$TEST_SCANNER_EXIT"
""",
    )
    _executable(
        binary_dir / "git",
        """#!/usr/bin/env bash
set -eu
[[ "$1" == rev-parse && "$2" == HEAD ]] || exit 91
printf 'controlled-checkout\\n'
""",
    )
    _executable(
        binary_dir / "uv",
        """#!/usr/bin/env bash
set -eu
if [[ "$1" == run && "$2" == pytest ]]; then
  exit "$TEST_PYTEST_EXIT"
elif [[ "$1" == run && "$2" == python && "$3" == - ]]; then
  if [[ "$4" == .pytest_tmp/aud148-expanded ]]; then
    mkdir -p "$4"
    if [[ "${TEST_PREPARED_ARTIFACTS:-0}" != 1 ]]; then
      printf 'SELECT 1;\\n' > "$4/expanded.sql"
      printf '{}\\n' > "$4/trace.json"
    fi
    printf '%s\\0%s\\0' "$4/expanded.sql" "$4/trace.json" > "$5"
  elif [[ "$4" == *squawk-linux-x64 ]]; then
    printf 'COLLECTOR_RAN\\n'
    exit "$TEST_COLLECTOR_EXIT"
  elif [[ "${5:-}" == 131072 && ( "${6:-}" == log || "${6:-}" == metadata ) ]]; then
    shift 2
    exec "$TEST_PYTHON_EXECUTABLE" "$@"
  elif [[ "${TEST_RUN_METADATA:-0}" == 1 ]]; then
    shift 2
    exec "$TEST_PYTHON_EXECUTABLE" "$@"
  fi
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
    script_path = tmp_path / "actual-diagnostic-step.sh"
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
    monkeypatch.setenv("AUD148_ORDINARY_SQL", "controlled-ordinary.sql")
    monkeypatch.setenv("TEST_PYTHON_EXECUTABLE", Path(sys.executable).as_posix())
    for name in ("TEST_PREPARED_ARTIFACTS", "TEST_RUN_METADATA", "TEST_SCANNER_TEXT"):
        monkeypatch.delenv(name, raising=False)

    def run(
        scanner_exit: int,
        collector_exit: int,
        pytest_exit: int = 0,
        *,
        quiet: bool = False,
    ):
        monkeypatch.setenv("TEST_SCANNER_EXIT", str(scanner_exit))
        monkeypatch.setenv("TEST_COLLECTOR_EXIT", str(collector_exit))
        monkeypatch.setenv("TEST_PYTEST_EXIT", str(pytest_exit))
        args = _bash_command(bash, script_path)
        if quiet:
            process = pytester.popen(args, stdin=None)
            try:
                stdout, stderr = process.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                pytest.fail("diagnostic shell timed out", pytrace=False)
            return process.returncode, stdout.decode(), stderr.decode()
        return pytester.run(*args, timeout=20)

    return run


@pytest.mark.parametrize(
    ("scanner_exit", "collector_exit", "expected"),
    [(0, 0, 0), (23, 0, 23), (0, 17, 17), (23, 17, 23)],
)
def test_diagnostic_step_propagates_raw_and_collector_failures(
    diagnostic_gate, scanner_exit: int, collector_exit: int, expected: int
) -> None:
    result = diagnostic_gate(scanner_exit, collector_exit)
    assert result.ret == expected
    assert "RAW_SCANNER_RAN" in result.stdout.str()
    assert "COLLECTOR_RAN" in result.stdout.str()


def test_diagnostic_step_stops_after_failed_focused_tests(diagnostic_gate) -> None:
    result = diagnostic_gate(0, 0, pytest_exit=31)
    assert result.ret == 31
    assert "RAW_SCANNER_RAN" not in result.stdout.str()
    assert "COLLECTOR_RAN" not in result.stdout.str()


@pytest.mark.parametrize("location", ["clean", "sql", "scanner"])
def test_diagnostic_step_does_not_print_private_runtime_context(
    diagnostic_gate, pytester, monkeypatch: pytest.MonkeyPatch, location: str
) -> None:
    canary = secrets.token_urlsafe(24)
    sql = "-- DIAGNOSTIC ONLY: synthetic evidence\nSELECT 1;\n"
    if location == "sql":
        sql += f"SELECT '{canary}';\n"
    artifacts = pytester.path / ".pytest_tmp/aud148-expanded"
    artifacts.mkdir(parents=True)
    (artifacts / "expanded.sql").write_text(sql, encoding="utf-8", newline="\n")
    sources = {
        "alembic/versions/148642dd1207_fix_missing_tables.py": b"migration\n",
        "tests/helpers/migration_148642dd1207_trace.py": b"helper\n",
        "tests/integration/test_migration_148642dd1207.py": b"fixture\n",
        ".github/workflows/ci.yml": b"workflow\n",
        "scripts/quality/render_live_alembic_sql.py": b"renderer\n",
        ".squawk.toml": b"config\n",
        "uv.lock": b"lockfile\n",
    }
    for name, content in sources.items():
        path = pytester.path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    migration = sources["alembic/versions/148642dd1207_fix_missing_tables.py"]
    blob_header = b"blob " + str(len(migration)).encode("ascii") + b"\0"
    statement = "ALTER TABLE public.fixture ADD COLUMN marker integer"
    evidence = {
        "status": "diagnostic-only-not-an-exception",
        "migration_blob": hashlib.sha1(
            blob_header + migration, usedforsecurity=False
        ).hexdigest(),
        "helper_sha256": hashlib.sha256(b"helper\n").hexdigest(),
        "fixture_sha256": hashlib.sha256(b"fixture\n").hexdigest(),
        "workflow_sha": "controlled-workflow",
        "workflow_run_id": "1",
        "postgres_version": "controlled-postgresql",
        "expanded_sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
        "nested_ddl": [
            {
                "outer_ordinal": 1,
                "site": "synthetic_site",
                "sql": statement,
                "sql_sha256": hashlib.sha256(statement.encode()).hexdigest(),
            }
        ],
    }
    (artifacts / "trace.json").write_text(json.dumps(evidence), encoding="utf-8")
    monkeypatch.setenv("TEST_PREPARED_ARTIFACTS", "1")
    monkeypatch.setenv("TEST_RUN_METADATA", "1")
    monkeypatch.setenv("TEST_PYTHON_EXECUTABLE", Path(sys.executable).as_posix())
    monkeypatch.setenv("ORIGINAL_SQUAWK_OUTCOME", "failure")
    monkeypatch.setenv("SECRET_KEY", canary)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    if location == "scanner":
        monkeypatch.setenv("TEST_SCANNER_TEXT", canary)

    scanner_exit = 23 if location == "scanner" else 0
    status, stdout, stderr = diagnostic_gate(scanner_exit, 17, quiet=True)
    markers = (
        "AUD148_EXPANDED_SQL_BEGIN",
        "RAW_SCANNER_RAN",
        "COLLECTOR_RAN",
    )
    if status != (23 if scanner_exit else 17) or not all(
        marker in stdout for marker in markers
    ):
        pytest.fail(
            "diagnostic shell did not reach the expected boundaries", pytrace=False
        )
    if canary in stdout or canary in stderr:
        pytest.fail(
            "diagnostic output exposed synthetic private context", pytrace=False
        )


@pytest.mark.parametrize(
    "case",
    ["clean", "private-log", "private-metadata", "escaped-metadata", "oversized"],
)
def test_diagnostic_printer_checks_bounds_and_private_forms_before_output(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    job = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )["jobs"]["alembic-migrations"]
    step = next(
        step for step in job["steps"] if step.get("id") == "migration-ddl-evidence"
    )
    opening = "<<'AUD148_PRINT'\n"
    assert step["run"].count(opening) == 1, "one bounded privacy printer is required"
    body = step["run"].split(opening, 1)[1]
    body = body.split("\nAUD148_PRINT\n", 1)[0]
    script = tmp_path / "printer.py"
    script.write_text(body, encoding="utf-8")
    input_path = tmp_path / "diagnostic.log"

    def invoke(data: bytes, mode: str):
        input_path.write_bytes(data)
        monkeypatch.setattr(sys, "argv", [str(script), str(input_path), "131072", mode])
        status = 0
        try:
            runpy.run_path(str(script), run_name="__main__")
        except SystemExit as error:
            status = error.code
        finally:
            output = capsys.readouterr()
        return status, output.out, output.err

    monkeypatch.setenv("SECRET_KEY", "")
    monkeypatch.setenv("DATABASE_URL", "")
    clean = "PUBLIC_DIAGNOSTIC\nПривет\n".encode()
    status, stdout, stderr = invoke(clean, "metadata")
    assert status == 0
    assert stdout.encode() == clean
    assert stderr == ""
    if case == "clean":
        return

    canary = secrets.token_urlsafe(24)
    private = f'postgresql://{canary}/"Привет"\n'
    monkeypatch.setenv("SECRET_KEY", "" if case == "private-metadata" else private)
    monkeypatch.setenv("DATABASE_URL", private if case == "private-metadata" else "")
    mode = "metadata" if "metadata" in case else "log"
    if case == "oversized":
        prefix = b"PARTIAL_OUTPUT_MUST_NOT_BE_PRINTED\n"
        payload = prefix + b"x" * (131073 - len(prefix))
    elif case == "escaped-metadata":
        payload = json.dumps({"sql": private}, ensure_ascii=True).encode()
    else:
        payload = b"PUBLIC_BEFORE\n" + private.encode() + b"PUBLIC_AFTER\n"
    status, stdout, stderr = invoke(payload, mode)
    opaque = canary not in stdout + stderr
    assert opaque, "diagnostic printer exposed synthetic private context"
    assert status == 1
    assert stderr == ""
    if case == "oversized":
        assert "PARTIAL_OUTPUT_MUST_NOT_BE_PRINTED" not in stdout
        assert stdout == "::error::AUD148 diagnostic output exceeded its byte limit\n"
        monkeypatch.setenv("SECRET_KEY", canary)
        monkeypatch.setenv("DATABASE_URL", "")
        payload = b"x" * (131072 - len(canary)) + canary.encode()
        status, stdout, stderr = invoke(payload, "log")
        opaque = canary not in stdout + stderr
        assert opaque, "bounded redaction exposed synthetic private context"
        assert status == 1
        assert stdout == "::error::AUD148 diagnostic output exceeded its byte limit\n"
        assert stderr == ""
    elif mode == "metadata":
        assert stdout == (
            "AUD148_DIAGNOSTIC_METADATA_BEGIN\n"
            "AUD148_OMITTED_PRIVATE_RUNTIME_CONTEXT\n"
            "AUD148_DIAGNOSTIC_METADATA_END\n"
            "AUD148_EXPANDED_SQL_BEGIN\n"
            "AUD148_OMITTED_PRIVATE_RUNTIME_CONTEXT\n"
            "AUD148_EXPANDED_SQL_END\n"
        )
    else:
        assert stdout.startswith("AUD148_DIAGNOSTIC_OUTPUT_REDACTED_NOT_RAW\n")
        assert "PUBLIC_BEFORE" in stdout
        assert "PUBLIC_AFTER" in stdout
        monkeypatch.setenv("SECRET_KEY", "REDACTED")
        monkeypatch.setenv("DATABASE_URL", "")
        status, stdout, stderr = invoke(b"REDACTED\n", "log")
        assert status == 1
        assert stdout == "AUD148_DIAGNOSTIC_OUTPUT_OMITTED\n"
        assert stderr == ""
        monkeypatch.setenv("DATABASE_URL", "OMITTED")
        status, stdout, stderr = invoke(b"REDACTED\n", "log")
        assert status == 1
        assert stdout == ""
        assert stderr == ""


def test_private_diagnostics_fail_after_successful_raw_scan_and_collector(
    diagnostic_gate, monkeypatch: pytest.MonkeyPatch
) -> None:
    canary = secrets.token_urlsafe(24)
    monkeypatch.setenv("SECRET_KEY", canary)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("TEST_SCANNER_TEXT", canary)
    status, stdout, stderr = diagnostic_gate(0, 0, quiet=True)
    opaque = canary not in stdout + stderr
    assert opaque, "diagnostic output exposed synthetic private context"
    assert status == 1
    assert "RAW_SCANNER_RAN" in stdout
    assert "COLLECTOR_RAN" in stdout
    assert "AUD148_EXPANDED_SQUAWK_EXIT=0" in stdout
    assert "AUD148_DIAGNOSTIC_OUTPUT_REDACTED_NOT_RAW" in stdout
