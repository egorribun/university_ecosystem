"""Contracts for diagnostic Squawk JSON from both historical SQL files."""

from __future__ import annotations

import hashlib
import json
import os
import re
import runpy
import secrets
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"
OPAQUE_ERROR = "AUD148 Squawk JSON: scanner output cannot be safely published"
PRIVATE_ERROR = "AUD148 Squawk JSON: scanner output contains private runtime context"
PRIVATE_PATH_ERROR = "AUD148 Squawk JSON: SQL path contains private runtime context"
pytest_plugins = ("pytester",)


def _steps():
    job = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"][
        "alembic-migrations"
    ]
    ordinary = next(
        step for step in job["steps"] if step.get("id") == "migration-squawk"
    )
    expanded = next(
        step for step in job["steps"] if step.get("id") == "migration-ddl-evidence"
    )
    return job, ordinary, expanded


def _args(run):
    match = re.search(r"squawk_args=\(\n(.*?)\n\)", run, re.DOTALL)
    assert match is not None
    return shlex.split(match.group(1))


def _collector(run):
    opening = "<<'AUD148_JSON' || capture_status=$?\n"
    closing = "\nAUD148_JSON\n"
    assert opening in run, "both raw gates need a subsequent Squawk JSON collector"
    assert closing in run.split(opening, 1)[1]
    return run.split(opening, 1)[1].split(closing, 1)[0]


def test_workflow_captures_same_files_after_both_unchanged_raw_gates() -> None:
    job, ordinary, expanded = _steps()
    ordinary_run, expanded_run = ordinary["run"], expanded["run"]
    raw = '"$squawk_binary_path" "${squawk_args[@]}" "$sql_file"'
    assert ordinary_run.count(raw) == expanded_run.count(raw) == 1
    assert ordinary_run.rstrip().endswith(raw + '\ndone <<< "$changed_files"')
    assert expanded_run.rstrip().endswith('exit "$lint_status"')
    assert '"$sql_file" > "$lint_log" 2>&1 || lint_status=$?' in expanded_run
    raw_status = 'raw_expanded_exit="$lint_status"'
    assert raw_status in expanded_run
    assert expanded_run.index(raw) < expanded_run.index(raw_status)
    assert expanded_run.index(raw_status) < expanded_run.index(
        'print_bounded "$lint_log" 131072'
    )
    assert 'AUD148_RAW_EXPANDED_EXIT="$raw_expanded_exit"' in expanded_run
    assert 'print_bounded "$lint_log" 131072' in expanded_run
    assert "<<'AUD148_JSON'" in expanded_run, "Squawk JSON collector is missing"
    assert expanded_run.index(raw) < expanded_run.index("<<'AUD148_JSON'")
    assert ordinary_run.index("aud148_ordinary_sql=") < ordinary_run.index(raw)
    assert ordinary_run.index("aud148_ordinary_sha256=") < ordinary_run.index(raw)
    assert ordinary_run.index("aud148_ordinary_identity=") < ordinary_run.index(raw)
    assert expanded["env"]["AUD148_ORDINARY_SQL"] == (
        "${{ steps.migration-squawk.outputs.aud148_ordinary_sql }}"
    )
    assert expanded["env"]["AUD148_ORDINARY_SHA256"] == (
        "${{ steps.migration-squawk.outputs.aud148_ordinary_sha256 }}"
    )
    assert expanded["env"]["AUD148_ORDINARY_IDENTITY"] == (
        "${{ steps.migration-squawk.outputs.aud148_ordinary_identity }}"
    )
    assert expanded["env"]["AUD148_RAW_ORDINARY_EXIT"] == (
        "${{ steps.migration-squawk.outputs.aud148_ordinary_exit }}"
    )
    assert 'if [[ -n "$AUD148_ORDINARY_SQL" ]]; then' in expanded_run
    assert "AUD148_SQUAWK_JSON_SKIPPED" in expanded_run
    assert (
        'if [[ "$lint_status" -eq 0 && "$capture_status" -ne 0 ]]; then' in expanded_run
    )
    assert 'exit "$capture_status"' in expanded_run
    assert _args(ordinary_run) == _args(expanded_run)
    assert "continue-on-error" not in ordinary
    assert "continue-on-error" not in expanded
    assert "continue-on-error" not in job
    assert "always()" not in expanded["if"]
    assert "steps.migration-squawk.outcome == 'failure'" in expanded["if"]
    _collector(expanded_run)


def _identity(path):
    stat = path.stat()
    return f"{stat.st_dev}:{stat.st_ino}"


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def capture(tmp_path, monkeypatch):
    _, ordinary, expanded = _steps()
    script = tmp_path / "collector.py"
    script.write_text(_collector(expanded["run"]), encoding="utf-8")
    binary = tmp_path / "verified binary"
    binary.write_bytes(b"synthetic binary")
    files = (tmp_path / "ordinary input.sql", tmp_path / "expanded input.sql")
    files[0].write_bytes('BEGIN;\nSELECT "λ";\nCOMMIT;\n'.encode())
    files[1].write_bytes(b"-- DIAGNOSTIC ONLY:\nBEGIN;\nCOMMIT;\n")
    args = _args(ordinary["run"])
    monkeypatch.setattr(
        sys, "argv", [str(script), str(binary), *map(str, files), *args]
    )
    environment = {
        "AUD148_ORDINARY_SHA256": _digest(files[0]),
        "AUD148_ORDINARY_IDENTITY": _identity(files[0]),
        "AUD148_EXPANDED_SHA256": _digest(files[1]),
        "AUD148_EXPANDED_IDENTITY": _identity(files[1]),
        "AUD148_SQUAWK_BINARY_EXPECTED_SHA256": _digest(binary),
        "AUD148_SQUAWK_BINARY_SHA256": _digest(binary),
        "AUD148_SQUAWK_VERSION": "squawk 2.67.0",
        "AUD148_CHECKOUT_SHA": "a" * 40,
        "GITHUB_SHA": "a" * 40,
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_JOB": "alembic-migrations",
        "ORIGINAL_SQUAWK_OUTCOME": "failure",
        "AUD148_RAW_ORDINARY_EXIT": "1",
        "AUD148_RAW_EXPANDED_EXIT": "1",
        "SECRET_KEY": secrets.token_urlsafe(32),
        "DATABASE_URL": "private-database-for-capture-test",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    payloads = [
        '[{"rule_name":"one","message":"λ","help":"details","line":0,"column":7}]\n'.encode(),
        b'[{"rule_name":"two","message":"distinct finding","line":1,"column":2}]\n',
    ]
    errors = [b"", b""]
    statuses = [1, 1]
    calls = []
    monkeypatch.setitem(
        sys.modules,
        "resource",
        SimpleNamespace(RLIMIT_FSIZE=42, setrlimit=lambda _kind, _value: None),
    )

    def fake_run(argv, *, stdout, stderr, timeout, check, preexec_fn):
        index = len(calls)
        calls.append(argv)
        assert timeout > 0
        assert check is False
        assert callable(preexec_fn)
        stdout.write(payloads[index])
        stderr.write(errors[index])
        return SimpleNamespace(returncode=statuses[index])

    monkeypatch.setattr(subprocess, "run", fake_run)
    return script, binary, files, args, environment, payloads, errors, statuses, calls


def _report(output):
    opening, closing = "AUD148_SQUAWK_JSON_BEGIN\n", "\nAUD148_SQUAWK_JSON_END\n"
    assert output.startswith(opening)
    assert output.endswith(closing)
    return json.loads(output[len(opening) : -len(closing)])


def test_collector_runs_both_scans_and_retains_complete_diagnostics(capture, capsys):
    script, binary, files, args, env, payloads, errors, statuses, calls = capture
    runpy.run_path(str(script), run_name="__main__")
    output = capsys.readouterr().out
    report = _report(output)
    assert calls == [
        [str(binary), *args, "--reporter", "json", str(path)] for path in files
    ]
    assert report["status"] == "diagnostic-only-not-an-exception"
    assert report["checkout_sha"] == env["GITHUB_SHA"]
    assert report["workflow_run_id"] == "123"
    assert report["workflow_run_attempt"] == "2"
    assert report["original_squawk_outcome"] == "failure"
    assert report["raw_ordinary_exit"] == 1
    assert report["raw_expanded_exit"] == 1
    assert report["squawk_version"] == "squawk 2.67.0"
    assert report["squawk_binary_sha256"] == _digest(binary)
    assert report["squawk_args"] == args
    assert [item["scenario"] for item in report["captures"]] == [
        "ordinary-parent-live",
        "expanded-populated-diagnostic",
    ]
    for index, item in enumerate(report["captures"]):
        assert item["sql_path"] == str(files[index])
        assert item["sql_sha256"] == _digest(files[index])
        assert item["sql_bytes"] == files[index].stat().st_size
        assert item["sql_identity"] == _identity(files[index])
        assert item["exit_code"] == statuses[index]
        assert item["stdout"].encode() == payloads[index]
        assert item["stderr"].encode() == errors[index]
    assert len(output.encode()) < 262144
    assert not any(line.startswith("::") for line in output.splitlines())
    assert env["SECRET_KEY"] not in output
    assert env["DATABASE_URL"] not in output
    assert "equivalent" not in output


@pytest.mark.parametrize(
    "case",
    [
        "ordinary_digest",
        "ordinary_identity",
        "expanded_digest",
        "expanded_identity",
        "same_file",
        "sql_missing",
        "sql_too_large",
        "binary_changed",
        "scanner_version",
        "checkout_mismatch",
        "invalid_run",
        "invalid_ordinary_exit",
        "private_context",
        "changed_arguments",
    ],
)
def test_collector_rejects_invalid_provenance_before_scanning(
    case, capture, monkeypatch, capsys
):
    script, binary, files, _, env, _, _, _, calls = capture
    changes = {
        "ordinary_digest": ("AUD148_ORDINARY_SHA256", "0" * 64),
        "ordinary_identity": ("AUD148_ORDINARY_IDENTITY", "0:0"),
        "expanded_digest": ("AUD148_EXPANDED_SHA256", "0" * 64),
        "expanded_identity": ("AUD148_EXPANDED_IDENTITY", "0:0"),
        "scanner_version": ("AUD148_SQUAWK_VERSION", "squawk 2.67.1"),
        "checkout_mismatch": ("GITHUB_SHA", "b" * 40),
        "invalid_run": ("GITHUB_RUN_ATTEMPT", "01"),
        "invalid_ordinary_exit": ("AUD148_RAW_ORDINARY_EXIT", "999"),
    }
    if case in changes:
        monkeypatch.setenv(*changes[case])
    elif case == "same_file":
        sys.argv[3] = str(files[0])
    elif case == "sql_missing":
        files[0].unlink()
    elif case == "sql_too_large":
        files[0].write_bytes(b"x" * 65537)
        monkeypatch.setenv("AUD148_ORDINARY_SHA256", _digest(files[0]))
    elif case == "binary_changed":
        binary.write_bytes(b"other binary")
    elif case == "private_context":
        files[0].write_text(env["SECRET_KEY"], encoding="utf-8")
        monkeypatch.setenv("AUD148_ORDINARY_SHA256", _digest(files[0]))
    else:
        sys.argv[-1] = "another-rule"
    with pytest.raises(SystemExit, match="AUD148 Squawk JSON"):
        runpy.run_path(str(script), run_name="__main__")
    assert capsys.readouterr().out == ""
    assert calls == []


@pytest.mark.parametrize("case", ["scanner_error", "error_diagnostic"])
def test_collector_keeps_errors_as_diagnostics_but_fails(case, capture, capsys):
    script, _, _, _, _, payloads, errors, statuses, calls = capture
    if case == "scanner_error":
        statuses[0] = 2
    else:
        payloads[0] = b'[{"level":"Error","message":"invalid SQL"}]\n'
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(script), run_name="__main__")
    assert exc.value.code != 0
    report = _report(capsys.readouterr().out)
    assert len(calls) == 2
    assert report["captures"][0]["stdout"].encode() == payloads[0]
    assert report["captures"][0]["stderr"].encode() == errors[0]
    assert report["captures"][0]["exit_code"] == statuses[0]


@pytest.mark.parametrize(
    "invalid_json",
    [
        b"not JSON\n",
        b'[{"level":"Error","level":"Warning"}]',
        b'[{"message":"first","message":"second"}]',
        b'[{"line":NaN}]',
        b'[{"line":Infinity}]',
        b'[{"line":-Infinity}]',
        b'[{"line":1e999}]',
    ],
    ids=[
        "malformed",
        "duplicate-level",
        "duplicate-field",
        "nan",
        "infinity",
        "negative-infinity",
        "numeric-overflow",
    ],
)
def test_collector_rejects_unpublishable_json_without_raw_output(
    invalid_json, capture, monkeypatch, capsys
):
    script, _, _, _, _, payloads, _, statuses, calls = capture
    payloads[0] = invalid_json
    statuses[:] = [0, 0]
    monkeypatch.setenv("ORIGINAL_SQUAWK_OUTCOME", "success")
    monkeypatch.setenv("AUD148_RAW_ORDINARY_EXIT", "0")
    monkeypatch.setenv("AUD148_RAW_EXPANDED_EXIT", "0")

    with pytest.raises(SystemExit, match="AUD148 Squawk JSON") as exc:
        runpy.run_path(str(script), run_name="__main__")
    assert len(calls) == 2
    assert str(exc.value) == OPAQUE_ERROR
    output = capsys.readouterr()
    assert output.out == output.err == ""


def test_collector_refuses_oversized_output(capture, capsys):
    script, _, _, _, _, payloads, _, _, _ = capture
    payloads[0] = b"x" * 131073
    with pytest.raises(SystemExit, match="AUD148 Squawk JSON"):
        runpy.run_path(str(script), run_name="__main__")
    output = capsys.readouterr()
    assert output.out == output.err == ""


@pytest.mark.parametrize("target", ["sql", "binary"])
def test_collector_rechecks_inputs_after_each_scan(
    target, capture, monkeypatch, capsys
):
    script, binary, files, _, _, _, _, _, calls = capture
    original_run = subprocess.run

    def changing_run(*args, **kwargs):
        result = original_run(*args, **kwargs)
        (files[0] if target == "sql" else binary).write_bytes(b"changed during scan")
        return result

    monkeypatch.setattr(subprocess, "run", changing_run)
    with pytest.raises(SystemExit, match="AUD148 Squawk JSON"):
        runpy.run_path(str(script), run_name="__main__")
    assert len(calls) == 1
    output = capsys.readouterr()
    assert output.out == output.err == ""


def test_collector_rejects_private_context_in_decoded_scanner_output(
    capture, monkeypatch, capsys
):
    script, _, _, _, _, payloads, _, _, _ = capture
    private = "private λ token"
    monkeypatch.setenv("SECRET_KEY", private)
    payloads[0] = json.dumps([{"message": private}], ensure_ascii=True).encode()
    with pytest.raises(SystemExit, match="AUD148 Squawk JSON") as exc:
        runpy.run_path(str(script), run_name="__main__")
    assert str(exc.value) == PRIVATE_ERROR
    output = capsys.readouterr()
    assert output.out == output.err == ""


@pytest.mark.parametrize("escaped", ['"', "\\", "\n"])
@pytest.mark.parametrize("location", ["value", "key"])
@pytest.mark.parametrize("private_name", ["SECRET_KEY", "DATABASE_URL"])
def test_collector_rejects_json_escaped_private_context(
    private_name, escaped, location, capture, monkeypatch, capsys
):
    script, _, _, _, _, payloads, _, _, calls = capture
    private = secrets.token_urlsafe(16) + escaped + secrets.token_urlsafe(16)
    monkeypatch.setenv(private_name, private)
    nested = {private: "detail"} if location == "key" else {"detail": private}
    payloads[0] = json.dumps([{"nested": [nested]}], ensure_ascii=True).encode()

    with pytest.raises(SystemExit, match="AUD148 Squawk JSON") as exc:
        runpy.run_path(str(script), run_name="__main__")
    assert len(calls) == 1
    assert str(exc.value) == PRIVATE_ERROR
    output = capsys.readouterr()
    assert output.out == output.err == ""


@pytest.mark.parametrize("defect", ["truncated", "duplicate"])
@pytest.mark.parametrize("private_name", ["SECRET_KEY", "DATABASE_URL"])
def test_collector_never_reports_private_context_in_unpublishable_json(
    private_name, defect, capture, monkeypatch, capsys
):
    script, _, _, _, _, payloads, _, _, calls = capture
    private = secrets.token_urlsafe(16) + '"' + secrets.token_urlsafe(16)
    monkeypatch.setenv(private_name, private)
    encoded = json.dumps(private)
    suffix = "" if defect == "truncated" else ',"message":"safe"}]'
    payloads[0] = ('[{"message":' + encoded + suffix).encode()

    with pytest.raises(SystemExit, match="AUD148 Squawk JSON") as exc:
        runpy.run_path(str(script), run_name="__main__")
    assert len(calls) == 2
    assert str(exc.value) == OPAQUE_ERROR
    output = capsys.readouterr()
    assert output.out == output.err == ""


@pytest.mark.parametrize("escaped", ['"', "\\"])
@pytest.mark.parametrize("private_name", ["SECRET_KEY", "DATABASE_URL"])
def test_collector_rejects_private_context_in_json_encoded_stderr(
    private_name, escaped, capture, monkeypatch, capsys
):
    script, _, _, _, _, _, errors, _, _ = capture
    private = secrets.token_urlsafe(16) + escaped + secrets.token_urlsafe(16)
    monkeypatch.setenv(private_name, private)
    errors[0] = json.dumps({"detail": private}).encode()

    with pytest.raises(SystemExit, match="AUD148 Squawk JSON") as exc:
        runpy.run_path(str(script), run_name="__main__")
    assert str(exc.value) == OPAQUE_ERROR
    output = capsys.readouterr()
    assert output.out == output.err == ""


@pytest.mark.parametrize("scenario", [0, 1], ids=["ordinary", "expanded"])
def test_collector_keeps_nonempty_stderr_opaque(scenario, capture, capsys):
    script, _, _, _, _, _, errors, _, calls = capture
    errors[scenario] = b"untrusted scanner diagnostic\n"

    with pytest.raises(SystemExit, match="AUD148 Squawk JSON") as exc:
        runpy.run_path(str(script), run_name="__main__")
    assert len(calls) == 2
    assert str(exc.value) == OPAQUE_ERROR
    output = capsys.readouterr()
    assert output.out == output.err == ""


@pytest.mark.parametrize("scenario", [0, 1], ids=["ordinary", "expanded"])
@pytest.mark.parametrize("private_name", ["SECRET_KEY", "DATABASE_URL"])
def test_collector_rejects_private_context_in_reported_sql_path(
    private_name, scenario, capture, monkeypatch, capsys
):
    script, _, files, _, _, _, _, _, _ = capture
    private = secrets.token_urlsafe(24)
    renamed = files[scenario].with_name(private + ".sql")
    files[scenario].rename(renamed)
    sys.argv[2 + scenario] = str(renamed)
    monkeypatch.setenv(private_name, private)

    with pytest.raises(SystemExit, match="AUD148 Squawk JSON") as exc:
        runpy.run_path(str(script), run_name="__main__")
    assert str(exc.value) == PRIVATE_PATH_ERROR
    output = capsys.readouterr()
    assert output.out == output.err == ""


def test_each_json_scanner_gets_a_hard_output_file_limit(capture, monkeypatch, capsys):
    script, _, _, _, _, _, _, _, calls = capture
    original_run = subprocess.run
    limits = []
    resource = SimpleNamespace(
        RLIMIT_FSIZE=42,
        setrlimit=lambda kind, value: limits.append((kind, value)),
    )
    monkeypatch.setitem(sys.modules, "resource", resource)

    def limited_run(*args, preexec_fn=None, **kwargs):
        assert callable(preexec_fn), "scanner process must have a hard file-size limit"
        preexec_fn()
        return original_run(*args, preexec_fn=preexec_fn, **kwargs)

    monkeypatch.setattr(subprocess, "run", limited_run)
    runpy.run_path(str(script), run_name="__main__")
    _report(capsys.readouterr().out)
    assert len(calls) == 2
    assert limits == [(42, (131073, 131073))] * 2


def _trap_fragment(run, name):
    opening = f"# AUD148_ORDINARY_{name}_BEGIN\n"
    closing = f"# AUD148_ORDINARY_{name}_END\n"
    assert opening in run, f"ordinary scanner {name} receipt is missing"
    assert closing in run.split(opening, 1)[1]
    return run.split(opening, 1)[1].split(closing, 1)[0]


@pytest.mark.parametrize(
    ("commands", "expected_exit", "expected_receipt", "output_is_directory"),
    [
        ("historical:17", 17, "17", False),
        ("historical:0", 0, "0", False),
        ("historical:0 other:23", 23, "0", False),
        ("other:23 historical:0", 23, None, False),
        ("historical:17", 17, None, True),
        ("historical:0", 0, None, True),
        ("historical:0 other:23", 23, None, True),
    ],
)
def test_ordinary_scanner_exit_receipt_never_changes_the_gate(
    commands,
    expected_exit,
    expected_receipt,
    output_is_directory,
    tmp_path,
    monkeypatch,
    pytester,
):
    _, ordinary, _ = _steps()
    reset = _trap_fragment(ordinary["run"], "TRAPS_RESET")
    install = _trap_fragment(ordinary["run"], "TRAPS_INSTALL")
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = (
        str(git_bash) if os.name == "nt" and git_bash.exists() else shutil.which("bash")
    )
    assert bash, "Bash is required to verify the workflow's shell exit semantics"
    output_path = tmp_path / "github-output"
    if output_is_directory:
        output_path.mkdir()
    script = f"""set -euo pipefail
for item in {commands}; do
{reset}
  IFS=: read -r kind code <<< "$item"
  if [[ "$kind" == historical ]]; then
{install}
  fi
  printf 'RAW_STDOUT %s\\n' "$code"
  printf 'RAW_STDERR %s\\n' "$code" >&2
  (exit "$code")
done
"""
    monkeypatch.setenv("GITHUB_OUTPUT", output_path.as_posix())
    result = pytester.run(bash, "-c", script, timeout=10)
    assert result.ret == expected_exit
    assert result.stdout.str().count("RAW_STDOUT") == (
        2 if commands == "historical:0 other:23" else 1
    )
    assert result.stderr.str().count("RAW_STDERR") == (
        2 if commands == "historical:0 other:23" else 1
    )
    if expected_receipt is None:
        assert output_is_directory or not output_path.exists()
    else:
        assert output_path.read_text() == f"aud148_ordinary_exit={expected_receipt}\n"


def test_scanner_child_setup_failure_is_sanitized(capture, monkeypatch, capsys):
    script, _, _, _, _, _, _, _, _ = capture

    def failed_setup(*_args, **_kwargs):
        raise subprocess.SubprocessError("private child setup details")

    monkeypatch.setattr(subprocess, "run", failed_setup)
    with pytest.raises(SystemExit, match="AUD148 Squawk JSON") as exc:
        runpy.run_path(str(script), run_name="__main__")
    assert "private child setup details" not in str(exc.value)
    assert capsys.readouterr().out == ""


def test_successful_ordinary_step_cannot_report_a_failed_raw_scan(
    capture, monkeypatch, capsys
):
    script, _, _, _, _, _, _, _, calls = capture
    monkeypatch.setenv("ORIGINAL_SQUAWK_OUTCOME", "success")
    monkeypatch.setenv("AUD148_RAW_ORDINARY_EXIT", "17")
    with pytest.raises(SystemExit, match="AUD148 Squawk JSON"):
        runpy.run_path(str(script), run_name="__main__")
    assert calls == []
    assert capsys.readouterr().out == ""


def test_failed_ordinary_step_can_follow_a_successful_raw_scan(
    capture, monkeypatch, capsys
):
    script, _, _, _, _, _, _, _, _ = capture
    monkeypatch.setenv("AUD148_RAW_ORDINARY_EXIT", "0")
    runpy.run_path(str(script), run_name="__main__")
    report = _report(capsys.readouterr().out)
    assert report["original_squawk_outcome"] == "failure"
    assert report["raw_ordinary_exit"] == 0
