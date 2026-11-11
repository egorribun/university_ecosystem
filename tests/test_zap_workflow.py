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
TARGET = "https://private-stage.invalid"


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
        "DAST_SECRET_TARGET": TARGET,
    }
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
        "request_header": f"GET {target}/ HTTP/1.1\r\nHost: private-stage.invalid\r\n\r\n",
        "response_header": "HTTP/1.1 200 OK\r\n\r\n",
    }
    (work / "scan/origin-proof.json").write_text(json.dumps(proof))
    return finish_run(work, identity, nonce, 2, target)


def prepared(source, monkeypatch):
    root, env, work, public = source
    m = module()
    monkeypatch.setattr(m, "run_scan", fake_scan)
    m.prepare(root, env, work, public)
    return m, root, env, work, public


def test_publication_bound_across_processes(source, monkeypatch):
    m, root, env, work, public = prepared(source, monkeypatch)
    env.pop("DAST_SECRET_TARGET")
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
    env.pop("DAST_SECRET_TARGET")
    with pytest.raises(ValueError, match="trusted"):
        module().prepare(root, env, work, public)
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
    m.prepare(root, env, work, public)
    import os
    import sys

    process_env = {**os.environ, **env}
    process_env.pop("DAST_SECRET_TARGET")
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
    env["DAST_SECRET_TARGET"] = target
    with pytest.raises(ValueError, match="Invalid ZAP target"):
        module().prepare(root, env, work, public)
    assert not work.exists()


def test_target_is_masked_and_not_left_in_staging_file(source, monkeypatch, capsys):
    _, _, _, work, _ = prepared(source, monkeypatch)
    assert (
        capsys.readouterr().out
        == f"::add-mask::{TARGET}\n::add-mask::private-stage.invalid\n"
    )
    assert not work.with_name(work.name + "-target.txt").exists()


def test_native_runner_keeps_ajax_explicit():
    from scripts.quality.zap_runner import _CONTAINER_ENTRY

    assert "'--ajax-spider'" in _CONTAINER_ENTRY


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
    assert m.main(["prepare", *flags]) == 0
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
        module().prepare(root, env, work, public)


def test_existing_directory_not_reused(source):
    root, env, work, public = source
    work.mkdir()
    with pytest.raises(ValueError, match="fresh"):
        module().prepare(root, env, work, public)


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


def test_dispatch_target_is_read_privately_after_source_verification(
    source, monkeypatch, capsys
):
    root, env, work, public = source
    event = work.parent / "event.json"
    event.write_text(json.dumps({"inputs": {"target_url": TARGET}}))
    env.pop("DAST_SECRET_TARGET")
    env["GITHUB_EVENT_PATH"] = str(event)
    fallback_target = f"https://{secrets.token_hex(8)}.invalid"
    env["DAST_SECRET_TARGET"] = fallback_target
    m = module()
    monkeypatch.setattr(m, "run_scan", fake_scan)
    m.prepare(root, env, work, public)
    assert json.loads((work / "publication.json").read_text())["target"] == TARGET
    assert (
        capsys.readouterr().out
        == f"::add-mask::{TARGET}\n::add-mask::private-stage.invalid\n"
    )


def test_shared_target_preparation_accepts_explicit_environment(tmp_path):
    from scripts.quality.dast_privacy import prepare_target

    target = tmp_path / "target"
    assert (
        prepare_target(
            target, {"GITHUB_EVENT_NAME": "schedule", "DAST_SECRET_TARGET": TARGET}
        )
        == 0
    )
    assert target.read_text() == TARGET


@pytest.mark.parametrize("event_name", ["schedule", "workflow_dispatch"])
def test_empty_dispatch_or_schedule_uses_secret(source, monkeypatch, event_name):
    root, env, work, public = source
    env["GITHUB_EVENT_NAME"] = event_name
    event = Path(env["GITHUB_EVENT_PATH"])
    event.write_text(json.dumps({"inputs": {"target_url": ""}}))
    m = module()
    monkeypatch.setattr(m, "run_scan", fake_scan)
    m.prepare(root, env, work, public)
    assert json.loads((work / "publication.json").read_text())["target"] == TARGET


def test_source_rejection_precedes_event_file_read(source):
    root, env, work, public = source
    env["GITHUB_REF"] = "untrusted"
    env["GITHUB_EVENT_PATH"] = str(work / "missing-event")
    with pytest.raises(ValueError, match="trusted"):
        module().prepare(root, env, work, public)
    assert not work.with_name(work.name + "-target.txt").exists()
