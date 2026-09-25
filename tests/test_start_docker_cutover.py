"""Safe launcher contract tests: the Docker CLI is replaced at the process boundary."""

import json
import os
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_STATE_FILES = (
    ".env",
    ".env.docker",
    ".env.docker.workers",
    ".secrets/s3-seaweedfs-cutover-initiated",
)


def local_state_digests() -> dict[str, str | None]:
    return {
        name: sha256((ROOT / name).read_bytes()).hexdigest()
        if (ROOT / name).is_file()
        else None
        for name in LOCAL_STATE_FILES
    }


def run_launcher(
    *args: str,
    ack: str | None = None,
    existing_image: str | None = None,
    stop_before_env_bootstrap: bool = False,
    project_name: str | None = None,
    cutover_marker_exists: bool = False,
    seaweedfs_volume_exists: bool = False,
    ps_inspection_fails: bool = False,
    volume_inspection_fails: bool = False,
    script_root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    # -Logs exercises the launcher's real Compose argument construction without
    # starting containers or changing any environment files.
    script = (script_root or ROOT) / "start-docker.ps1"
    # These are fixed test switches, not user input. Named parameters must be
    # bare tokens in PowerShell; quoting them passes positional string values.
    command_args = " ".join(args)
    safety_barrier = (
        "function Test-Path { param($Path, $LiteralPath); "
        "if ($env:TEST_CUTOVER_MARKER_EXISTS -eq '1' -and "
        "$LiteralPath -match 's3-seaweedfs-cutover-initiated$') { return $true }; "
        "if ($env:TEST_STOP_BEFORE_ENV_BOOTSTRAP -eq '1' -and "
        "$Path -eq '.env.docker') { throw 'TEST_BARRIER_BEFORE_ENV_BOOTSTRAP' }; "
        "Microsoft.PowerShell.Management\\Test-Path @PSBoundParameters }; "
        if stop_before_env_bootstrap or cutover_marker_exists
        else ""
    )
    command = (
        "function docker { "
        "$global:LASTEXITCODE = 0; "
        "if ($args[0] -eq 'info') { return }; "
        "if ($args[0] -eq 'ps') { "
        "[Console]::Error.WriteLine('DOCKER_QUERY=' + ($args | ConvertTo-Json -Compress)); "
        "if ($env:TEST_DOCKER_PS_FAIL -eq '1') { $global:LASTEXITCODE = 7; return }; "
        "if ($env:TEST_EXISTING_STORAGE_IMAGE) { Write-Output $env:TEST_EXISTING_STORAGE_IMAGE }; "
        "return }; "
        "if ($args[0] -eq 'volume') { "
        "[Console]::Error.WriteLine('DOCKER_VOLUME_QUERY=' + ($args | ConvertTo-Json -Compress)); "
        "if ($env:TEST_DOCKER_VOLUME_FAIL -eq '1') { $global:LASTEXITCODE = 7; return }; "
        "if ($env:TEST_SEAWEEDFS_VOLUME_EXISTS -eq '1') { "
        "Write-Output 'university_ecosystem_seaweedfs_data' }; "
        "return }; "
        "Write-Output ('DOCKER_ARGV=' + ($args | ConvertTo-Json -Compress)) "
        "}; "
        f"{safety_barrier}"
        f"& '{script}' {command_args}"
    )
    env = os.environ.copy()
    env.pop("S3_CUTOVER_ACK", None)
    if ack is not None:
        env["S3_CUTOVER_ACK"] = ack
    env.pop("TEST_EXISTING_STORAGE_IMAGE", None)
    if existing_image is not None:
        env["TEST_EXISTING_STORAGE_IMAGE"] = existing_image
    env.pop("COMPOSE_PROJECT_NAME", None)
    if project_name is not None:
        env["COMPOSE_PROJECT_NAME"] = project_name
    env["TEST_CUTOVER_MARKER_EXISTS"] = "1" if cutover_marker_exists else "0"
    env["TEST_SEAWEEDFS_VOLUME_EXISTS"] = "1" if seaweedfs_volume_exists else "0"
    env["TEST_STOP_BEFORE_ENV_BOOTSTRAP"] = "1" if stop_before_env_bootstrap else "0"
    env["TEST_DOCKER_PS_FAIL"] = "1" if ps_inspection_fails else "0"
    env["TEST_DOCKER_VOLUME_FAIL"] = "1" if volume_inspection_fails else "0"
    powershell = shutil.which("pwsh")
    assert powershell is not None
    before = local_state_digests()
    result = subprocess.run(  # noqa: S603 - fixed local interpreter and fixed test switches
        [powershell, "-NoProfile", "-Command", command],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert local_state_digests() == before, (
        "launcher test unexpectedly changed local environment or cutover marker files"
    )
    return result


def test_plain_start_refuses_existing_seaweedfs_before_env_bootstrap() -> None:
    result = run_launcher(
        "-Build",
        existing_image="ghcr.io/chrislusf/seaweedfs:4.47",
        stop_before_env_bootstrap=True,
    )
    assert result.returncode != 0
    assert "SeaweedFS" in result.stdout + result.stderr
    assert "rollback" in (result.stdout + result.stderr).lower()
    assert "TEST_BARRIER_BEFORE_ENV_BOOTSTRAP" not in result.stdout + result.stderr
    assert "DOCKER_QUERY=" in result.stderr
    query = json.loads(result.stderr.split("DOCKER_QUERY=", 1)[1].splitlines()[0])
    assert query[:2] == ["ps", "-a"]
    assert "label=com.docker.compose.project=university_ecosystem" in query
    assert "label=com.docker.compose.service=minio" in query


def test_plain_first_start_passes_storage_guard_without_existing_container() -> None:
    result = run_launcher("-Build", stop_before_env_bootstrap=True)
    assert "DOCKER_QUERY=" in result.stderr
    assert "TEST_BARRIER_BEFORE_ENV_BOOTSTRAP" in result.stderr
    assert "rollback" not in (result.stdout + result.stderr).lower()


def test_plain_start_inspects_custom_compose_project() -> None:
    result = run_launcher(
        "-Build",
        project_name="other_project",
        existing_image="ghcr.io/chrislusf/seaweedfs:4.47",
        stop_before_env_bootstrap=True,
    )
    assert "rollback" in (result.stdout + result.stderr).lower()
    query = json.loads(result.stderr.split("DOCKER_QUERY=", 1)[1].splitlines()[0])
    assert "label=com.docker.compose.project=other_project" in query


def test_plain_start_refuses_prior_cutover_after_containers_are_removed() -> None:
    result = run_launcher(
        "-Build",
        stop_before_env_bootstrap=True,
        cutover_marker_exists=True,
    )
    assert result.returncode != 0
    assert "rollback" in (result.stdout + result.stderr).lower()
    assert "TEST_BARRIER_BEFORE_ENV_BOOTSTRAP" not in result.stdout + result.stderr


def test_plain_start_refuses_persistent_cutover_volume_without_marker_or_container() -> (
    None
):
    result = run_launcher(
        "-Build",
        stop_before_env_bootstrap=True,
        seaweedfs_volume_exists=True,
    )
    assert result.returncode != 0
    assert "rollback" in (result.stdout + result.stderr).lower()
    assert "TEST_BARRIER_BEFORE_ENV_BOOTSTRAP" not in result.stdout + result.stderr
    assert "DOCKER_VOLUME_QUERY=" in result.stderr


def test_plain_start_fails_closed_when_storage_inspection_fails() -> None:
    result = run_launcher(
        "-Build", stop_before_env_bootstrap=True, ps_inspection_fails=True
    )
    assert (
        "Cannot inspect the existing Compose storage service"
        in result.stdout + result.stderr
    )
    assert "TEST_BARRIER_BEFORE_ENV_BOOTSTRAP" not in result.stdout + result.stderr


def test_plain_start_fails_closed_when_volume_inspection_fails() -> None:
    result = run_launcher(
        "-Build", stop_before_env_bootstrap=True, volume_inspection_fails=True
    )
    assert (
        "Cannot inspect the SeaweedFS cutover volume" in result.stdout + result.stderr
    )
    assert "TEST_BARRIER_BEFORE_ENV_BOOTSTRAP" not in result.stdout + result.stderr


def test_down_remains_available_with_cutover_marker() -> None:
    result = run_launcher("-Down", cutover_marker_exists=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert compose_argv(result)[-1] == "down"
    assert "DOCKER_QUERY=" not in result.stderr


def test_down_refuses_another_storage_operation_holding_the_shared_lock(
    tmp_path: Path,
) -> None:
    shutil.copyfile(ROOT / "start-docker.ps1", tmp_path / "start-docker.ps1")
    lock_dir = tmp_path / ".secrets" / "s3-storage-compose.lock"
    lock_dir.mkdir(parents=True)

    result = run_launcher("-Down", script_root=tmp_path)

    assert result.returncode != 0
    assert "DOCKER_ARGV=" not in result.stdout
    assert lock_dir.is_dir(), "a competing lock must never be removed"


def test_launcher_rechecks_storage_under_lock_before_final_up() -> None:
    source = (ROOT / "start-docker.ps1").read_text(encoding="utf-8")
    start = source.index("# -- Start services")
    end = source.index("# -- Health check loop", start)
    startup = source[start:end]

    assert startup.index("Enter-S3StorageComposeLock") < startup.index(
        "Assert-PlainS3RollbackGuard"
    )
    assert startup.index("Assert-PlainS3RollbackGuard") < startup.index(
        "docker compose @ComposeArgs --env-file $EnvFile up"
    )
    assert "finally" in startup and "Exit-S3StorageComposeLock" in startup


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
    assert "DOCKER_QUERY=" not in result.stderr


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
