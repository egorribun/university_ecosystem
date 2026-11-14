"""Synthetic source and cross-process publication contracts; never scan a target."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import secrets
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "dast_privacy",
    "nuclei_findings_gate",
    "zap_findings_gate",
    "zap_evidence_pipeline",
    "zap_origin_evidence",
    "zap_report_binding",
    "zap_run_provenance",
    "zap_runner",
    "zap_sarif_producer",
    "zap_workflow",
)
TARGET = "http://localhost:20000"
STATUS_LINE = f"LIVE_BASE_URL={TARGET}\n"
MASKS = f"::add-mask::{TARGET}\n::add-mask::localhost:20000\n::add-mask::localhost\n"


def module():
    assert importlib.util.find_spec("scripts.quality.zap_workflow"), (
        "Missing trusted workflow orchestration"
    )
    return importlib.import_module("scripts.quality.zap_workflow")


def command_output(command, **kwargs):
    async def execute():
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **kwargs,
        )
        stdout, stderr = await process.communicate()
        from types import SimpleNamespace

        return SimpleNamespace(
            returncode=process.returncode,
            stdout=stdout.decode(),
            stderr=stderr.decode(),
        )

    return asyncio.run(execute())


def git(root, *args):
    result = command_output([shutil.which("git"), "-C", str(root), *args])
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    for name in MODULES:
        dst = root / f"scripts/quality/{name}.py"
        dst.parent.mkdir(parents=True, exist_ok=True)
        src = ROOT / f"scripts/quality/{name}.py"
        dst.write_bytes(src.read_bytes() if src.exists() else b"# absent candidate\n")
    for name, data in {
        ".github/workflows/dast.yml": b"name: synthetic\n",
        ".zap/rules.tsv": b"# rules\n",
        ".zap/image.txt": b"ghcr.io/zaproxy/zaproxy@sha256:" + b"a" * 64 + b"\n",
    }.items():
        dst = root / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
    git(root, "init", "-q")
    git(root, "add", ".")
    git(
        root,
        "-c",
        "user.name=Synthetic",
        "-c",
        "user.email=synthetic@example.invalid",
        "commit",
        "-qm",
        "fixture",
    )
    event = tmp_path / "event.json"
    event.write_text("{}")
    env = {
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_SHA": git(root, "rev-parse", "HEAD"),
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REPOSITORY": "owner/repository",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
    }
    (tmp_path / "stand-status.txt").write_text(STATUS_LINE, encoding="utf-8")
    return root, env, tmp_path / "private", root / "zap-public"


def test_trusted_source_has_exact_file_hashes(source):
    root, env, _, _ = source
    result = module().verify_source(root, env)
    assert result["identity"]["source_sha"] == env["GITHUB_SHA"]
    assert (
        result["files"]["scripts/quality/zap_workflow.py"]
        == hashlib.sha256(
            (root / "scripts/quality/zap_workflow.py").read_bytes()
        ).hexdigest()
    )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("GITHUB_REF", "refs/heads/other"),
        ("GITHUB_EVENT_NAME", "pull_request"),
        ("GITHUB_SHA", "b" * 40),
        ("GITHUB_RUN_ID", "0"),
        ("GITHUB_RUN_ATTEMPT", "0"),
    ],
)
def test_untrusted_context_rejected(source, key, value):
    root, env, _, _ = source
    env[key] = value
    with pytest.raises(ValueError):
        module().verify_source(root, env)


@pytest.mark.parametrize(
    "name",
    [
        ".github/workflows/dast.yml",
        ".zap/rules.tsv",
        ".zap/image.txt",
        *[f"scripts/quality/{n}.py" for n in MODULES],
    ],
)
def test_changed_source_rejected(source, name):
    root, env, _, _ = source
    with (root / name).open("ab") as out:
        out.write(b"# changed\n")
    with pytest.raises(ValueError):
        module().verify_source(root, env)


async def fake_scan(target_file, rules_file, work, identity, timeout_seconds):
    from scripts.quality.zap_run_provenance import finish_run, start_run

    nonce = start_run(work, identity)
    target = target_file.read_text()
    report = {
        "@version": "2.16.1",
        "site": [{"@name": target, "alerts": [{"pluginid": "10055", "riskcode": "2"}]}],
    }
    (work / "scan/report_json.json").write_text(json.dumps(report))
    proof = {
        "schema_version": 1,
        "message_id": "1",
        "request_header": f"GET {target}/ HTTP/1.1\r\nHost: localhost:20000\r\n\r\n",
        "response_header": "HTTP/1.1 200 OK\r\n\r\n",
    }
    (work / "scan/origin-proof.json").write_text(json.dumps(proof))
    return finish_run(work, identity, nonce, 2, target)


def prepared(source, monkeypatch):
    root, env, work, public = source
    m = module()
    monkeypatch.setattr(m, "run_scan", fake_scan)
    m.prepare(root, env, work, public, root.parent / "stand-status.txt")
    return m, root, env, work, public


def test_publication_bound_across_processes(source, monkeypatch):
    m, root, env, work, public = prepared(source, monkeypatch)
    assert m.verify_publication(root, env, work, public) == [(2, "10055")]
    receipt = json.loads((public / "zap-sarif-provenance.json").read_text())
    assert receipt["identity"]["source_sha"] == env["GITHUB_SHA"]
    assert receipt["coverage_complete"] is False
    assert TARGET not in "".join(p.read_text() for p in public.iterdir())
    assert (work / "publication.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "name",
    [
        "scan/report_json.json",
        "scan/origin-proof.json",
        "receipt.json",
        "publication.json",
    ],
)
def test_private_evidence_tampering_blocks(source, monkeypatch, name):
    m, root, env, work, public = prepared(source, monkeypatch)
    with (work / name).open("ab") as out:
        out.write(b" ")
    with pytest.raises(ValueError):
        m.verify_publication(root, env, work, public)


@pytest.mark.parametrize(
    "name", ["zap-results.sarif", "zap-evidence.txt", "zap-sarif-provenance.json"]
)
def test_public_evidence_tampering_blocks(source, monkeypatch, name):
    m, root, env, work, public = prepared(source, monkeypatch)
    with (public / name).open("ab") as out:
        out.write(b" ")
    with pytest.raises(ValueError):
        m.verify_publication(root, env, work, public)


def test_source_validation_precedes_target_and_scan(source, monkeypatch):
    root, env, work, public = source
    env["GITHUB_REF"] = "refs/heads/untrusted"
    with pytest.raises(ValueError, match="trusted"):
        module().prepare(root, env, work, public, root.parent / "stand-status.txt")
    assert not work.exists()
    assert not public.exists()


@pytest.mark.parametrize("risk", ["0", "1", "2", "3"])
def test_new_cli_process_verifies_and_gates_without_target(source, monkeypatch, risk):
    m = module()

    async def scan(*args):
        await fake_scan(*args)
        work, identity = args[2], args[3]
        from scripts.quality.zap_run_provenance import finish_run

        receipt = json.loads((work / "receipt.json").read_text())
        (work / "receipt.json").unlink()
        report = json.loads((work / "scan/report_json.json").read_text())
        report["site"][0]["alerts"][0]["riskcode"] = risk
        (work / "scan/report_json.json").write_text(json.dumps(report))
        return finish_run(work, identity, receipt["run_nonce"], 2, TARGET)

    monkeypatch.setattr(m, "run_scan", scan)
    root, env, work, public = source
    m.prepare(root, env, work, public, root.parent / "stand-status.txt")
    import os
    import sys

    process_env = {**os.environ, **env}
    command = [sys.executable, "-m", "scripts.quality.zap_workflow"]
    flags = ["--repo-root", str(root), "--work", str(work), "--public", str(public)]
    verified = command_output([*command, "verify", *flags], env=process_env)
    gated = command_output([*command, "gate", *flags], env=process_env)
    assert verified.returncode == 0, verified.stderr
    assert gated.returncode == (1 if int(risk) >= 2 else 0), gated.stderr
    assert TARGET not in verified.stdout + verified.stderr + gated.stdout + gated.stderr


@pytest.mark.parametrize(
    "target",
    [
        "",
        f"https://{secrets.token_urlsafe(12)}:{secrets.token_urlsafe(12)}@example.invalid",
        "https://x.invalid/\n::warning::secret",
        "https://x.invalid/?token=secret",
    ],
    ids=["empty", "randomized-userinfo", "newline", "query-token"],
)
def test_invalid_target_fails_before_creating_private_files(source, target):
    root, env, work, public = source
    (root.parent / "stand-status.txt").write_text(
        f"LIVE_BASE_URL={target}\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Invalid ZAP target"):
        module().prepare(root, env, work, public, root.parent / "stand-status.txt")
    assert not work.exists()


def test_target_is_masked_and_not_left_in_staging_file(source, monkeypatch, capsys):
    _, _, _, work, _ = prepared(source, monkeypatch)
    assert capsys.readouterr().out == MASKS
    assert not work.with_name(work.name + "-target.txt").exists()


def test_native_runner_executes_the_exact_full_scan_command():
    import ast

    from scripts.quality.zap_runner import _CONTAINER_ENTRY

    # The container entry is Python source; inspect its syntax tree so the
    # scan mode, rules file, AJAX spider, timeout and origin hook stay exact.
    tree = ast.parse(_CONTAINER_ENTRY)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "os.execvp"
    ]
    assert len(calls) == 1
    program, argv = calls[0].args
    assert ast.literal_eval(program) == "zap-full-scan.py"
    assert isinstance(argv, ast.List)
    assert [
        element.id if isinstance(element, ast.Name) else ast.literal_eval(element)
        for element in argv.elts
    ] == [
        "zap-full-scan.py",
        "-t",
        "target",
        "-c",
        "/zap/rules.tsv",
        "-J",
        "report_json.json",
        "-a",
        "-j",
        "--ajax-spider",
        "-m",
        "10",
        "-z",
        "-config ajaxSpider.maxDuration=10 -config scanner.maxScanDurationInMins=30",
        "-T",
        "60",
        "--hook=/zap/origin-hook.py",
    ]
    assignments = {
        target.id: ast.unparse(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert assignments == {
        "target": "Path('/zap/target.txt').read_text(encoding='utf-8')"
    }


def test_source_receipt_binds_repository(source):
    root, env, _, _ = source
    env["GITHUB_REPOSITORY"] = "owner/repository"
    assert module().verify_source(root, env)["repository"] == "owner/repository"


@pytest.mark.parametrize("name", ["scripts/__init__.py", "scripts/quality/__init__.py"])
def test_uncommitted_package_initializer_rejected(source, name):
    root, env, _, _ = source
    (root / name).write_text("# uncommitted initializer\n")
    with pytest.raises(ValueError):
        module().verify_source(root, env)


def test_main_commands_and_safe_failure(source, monkeypatch, capsys):
    root, env, work, public = source
    m = module()
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(m, "run_scan", fake_scan)
    flags = ["--repo-root", str(root), "--work", str(work), "--public", str(public)]
    assert (
        m.main(
            ["prepare", *flags, "--status-in", str(root.parent / "stand-status.txt")]
        )
        == 0
    )
    assert m.main(["verify", *flags]) == 0
    assert m.main(["gate", *flags]) == 1
    monkeypatch.setenv("GITHUB_SHA", "not-a-sha")
    assert m.main(["verify", *flags]) == 1
    assert TARGET not in capsys.readouterr().err


def test_module_entrypoint_errors_safely(source, monkeypatch):
    import runpy
    import sys

    root, _, work, public = source
    monkeypatch.setenv("GITHUB_REF", "untrusted")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "zap_workflow",
            "verify",
            "--repo-root",
            str(root),
            "--work",
            str(work),
            "--public",
            str(public),
        ],
    )
    with pytest.raises(SystemExit) as result:
        runpy.run_path(
            str(ROOT / "scripts/quality/zap_workflow.py"), run_name="__main__"
        )
    assert result.value.code == 1


def test_missing_git_rejected(source, monkeypatch):
    root, env, _, _ = source
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(ValueError, match="Git unavailable"):
        module().verify_source(root, env)


@pytest.mark.parametrize("completed", [False, True])
def test_git_cancellation_reaps_process(source, monkeypatch, completed):
    root, _, _, _ = source

    async def interrupted(awaitable, timeout):
        if completed:
            await awaitable
        else:
            awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(asyncio, "wait_for", interrupted)
    with pytest.raises(TimeoutError):
        module()._git(root, "status", "--short")


def test_changed_source_symlink_rejected(source):
    root, env, _, _ = source
    path = root / ".zap/rules.tsv"
    saved = root / ".zap/saved.tsv"
    path.rename(saved)
    path.symlink_to(saved)
    with pytest.raises(ValueError, match="symlinks"):
        module().verify_source(root, env)


@pytest.mark.parametrize("relation", ["inside", "parent", "symlink"])
def test_unsafe_public_paths_rejected(source, relation):
    root, env, work, public = source
    if relation == "inside":
        public = work / "public"
    elif relation == "parent":
        public = work.parent
    else:
        public.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError):
        module().prepare(root, env, work, public, root.parent / "stand-status.txt")


def test_existing_directory_not_reused(source):
    root, env, work, public = source
    work.mkdir()
    with pytest.raises(ValueError, match="fresh"):
        module().prepare(root, env, work, public, root.parent / "stand-status.txt")


def test_wrong_raw_digest_in_manifest_rejected(source, monkeypatch):
    m, root, env, work, public = prepared(source, monkeypatch)
    path = work / "publication.json"
    manifest = json.loads(path.read_text())
    manifest["raw_report_sha256"] = "f" * 64
    path.write_bytes(m._encoded(manifest))
    with pytest.raises(ValueError, match="raw report changed"):
        m.verify_publication(root, env, work, public)


def test_existing_gate_read_error_is_fail_closed(tmp_path, monkeypatch):
    from scripts.quality.zap_findings_gate import ReportError, read_alerts

    path = tmp_path / "report.json"
    path.write_text("{}")

    def unreadable(*args, **kwargs):
        raise OSError("private path")

    monkeypatch.setattr(Path, "open", unreadable)
    with pytest.raises(ReportError, match="Could not read"):
        read_alerts(path)


def test_repository_identity_required(source):
    root, env, _, _ = source
    env.pop("GITHUB_REPOSITORY")
    with pytest.raises(ValueError, match="repository identity"):
        module().verify_source(root, env)


def test_committed_initializer_is_bound(source):
    root, env, _, _ = source
    name = "scripts/__init__.py"
    (root / name).write_text("# committed initializer\n")
    git(root, "add", name)
    git(
        root,
        "-c",
        "user.name=Synthetic",
        "-c",
        "user.email=synthetic@example.invalid",
        "commit",
        "-qm",
        "initializer fixture",
    )
    env["GITHUB_SHA"] = git(root, "rev-parse", "HEAD")
    assert name in module().verify_source(root, env)["files"]


def test_stand_status_is_read_privately_after_source_verification(
    source, monkeypatch, capsys
):
    root, env, work, public = source
    m = module()
    monkeypatch.setattr(m, "run_scan", fake_scan)
    m.prepare(root, env, work, public, root.parent / "stand-status.txt")
    assert json.loads((work / "publication.json").read_text())["target"] == TARGET
    assert capsys.readouterr().out == MASKS


def test_shared_target_preparation_reads_only_the_stand_status(tmp_path):
    from scripts.quality.dast_privacy import prepare_target

    status = tmp_path / "stand-status.txt"
    status.write_text(STATUS_LINE, encoding="utf-8")
    target = tmp_path / "target"
    assert prepare_target(target, status) == 0
    assert target.read_text() == TARGET


def test_prepare_requires_the_owned_stand_status(source, monkeypatch):
    root, env, work, public = source
    m = module()
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(m, "run_scan", fake_scan)
    flags = ["--repo-root", str(root), "--work", str(work), "--public", str(public)]
    assert m.main(["prepare", *flags]) == 1
    assert not work.exists()


def test_scanner_budget_expiry_fails_closed_with_a_specific_message(
    source, monkeypatch, capsys
):
    root, env, work, public = source
    m = module()
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    budgets = []

    async def expired(target_file, rules_file, work, identity, timeout_seconds):
        budgets.append(timeout_seconds)
        raise TimeoutError

    monkeypatch.setattr(m, "run_scan", expired)
    flags = ["--repo-root", str(root), "--work", str(work), "--public", str(public)]
    status = str(root.parent / "stand-status.txt")
    (root.parent / "stand-status.txt").write_text(STATUS_LINE, encoding="utf-8")
    assert m.main(["prepare", *flags, "--status-in", status]) == 1
    assert budgets == [m.SCAN_BUDGET_SECONDS]
    assert 0 < m.SCAN_BUDGET_SECONDS <= 6000
    err = capsys.readouterr().err
    assert "did not finish within its time budget; scan result is unknown." in err
    assert TARGET not in err
    assert not public.exists()


@pytest.mark.parametrize(
    ("exit_code", "error_class", "shown"),
    [
        (3, "ValueError", "3"),
        (137, None, "137"),
        (999, None, "unknown"),
    ],
)
def test_scanner_exit_is_reported_without_scanner_output(
    source, monkeypatch, capsys, exit_code, error_class, shown
):
    root, env, work, public = source
    m = module()
    provenance = importlib.import_module("scripts.quality.zap_run_provenance")
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    async def crashed(target_file, rules_file, work, identity, timeout_seconds):
        raise provenance.ScannerExitError(exit_code, error_class)

    monkeypatch.setattr(m, "run_scan", crashed)
    flags = ["--repo-root", str(root), "--work", str(work), "--public", str(public)]
    status = str(root.parent / "stand-status.txt")
    (root.parent / "stand-status.txt").write_text(STATUS_LINE, encoding="utf-8")
    assert m.main(["prepare", *flags, "--status-in", status]) == 1
    err = capsys.readouterr().err
    assert (
        f"ZAP scanner exited with code {shown}; diagnostic=unknown; scan result is unknown."
        in err
    )
    assert "evidence validation failed" not in err
    assert TARGET not in err
    assert not public.exists()


@pytest.mark.parametrize("event_name", ["schedule", "workflow_dispatch"])
def test_scheduled_and_manual_scans_share_the_owned_stand_target(
    source, monkeypatch, event_name
):
    root, env, work, public = source
    env["GITHUB_EVENT_NAME"] = event_name
    m = module()
    monkeypatch.setattr(m, "run_scan", fake_scan)
    m.prepare(root, env, work, public, root.parent / "stand-status.txt")
    assert json.loads((work / "publication.json").read_text())["target"] == TARGET


def test_source_rejection_precedes_stand_status_read(source):
    root, env, work, public = source
    env["GITHUB_REF"] = "untrusted"
    (root.parent / "stand-status.txt").unlink()
    with pytest.raises(ValueError, match="trusted"):
        module().prepare(root, env, work, public, root.parent / "stand-status.txt")
    assert not work.with_name(work.name + "-target.txt").exists()


@pytest.mark.parametrize(
    ("log", "expected"),
    [
        (
            b"ERROR [Errno 5] Failed to connect to ZAP after 3600 seconds\n",
            "startup_wait_expired",
        ),
        (b"ERROR <class 'private_secret_sentinel'>\n", "scanner_exception"),
        (b"ERROR https://private_secret_sentinel.invalid/\n", "unknown"),
    ],
)
def test_scanner_diagnostics_publish_only_fixed_reason_and_no_success_evidence(
    source, monkeypatch, capsys, log, expected
):
    root, env, work, public = source
    m = module()
    provenance = importlib.import_module("scripts.quality.zap_run_provenance")
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    async def failed_scan(target_file, rules_file, work, identity, timeout_seconds):
        nonce = provenance.start_run(work, identity)
        (work / "stdout.log").write_bytes(log)
        (work / "stderr.log").write_bytes(
            b"Authorization: Bearer private_secret_sentinel\n"
        )
        return provenance.finish_run(work, identity, nonce, 3, TARGET)

    monkeypatch.setattr(m, "run_scan", failed_scan)
    flags = ["--repo-root", str(root), "--work", str(work), "--public", str(public)]
    status = root.parent / "stand-status.txt"
    assert m.main(["prepare", *flags, "--status-in", str(status)]) == 1
    captured = capsys.readouterr()
    assert f"diagnostic={expected}" in captured.err
    assert "scan result is unknown" in captured.err
    assert "private_secret_sentinel" not in captured.out + captured.err
    assert TARGET not in captured.err
    assert not (work / "receipt.json").exists()
    assert not (work / "publication.json").exists()
    assert not public.exists()
    assert m.main(["gate", *flags]) == 1
    assert "scan result is unknown" in capsys.readouterr().err
    assert not public.exists()
