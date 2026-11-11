"""Offline process-boundary tests; fake Docker never scans or uses a network."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
from pathlib import Path

import pytest

IDENTITY = {
    "source_sha": "a" * 40,
    "run_id": "123",
    "run_attempt": "2",
    "image": "ghcr.io/zaproxy/zaproxy@sha256:" + "b" * 64,
    "rules_sha256": "",
}


@pytest.fixture
def runner_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    executable = binary_dir / "docker"
    executable.write_text("""#!/usr/bin/env python3
import json, os, pathlib, sys, time
args = sys.argv[1:]
with open(os.environ["FAKE_COMMANDS"], "a") as log:
    log.write(json.dumps(args) + "\\n")
if args[:2] == ["rm", "--force"]:
    time.sleep(float(os.environ.get("FAKE_REMOVE_SLEEP", "0")))
    if os.environ.get("FAKE_REMOVED"):
        pathlib.Path(os.environ["FAKE_REMOVED"]).write_text("done")
    sys.exit(int(os.environ.get("FAKE_REMOVE_EXIT", "0")))
if args[0] != "run":
    sys.exit(99)
mounts = [args[i + 1] for i, value in enumerate(args) if value == "--mount"]
scan = next(item.split("src=", 1)[1].split(",", 1)[0] for item in mounts if "dst=/zap/wrk" in item)
target = next(item.split("src=", 1)[1].split(",", 1)[0] for item in mounts if "dst=/zap/target.txt" in item)
print(pathlib.Path(target).read_text(), flush=True)
print("private-zap-marker", file=sys.stderr, flush=True)
if os.environ.get("FAKE_SLEEP"):
    time.sleep(60)
if not os.environ.get("FAKE_NO_REPORT"):
    pathlib.Path(scan, "report_json.json").write_text(json.dumps({"@version":"2.16.1","site":[{"@name": "https://private-zap-marker.invalid", "alerts":[{"pluginid":"10055", "riskcode":"2"}]}]}))
mode = os.environ.get("FAKE_ORIGIN_MODE", "valid")
if mode != "missing":
    authority = "attacker.invalid" if mode == "wrong-origin" else "private-zap-marker.invalid"
    status = "502 Bad Gateway" if mode == "proxy-error" else "302 Found" if mode == "redirect-only" else "200 OK"
    proof = {"schema_version":1,"message_id":"1","request_header":f"GET https://{authority}/ HTTP/1.1\\r\\nHost: {authority}\\r\\n\\r\\n","response_header":f"HTTP/1.1 {status}\\r\\n\\r\\n"}
    pathlib.Path(scan, "origin-proof.json").write_text(json.dumps(proof))
sys.exit(int(os.environ.get("FAKE_EXIT", "2")))
""")
    executable.chmod(0o700)
    monkeypatch.setenv("PATH", str(binary_dir) + ":/usr/bin:/bin")
    commands = tmp_path / "commands.jsonl"
    monkeypatch.setenv("FAKE_COMMANDS", str(commands))
    target, rules = tmp_path / "target.txt", tmp_path / "rules.tsv"
    target.write_text("https://private-zap-marker.invalid")
    rules.write_text("# synthetic rules\n")
    identity = {
        **IDENTITY,
        "rules_sha256": hashlib.sha256(rules.read_bytes()).hexdigest(),
        "hook_sha256": hashlib.sha256(
            (
                Path(__file__).resolve().parents[1]
                / "scripts/quality/zap_origin_evidence.py"
            ).read_bytes()
        ).hexdigest(),
    }
    return target, rules, identity, tmp_path / "run", commands


def _run(inputs, timeout: float = 5):
    spec = importlib.util.find_spec("scripts.quality.zap_runner")
    assert spec is not None, "missing isolated ZAP runner"
    module = importlib.import_module("scripts.quality.zap_runner")
    target, rules, identity, work, _ = inputs
    return asyncio.run(module.run_scan(target, rules, work, identity, timeout))


@pytest.mark.parametrize("exit_code", [0, 1, 2])
def test_completed_process_preserves_findings_and_private_logs(
    runner_inputs, monkeypatch: pytest.MonkeyPatch, capsys, exit_code: int
) -> None:
    monkeypatch.setenv("FAKE_EXIT", str(exit_code))
    receipt = _run(runner_inputs)
    _, _, _, work, commands = runner_inputs
    assert receipt["scanner_exit_code"] == exit_code
    assert (work / "receipt.json").is_file()
    assert "private-zap-marker" in (work / "stdout.log").read_text()
    assert "private-zap-marker" in (work / "stderr.log").read_text()
    assert "private-zap-marker" not in str(receipt)
    captured = capsys.readouterr()
    assert "private-zap-marker" not in captured.out + captured.err
    arguments = json.loads(commands.read_text().splitlines()[0])
    assert "private-zap-marker" not in json.dumps(arguments)
    assert not any(
        "context.json" in item or "receipt.json" in item for item in arguments
    )
    assert not (work / "target.txt").exists()


@pytest.mark.parametrize("exit_code", [3, 125, 127])
def test_scan_errors_never_issue_completion_receipt(
    runner_inputs, monkeypatch: pytest.MonkeyPatch, exit_code: int
) -> None:
    monkeypatch.setenv("FAKE_EXIT", str(exit_code))
    with pytest.raises(ValueError):
        _run(runner_inputs)
    assert not (runner_inputs[3] / "receipt.json").exists()


def test_timeout_cleans_container_and_never_issues_receipt(
    runner_inputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_SLEEP", "1")
    with pytest.raises(TimeoutError):
        _run(runner_inputs, timeout=0.1)
    commands = [json.loads(line) for line in runner_inputs[4].read_text().splitlines()]
    assert any(command[:2] == ["rm", "--force"] for command in commands)
    assert not (runner_inputs[3] / "receipt.json").exists()


def test_missing_report_cannot_become_clean_scan(
    runner_inputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_NO_REPORT", "1")
    with pytest.raises((OSError, ValueError)):
        _run(runner_inputs)
    assert not (runner_inputs[3] / "receipt.json").exists()


def test_changed_rules_stop_before_container(runner_inputs) -> None:
    runner_inputs[1].write_text("changed rules")
    with pytest.raises(ValueError):
        _run(runner_inputs)
    assert not runner_inputs[4].exists()


def test_cancellation_during_cleanup_waits_for_removal(
    runner_inputs, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = importlib.import_module("scripts.quality.zap_runner")
    monkeypatch.setenv("FAKE_SLEEP", "1")
    monkeypatch.setenv("FAKE_REMOVE_SLEEP", "0.3")
    removed = tmp_path / "removed"
    monkeypatch.setenv("FAKE_REMOVED", str(removed))
    target, rules, identity, work, commands = runner_inputs

    async def scenario() -> None:
        task = asyncio.create_task(module.run_scan(target, rules, work, identity, 0.1))
        for _ in range(200):
            if commands.exists() and '"--force"' in commands.read_text():
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("cleanup did not start")
        task.cancel()
        await asyncio.sleep(0.02)
        assert not task.done(), "runner returned before cleanup completed"
        assert (work / "target.txt").exists()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert removed.is_file()
        assert not (work / "target.txt").exists()
        assert not (work / "receipt.json").exists()

    asyncio.run(scenario())


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), 3001])
def test_invalid_timeouts_never_start_container(runner_inputs, timeout: float) -> None:
    with pytest.raises(ValueError):
        _run(runner_inputs, timeout)
    assert not runner_inputs[4].exists()


def test_missing_docker_never_stages_target(
    runner_inputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module("scripts.quality.zap_runner")
    monkeypatch.setattr(module.shutil, "which", lambda _: None)
    with pytest.raises(ValueError, match="Docker is unavailable"):
        _run(runner_inputs)
    assert not runner_inputs[3].exists()


def test_invalid_target_never_starts_container(runner_inputs) -> None:
    runner_inputs[0].write_text("https://private-zap-marker.invalid/?private=query")
    with pytest.raises(ValueError):
        _run(runner_inputs)
    assert not runner_inputs[4].exists()


def test_ambiguous_mount_path_never_starts_container(runner_inputs) -> None:
    inputs = list(runner_inputs)
    inputs[3] = inputs[3].with_name("ambiguous,path")
    with pytest.raises(ValueError):
        _run(inputs)
    assert not runner_inputs[4].exists()


@pytest.mark.parametrize("code", [1, 125])
def test_cleanup_failure_is_not_treated_as_confirmed_removal(
    runner_inputs, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    monkeypatch.setenv("FAKE_SLEEP", "1")
    monkeypatch.setenv("FAKE_REMOVE_EXIT", str(code))
    with pytest.raises(ValueError, match="Could not confirm ZAP container cleanup"):
        _run(runner_inputs, timeout=0.1)
    assert not (runner_inputs[3] / "receipt.json").exists()


@pytest.mark.parametrize("sleep", [False, True])
def test_startup_cancellation_waits_for_launch_then_removes_container(
    runner_inputs, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sleep: bool
) -> None:
    module = importlib.import_module("scripts.quality.zap_runner")
    if sleep:
        monkeypatch.setenv("FAKE_SLEEP", "1")
    removed = tmp_path / "startup-removed"
    monkeypatch.setenv("FAKE_REMOVED", str(removed))
    target, rules, identity, work, _ = runner_inputs
    original_spawn = module.asyncio.create_subprocess_exec

    async def scenario() -> None:
        spawned = asyncio.Event()
        processes = []

        async def delayed_spawn(*args, **kwargs):
            process = await original_spawn(*args, **kwargs)
            if "run" in args:
                processes.append(process)
                spawned.set()
                await asyncio.sleep(0.2)
            return process

        monkeypatch.setattr(module.asyncio, "create_subprocess_exec", delayed_spawn)
        task = asyncio.create_task(module.run_scan(target, rules, work, identity, 5))
        try:
            await asyncio.wait_for(spawned.wait(), 2)
            task.cancel()
            await asyncio.sleep(0.02)
            assert not task.done(), "runner returned while launch was unresolved"
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert removed.is_file()
            assert not (work / "receipt.json").exists()
            assert not (work / "target.txt").exists()
        finally:
            for process in processes:
                if process.returncode is None:
                    process.kill()
                await process.wait()

    asyncio.run(scenario())


def test_stuck_container_removal_has_a_terminal_timeout(
    runner_inputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_SLEEP", "1")
    monkeypatch.setenv("FAKE_REMOVE_SLEEP", "60")
    with pytest.raises(TimeoutError):
        _run(runner_inputs, timeout=0.1)
    assert not (runner_inputs[3] / "receipt.json").exists()


@pytest.mark.parametrize(
    "mode", ["missing", "wrong-origin", "proxy-error", "redirect-only"]
)
def test_report_alone_cannot_issue_verified_receipt(
    runner_inputs, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("FAKE_ORIGIN_MODE", mode)
    with pytest.raises((ValueError, OSError)):
        _run(runner_inputs)
    assert not (runner_inputs[3] / "receipt.json").exists()


def test_changed_hook_identity_stops_before_container(runner_inputs) -> None:
    runner_inputs[2]["hook_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="origin hook"):
        _run(runner_inputs)
    assert not runner_inputs[4].exists()


def test_runner_selects_verified_linux_amd64_platform(runner_inputs) -> None:
    _run(runner_inputs)
    arguments = json.loads(runner_inputs[4].read_text().splitlines()[0])
    assert "--platform" in arguments
    assert arguments[arguments.index("--platform") + 1] == "linux/amd64"


def test_cleanup_removes_container_after_client_already_exited(runner_inputs) -> None:
    import shutil
    import sys

    module = importlib.import_module("scripts.quality.zap_runner")

    async def scenario():
        process = await asyncio.create_subprocess_exec(sys.executable, "-c", "pass")
        assert await process.wait() == 0
        await module._stop_and_remove(
            process,
            shutil.which("docker"),
            "completed-client",
            asyncio.subprocess.DEVNULL,
            asyncio.subprocess.DEVNULL,
        )

    asyncio.run(scenario())
    assert json.loads(runner_inputs[4].read_text()) == [
        "rm",
        "--force",
        "completed-client",
    ]
