"""Behavioral coverage for source-bound, value-free delivery-case evidence."""

from __future__ import annotations

import importlib
import json
import runpy
import sys
from types import SimpleNamespace

import pytest


def _module():
    try:
        return importlib.import_module("scripts.aud154_receipt")
    except ModuleNotFoundError:
        pytest.fail("the source-bound AUD-154 receipt validator must exist")


def _record(project="desktop", **changes):
    return {
        "schema": 1,
        "case_id": "aud154-sent-confirmation",
        "project": project,
        "final_status": "passed",
        "expected_status": "passed",
        "outcome": "expected",
        "attempts": ["passed"],
        "retry": 0,
        "skipped": False,
        **changes,
    }


def _line(record=None, *, retained=False):
    prefix = "live E2E AUD154 " if retained else "UE_LIVE_AUD154_V1 "
    return prefix + json.dumps(record or _record(), separators=(",", ":")) + "\n"


def _summary():
    return (
        _line(retained=True)
        + _line(_record("mobile"), retained=True)
        + _line(_record(case_id="aud154-enter-sent-confirmation"), retained=True)
        + _line(
            _record("mobile", case_id="aud154-enter-sent-confirmation"), retained=True
        )
        + "live E2E counts passed=18\nlive E2E outcome=passed exit_code=0\n"
    )


def test_parser_preserves_named_case_identity_and_drops_unrelated_content():
    module = _module()
    assert module.project_case_records("private-password\n" + _line()) == [_record()]


@pytest.mark.parametrize(
    "change",
    [
        {"schema": True},
        {"case_id": "private"},
        {"project": "desktop\nprivate"},
        {"retry": True},
        {"retry": 2},
        {"attempts": []},
        {"attempts": ["passed", "passed"]},
        {"final_status": "failed"},
        {"skipped": 0},
        {"skipped": True},
        {"unexpected": "private"},
        {"outcome": "private"},
        {"expected_status": "private"},
    ],
)
def test_parser_rejects_untrusted_fields_and_inconsistent_results(change):
    assert _module().project_case_records(_line(_record(**change))) == []


@pytest.mark.parametrize(
    "defect",
    [
        "truncated",
        "duplicate_key",
        "duplicate_case",
        "overflow",
        "ansi",
        "cr",
        "suffix",
        "invalid_row",
    ],
)
def test_parser_rejects_ambiguous_or_injected_receipts(defect):
    line = _line()
    bad = {
        "truncated": line[:-1],
        "duplicate_key": line.replace('"schema":1', '"schema":1,"schema":1'),
        "duplicate_case": line + line,
        "overflow": line.replace('"schema":1', '"schema":1' + " " * 1024),
        "ansi": "\x1b[31m" + line,
        "cr": "private\r" + line,
        "suffix": line[:-1] + " private\n",
        "invalid_row": line + "UE_LIVE_AUD154_V1 invalid\n",
    }[defect]
    assert _module().project_case_records(bad) == []


def test_real_redaction_boundary_retains_only_the_valid_stdout_records(
    tmp_path, monkeypatch, capsys
):
    from scripts import live_stand

    monkeypatch.setattr(
        live_stand.fast_preflight,
        "run_check",
        lambda *a, **kw: SimpleNamespace(
            status="passed",
            exit_code=0,
            stdout=_line() + _line(_record("mobile")) + "private-body\n  16 passed\n",
            stderr="private-error\n" + _line(),
        ),
    )
    live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    output = capsys.readouterr()
    assert _module().project_case_records(output.out, retained=True) == [
        _record(),
        _record("mobile"),
    ]
    assert "private" not in output.out
    assert output.err == ""


def _git(root, *args):
    from scripts import fast_preflight

    result = fast_preflight.run_check(
        fast_preflight.CheckSpec("fixture-git", ("git", *args)),
        repo_root=root,
        timeout_seconds=10,
        include_output=True,
    )
    assert result.status == "passed", result.stderr
    return result.stdout.strip()


def _repo(tmp_path):
    module = _module()
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Receipt tests")
    _git(root, "config", "user.email", "receipt@example.invalid")
    for name in module.SOURCE_PATHS:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("source-bound fixture\n")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "test fixture")
    sha = _git(root, "rev-parse", "HEAD")
    return root, {"GITHUB_SHA": sha, "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}


def test_receipt_binds_both_projects_to_same_pre_and_post_source(tmp_path):
    module = _module()
    root, env = _repo(tmp_path)
    before = module.source_snapshot(root, env)
    receipt = module.build_receipt(
        _summary(), before, root=root, environment=env, exit_code="0"
    )
    assert receipt["accepted"] is True
    assert receipt["evidence_scope"] == "current-live-button-and-enter-cases-only"
    assert receipt["original_criterion_satisfied"] is False
    assert (
        receipt["original_case_title"]
        == "shows delivery confirmation after message is sent"
    )
    assert receipt["expected_projects"] == ["desktop", "mobile"]
    assert receipt["tested_commit"] == env["GITHUB_SHA"]
    assert receipt["source_tree"] == _git(root, "rev-parse", "HEAD^{tree}")
    assert receipt["run_id"] == 123 and receipt["run_attempt"] == 1
    assert [(case["case_id"], case["project"]) for case in receipt["cases"]] == [
        ("aud154-enter-sent-confirmation", "desktop"),
        ("aud154-enter-sent-confirmation", "mobile"),
        ("aud154-sent-confirmation", "desktop"),
        ("aud154-sent-confirmation", "mobile"),
    ]
    assert receipt["schema"] == "ue-aud154-named-case-receipt-v2"
    assert (
        receipt["case_titles"]["aud154-sent-confirmation"]
        == "a message is delivered, edited, and tombstoned in the other authenticated session"
    )
    assert set(receipt["bindings"]) == set(module.SOURCE_PATHS)
    for binding in receipt["bindings"].values():
        assert len(binding["blob"]) == 40 and len(binding["sha256"]) == 64
    assert "private" not in json.dumps(receipt)


@pytest.mark.parametrize(
    "defect",
    ["missing", "duplicate", "skip", "retry", "expected_failure", "counts", "process"],
)
def test_receipt_never_accepts_incomplete_skipped_retried_or_failed_cases(
    tmp_path, defect
):
    module = _module()
    root, env = _repo(tmp_path)
    before = module.source_snapshot(root, env)
    summary = _summary()
    if defect == "missing":
        summary = summary.replace(_line(_record("mobile"), retained=True), "")
    if defect == "duplicate":
        summary += _line(retained=True)
    if defect == "skip":
        summary = summary.replace(
            _line(retained=True),
            _line(
                _record(
                    final_status="skipped",
                    attempts=["skipped"],
                    skipped=True,
                    outcome="skipped",
                ),
                retained=True,
            ),
        )
    if defect == "retry":
        summary = summary.replace(
            _line(retained=True),
            _line(
                _record(attempts=["failed", "passed"], retry=1, outcome="flaky"),
                retained=True,
            ),
        )
    if defect == "expected_failure":
        summary = summary.replace(
            '"expected_status":"passed"', '"expected_status":"failed"'
        )
    if defect == "counts":
        summary = summary.replace("passed=18", "passed=15 skipped=1")
    receipt = module.build_receipt(
        summary,
        before,
        root=root,
        environment=env,
        exit_code="1" if defect == "process" else "0",
    )
    assert receipt["accepted"] is False


@pytest.mark.parametrize(
    "defect",
    [
        "dirty",
        "changed_commit",
        "wrong_sha",
        "wrong_run",
        "bad_binding",
        "extra_field",
        "symlink",
    ],
)
def test_binding_rejects_source_drift_and_untrusted_metadata(tmp_path, defect):
    module = _module()
    root, env = _repo(tmp_path)
    before = module.source_snapshot(root, env)
    source = root / module.SOURCE_PATHS[0]
    if defect in {"dirty", "changed_commit"}:
        source.write_text("changed source\n")
        if defect == "changed_commit":
            _git(root, "add", ".")
            _git(root, "commit", "-qm", "changed source")
    if defect == "wrong_sha":
        env["GITHUB_SHA"] = "a" * 40
    if defect == "wrong_run":
        env["GITHUB_RUN_ID"] = "124"
    if defect == "bad_binding":
        before["bindings"][module.SOURCE_PATHS[0]]["sha256"] = "a" * 64
    if defect == "extra_field":
        before["private"] = "secret"
    if defect == "symlink":
        source.unlink()
        source.symlink_to(root / module.SOURCE_PATHS[1])
    with pytest.raises(ValueError, match="AUD-154"):
        module.build_receipt(
            _summary(), before, root=root, environment=env, exit_code="0"
        )


def test_workflow_adds_a_separate_source_bound_receipt_without_weakening_the_18_case_guard():
    from tests.test_aud429_live_workflow import REUSABLE, _step, _workflow

    steps = _workflow(REUSABLE)["jobs"]["live-realtime-visual"]["steps"]
    names = [step.get("name") for step in steps]
    assert "Bind AUD-154 source before execution" in names
    assert names.index("Bind AUD-154 source before execution") < names.index(
        "Start the owned full live stand"
    )
    assert (
        "scripts.aud154_receipt snapshot"
        in _step("Bind AUD-154 source before execution")["run"]
    )
    realtime = _step("Exercise real realtime sessions without skips")
    assert '"live E2E counts passed=18"' in realtime["run"]
    assert '"live E2E outcome=passed exit_code=0"' in realtime["run"]
    assert "exit_code=$run_result" in realtime["run"]
    receipt = _step("Validate AUD-154 named-case receipt")
    assert "scripts.aud154_receipt receipt" in receipt["run"]
    assert "steps.realtime.outputs.exit_code" in receipt["env"]["REALTIME_EXIT_CODE"]
    assert "!cancelled()" in receipt["if"]
    assert "steps.realtime.outcome != 'skipped'" in receipt["if"]
    assert "continue-on-error" not in receipt
    upload = _step("Upload AUD-154 named-case receipt")
    assert upload["with"]["path"] == "${{ runner.temp }}/aud154-named-case-receipt.json"
    assert upload["with"]["if-no-files-found"] == "error"
    assert "github.sha" in upload["with"]["name"]
    assert "raw" not in upload["with"]["path"]


def test_snapshot_checks_blob_bytes_even_when_git_status_hides_a_change(tmp_path):
    module = _module()
    root, env = _repo(tmp_path)
    name = module.SOURCE_PATHS[0]
    _git(root, "update-index", "--assume-unchanged", name)
    (root / name).write_text("changed bytes hidden from status\n")
    assert not _git(root, "status", "--porcelain", "--untracked-files=no")
    with pytest.raises(ValueError, match="AUD-154"):
        module.source_snapshot(root, env)


def test_snapshot_rejects_committed_symlink_and_non_repository(tmp_path):
    module = _module()
    root, env = _repo(tmp_path)
    source = root / module.SOURCE_PATHS[0]
    source.unlink()
    source.symlink_to("fixtures.ts")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "symlink fixture")
    env["GITHUB_SHA"] = _git(root, "rev-parse", "HEAD")
    with pytest.raises(ValueError, match="AUD-154"):
        module.source_snapshot(root, env)
    with pytest.raises(ValueError, match="AUD-154"):
        module.source_snapshot(tmp_path, env)


def test_snapshot_rejects_invalid_tree_output(tmp_path, monkeypatch):
    module = _module()
    root, env = _repo(tmp_path)
    original = module._git
    monkeypatch.setattr(
        module,
        "_git",
        lambda root, *args: "private-tree"
        if args == ("rev-parse", "HEAD^{tree}")
        else original(root, *args),
    )
    with pytest.raises(ValueError, match="AUD-154"):
        module.source_snapshot(root, env)


@pytest.mark.parametrize(
    "field,value",
    [("GITHUB_SHA", ""), ("GITHUB_RUN_ID", "private"), ("GITHUB_RUN_ATTEMPT", "0")],
)
def test_snapshot_rejects_invalid_environment(tmp_path, field, value):
    module = _module()
    root, env = _repo(tmp_path)
    env[field] = value
    with pytest.raises(ValueError, match="AUD-154"):
        module.source_snapshot(root, env)


def test_cli_snapshot_receipt_failure_and_exclusive_output(
    tmp_path, monkeypatch, capsys
):
    module = _module()
    root, env = _repo(tmp_path)
    monkeypatch.chdir(root)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    before = tmp_path / "before.json"
    raw = tmp_path / "raw.txt"
    output = tmp_path / "receipt.json"
    monkeypatch.setattr(sys, "argv", ["aud154", "snapshot", "--output", str(before)])
    assert module.main() == 0
    raw.write_text("private-runtime-value\n" + _summary())
    argv = [
        "aud154",
        "receipt",
        "--before",
        str(before),
        "--input",
        str(raw),
        "--exit-code",
        "0",
        "--output",
        str(output),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert module.main() == 0
    value = output.read_text()
    assert json.loads(value)["accepted"] is True
    assert "private" not in value
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 1
    assert output.read_text() == value
    assert capsys.readouterr().err == "AUD-154 source or receipt validation failed\n"
    output.unlink()
    raw.write_text(_summary().replace("passed=18", "passed=15"))
    assert module.main() == 1
    assert json.loads(output.read_text())["accepted"] is False
    monkeypatch.setattr(sys, "argv", ["aud154", "receipt", "--output", str(output)])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 1


def test_module_entry_point_uses_same_fail_closed_cli(tmp_path, monkeypatch, capsys):
    module = _module()
    monkeypatch.setattr(
        sys, "argv", ["aud154", "receipt", "--output", str(tmp_path / "missing.json")]
    )
    with pytest.raises(SystemExit) as error:
        runpy.run_path(module.__file__, run_name="__main__")
    assert error.value.code == 1
    assert capsys.readouterr().err == "AUD-154 source or receipt validation failed\n"


@pytest.mark.parametrize("field", ["run_id", "run_attempt"])
def test_receipt_rejects_boolean_source_identity(tmp_path, field):
    module = _module()
    root, env = _repo(tmp_path)
    env["GITHUB_RUN_ID"] = "1"
    before = module.source_snapshot(root, env)
    before[field] = True
    with pytest.raises(ValueError):
        module.build_receipt(
            _summary(), before, root=root, environment=env, exit_code="0"
        )


def test_source_binding_uses_native_git_objects_without_a_legacy_digest_api(
    tmp_path, monkeypatch
):
    module = _module()
    root, env = _repo(tmp_path)

    def disabled_digest(*args, **kwargs):
        raise ValueError("legacy digest API unavailable")

    monkeypatch.setattr(module.hashlib, "sha1", disabled_digest)
    snapshot = module.source_snapshot(root, env)
    for name, binding in snapshot["bindings"].items():
        assert binding["blob"] == _git(root, "hash-object", "--no-filters", "--", name)


def test_blob_binding_rejects_a_buffer_different_from_committed_file(
    tmp_path, monkeypatch
):
    module = _module()
    root, env = _repo(tmp_path)
    target = root / module.SOURCE_PATHS[0]
    original_read = module.Path.read_bytes

    def changed_buffer(path):
        return b"different observed bytes\n" if path == target else original_read(path)

    monkeypatch.setattr(module.Path, "read_bytes", changed_buffer)
    with pytest.raises(ValueError):
        module.source_snapshot(root, env)


@pytest.mark.parametrize("defect", ["launch", "timeout", "failed", "encoding"])
def test_source_binding_rejects_native_git_hash_failures(tmp_path, monkeypatch, defect):
    module = _module()
    root, env = _repo(tmp_path)

    def rejected_hash(*args, **kwargs):
        assert args[0] == ("git", "hash-object", "--stdin")
        assert kwargs["input"] == b"source-bound fixture\n"
        if defect == "encoding":
            return SimpleNamespace(stdout=b"\xff")
        if defect == "timeout":
            raise module.subprocess.TimeoutExpired("git", 30)
        if defect == "failed":
            raise module.subprocess.CalledProcessError(1, "git")
        raise OSError("unavailable")

    monkeypatch.setattr(module.subprocess, "run", rejected_hash)
    with pytest.raises(ValueError, match="source or receipt validation failed"):
        module.source_snapshot(root, env)


@pytest.mark.parametrize("project", ["desktop", "mobile"])
@pytest.mark.parametrize(
    "defect", ["missing", "duplicate", "skip", "retry", "teardown"]
)
def test_enter_case_must_independently_pass_once(tmp_path, project, defect):
    module = _module()
    root, env = _repo(tmp_path)
    before = module.source_snapshot(root, env)
    original = _record(project, case_id="aud154-enter-sent-confirmation")
    replacement = dict(original)
    if defect == "skip":
        replacement.update(
            final_status="skipped",
            attempts=["skipped"],
            skipped=True,
            outcome="skipped",
        )
    if defect == "retry":
        replacement.update(attempts=["failed", "passed"], retry=1, outcome="flaky")
    if defect == "teardown":
        replacement.update(
            final_status="failed", attempts=["failed"], outcome="unexpected"
        )
    line = _line(original, retained=True)
    changed = (
        ""
        if defect == "missing"
        else line * 2
        if defect == "duplicate"
        else _line(replacement, retained=True)
    )
    receipt = module.build_receipt(
        _summary().replace(line, changed),
        before,
        root=root,
        environment=env,
        exit_code="0",
    )
    assert receipt["accepted"] is False


def test_parser_preserves_distinct_case_ids_within_one_project():
    enter = _record(case_id="aud154-enter-sent-confirmation")
    assert _module().project_case_records(_line() + _line(enter)) == [_record(), enter]


def test_historical_button_only_projection_cannot_satisfy_v2_receipt(tmp_path):
    module = _module()
    root, env = _repo(tmp_path)
    before = module.source_snapshot(root, env)
    historical = (
        _line(retained=True)
        + _line(_record("mobile"), retained=True)
        + "live E2E counts passed=16\nlive E2E outcome=passed exit_code=0\n"
    )
    receipt = module.build_receipt(
        historical, before, root=root, environment=env, exit_code="0"
    )
    assert receipt["schema"] == "ue-aud154-named-case-receipt-v2"
    assert receipt["accepted"] is False
    assert receipt["original_criterion_satisfied"] is False
    assert receipt["case_titles"]["aud154-enter-sent-confirmation"] == (
        "shows sent confirmation after the server accepts the message"
    )
