"""Private ZAP runner. Real-container compatibility needs separate validation.

The trusted workflow wrapper invokes this module; local tests use fake Docker.
The caller must verify source SHA and authorize the target before calling it.
A returned receipt proves this wrapper observed a completed process and report,
not that every intended active check ran or that the target was responsive.
The pinned container digest does not freeze add-ons updated by ZAP at runtime.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import shutil
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from scripts.quality.dast_privacy import target_is_safe
from scripts.quality.zap_run_provenance import finish_run, start_run
from scripts.quality.zap_sarif_producer import read_payload

# Target is read inside the container, never included in host command arguments.
_CONTAINER_ENTRY = (
    "import os;from pathlib import Path;"
    "target=Path('/zap/target.txt').read_text(encoding='utf-8');"
    "os.execvp('zap-full-scan.py',['zap-full-scan.py','-t',target,"
    "'-c','/zap/rules.tsv','-J','report_json.json','-a','-j','--ajax-spider','-T','60','--hook=/zap/origin-hook.py'])"
)


def _private_write(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


async def _remove_container(docker: str, name: str, stdout: Any, stderr: Any) -> None:
    cleanup = await asyncio.create_subprocess_exec(
        docker,
        "rm",
        "--force",
        name,
        stdout=stdout,
        stderr=stderr,
    )
    try:
        await asyncio.wait_for(cleanup.wait(), timeout=10)
    except BaseException:
        cleanup.kill()
        await cleanup.wait()
        raise
    if cleanup.returncode != 0:
        raise ValueError("Could not confirm ZAP container cleanup")


async def _stop_and_remove(
    process: asyncio.subprocess.Process,
    docker: str,
    name: str,
    stdout: Any,
    stderr: Any,
) -> None:
    try:
        if process.returncode is None:
            process.kill()
        await asyncio.wait_for(process.wait(), timeout=5)
    finally:
        await _remove_container(docker, name, stdout, stderr)


async def _finish_cleanup(
    process: asyncio.subprocess.Process,
    docker: str,
    name: str,
    stdout: Any,
    stderr: Any,
) -> None:
    # Shield alone is insufficient: outer cancellation would return early and
    # asyncio.run could cancel the still-pending removal at loop shutdown.
    task = asyncio.create_task(_stop_and_remove(process, docker, name, stdout, stderr))
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    task.result()
    if cancelled:
        raise asyncio.CancelledError


async def run_scan(
    target_file: Path,
    rules_file: Path,
    work: Path,
    identity: dict[str, str],
    timeout_seconds: float,
) -> dict[str, Any]:
    """Run one scanner in a fresh private directory, without uploading anything."""
    if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 3000:
        raise ValueError("Invalid ZAP outer timeout")
    docker = shutil.which("docker")
    if docker is None:
        raise ValueError("Docker is unavailable")
    target_bytes = read_payload(target_file)
    if not target_is_safe(target_bytes.decode("utf-8")):
        raise ValueError("Invalid ZAP target")
    hook_bytes = read_payload(Path(__file__).with_name("zap_origin_evidence.py"))
    if hashlib.sha256(hook_bytes).hexdigest() != identity.get("hook_sha256"):
        raise ValueError("ZAP origin hook does not match expected source")
    rules_bytes = read_payload(rules_file)
    if hashlib.sha256(rules_bytes).hexdigest() != identity.get("rules_sha256"):
        raise ValueError("ZAP rules do not match expected source")
    # Docker --mount uses commas as separators; reject ambiguous host paths.
    work = work.absolute()
    if any(char in str(work) for char in ",\r\n"):
        raise ValueError("Invalid private ZAP directory")
    nonce = start_run(work, identity)
    target_copy, rules_copy = work / "target.txt", work / "rules.tsv"
    try:
        _private_write(target_copy, target_bytes)
        _private_write(rules_copy, rules_bytes)
        hook_copy = work / "origin-hook.py"
        _private_write(hook_copy, hook_bytes)
        (work / "scan" / "home").mkdir(mode=0o700)
        name = f"zap-{nonce}"
        command = [
            docker,
            "run",
            "--rm",
            "--platform",
            "linux/amd64",
            # The target is the owned stand published on the runner's loopback.
            "--network",
            "host",
            "--name",
            name,
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--env",
            "HOME=/zap/wrk/home",
            "--workdir",
            "/zap/wrk",
            "--mount",
            f"type=bind,src={work / 'scan'},dst=/zap/wrk",
            "--mount",
            f"type=bind,src={target_copy},dst=/zap/target.txt,readonly",
            "--mount",
            f"type=bind,src={rules_copy},dst=/zap/rules.tsv,readonly",
            "--mount",
            f"type=bind,src={hook_copy},dst=/zap/origin-hook.py,readonly",
            identity["image"],
            "python3",
            "-c",
            _CONTAINER_ENTRY,
        ]
        with ExitStack() as stack:
            stdout = stack.enter_context(
                os.fdopen(
                    os.open(
                        work / "stdout.log", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                    ),
                    "wb",
                )
            )
            stderr = stack.enter_context(
                os.fdopen(
                    os.open(
                        work / "stderr.log", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                    ),
                    "wb",
                )
            )
            launch = asyncio.create_task(
                asyncio.create_subprocess_exec(*command, stdout=stdout, stderr=stderr)
            )
            cancelled_during_launch = False
            while not launch.done():
                try:
                    await asyncio.shield(launch)
                except asyncio.CancelledError:
                    cancelled_during_launch = True
            process = launch.result()
            try:
                if cancelled_during_launch:
                    raise asyncio.CancelledError
                code = await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
            except BaseException:
                await _finish_cleanup(process, docker, name, stdout, stderr)
                raise
        return finish_run(work, identity, nonce, code, target_bytes.decode("utf-8"))
    finally:
        target_copy.unlink(missing_ok=True)
