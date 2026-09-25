"""Safe launcher contract tests: the Docker CLI is replaced at the process boundary."""

import json
import os
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILES = (".env", ".env.docker", ".env.docker.workers")


def env_file_digests() -> dict[str, str | None]:
    return {
        name: sha256((ROOT / name).read_bytes()).hexdigest()
        if (ROOT / name).is_file()
        else None
        for name in ENV_FILES
    }


def run_launcher(
    *args: str, ack: str | None = None
) -> subprocess.CompletedProcess[str]:
    # -Logs exercises the launcher's real Compose argument construction without
    # starting containers or changing any environment files.
    script = ROOT / "start-docker.ps1"
    # These are fixed test switches, not user input. Named parameters must be
    # bare tokens in PowerShell; quoting them passes positional string values.
    command_args = " ".join(args)
    command = (
        "function docker { "
        "$global:LASTEXITCODE = 0; "
        "if ($args[0] -eq 'info') { return }; "
        "Write-Output ('DOCKER_ARGV=' + ($args | ConvertTo-Json -Compress)) "
        "}; "
        f"& '{script}' {command_args}"
    )
    env = os.environ.copy()
    env.pop("S3_CUTOVER_ACK", None)
    if ack is not None:
        env["S3_CUTOVER_ACK"] = ack
    powershell = shutil.which("pwsh")
    assert powershell is not None
    before = env_file_digests()
    result = subprocess.run(  # noqa: S603 - fixed local interpreter and fixed test switches
        [powershell, "-NoProfile", "-Command", command],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert env_file_digests() == before, (
        "-Logs unexpectedly changed local environment files"
    )
    return result


def compose_argv(result: subprocess.CompletedProcess[str]) -> list[str]:
    calls = [
        line.split("=", 1)[1]
        for line in result.stdout.splitlines()
        if line.startswith("DOCKER_ARGV=")
    ]
    assert len(calls) == 1, result.stdout + result.stderr
    return json.loads(calls[0])


def test_default_logs_use_only_base_compose_even_with_cutover_ack() -> None:
    result = run_launcher("-Logs", ack="VERIFIED_S3_CUTOVER")
    assert result.returncode == 0, result.stdout + result.stderr
    args = compose_argv(result)
    assert args[:3] == ["compose", "-f", "docker-compose.full.yml"]
    assert "docker-compose.seaweedfs-cutover.yml" not in args
    assert args[-2:] == ["logs", "-f"]


def test_cutover_logs_put_overlay_last() -> None:
    result = run_launcher("-SeaweedFS", "-Logs", ack="VERIFIED_S3_CUTOVER")
    assert result.returncode == 0, result.stdout + result.stderr
    args = compose_argv(result)
    assert args[:5] == [
        "compose",
        "-f",
        "docker-compose.full.yml",
        "-f",
        "docker-compose.seaweedfs-cutover.yml",
    ]
    assert args[-2:] == ["logs", "-f"]


def test_cutover_without_ack_fails_before_docker_call() -> None:
    result = run_launcher("-SeaweedFS", "-Logs")
    assert result.returncode != 0
    assert "S3_CUTOVER_ACK" in result.stdout + result.stderr
    assert "DOCKER_ARGV=" not in result.stdout


def test_cutover_rejects_arbitrary_nonempty_ack() -> None:
    result = run_launcher("-SeaweedFS", "-Logs", ack="yes")
    assert result.returncode != 0
    assert "S3_CUTOVER_ACK" in result.stdout + result.stderr
    assert "DOCKER_ARGV=" not in result.stdout
