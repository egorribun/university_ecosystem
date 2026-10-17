"""Launcher storage contracts: the Docker CLI is replaced at the process boundary.

Storage is always SeaweedFS (ADR-042). The launcher refuses a first start
that would create empty SeaweedFS storage next to an unmigrated legacy MinIO
volume unless a durable local attestation binds the verified migration to its
exact project, source volumes, and target volume.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from hashlib import sha256
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOCAL_STATE_FILES = (".env", ".env.docker", ".env.docker.workers")
STORAGE_VOLUME = "university_ecosystem_seaweedfs_data"
ATTESTATION = ".secrets/s3-cutover-attestation.txt"
RUNBOOK = "docs/runbooks/s3-seaweedfs-cutover.md"


def local_state_digests() -> dict[str, str | None]:
    return {
        name: sha256((ROOT / name).read_bytes()).hexdigest()
        if (ROOT / name).is_file()
        else None
        for name in LOCAL_STATE_FILES
    }


def run_launcher(
    *args: str,
    attestation: str | None = None,
    volumes: tuple[str, ...] = (),
    stop_before_env_bootstrap: bool = False,
    project_name: str | None = None,
    volume_inspection_fails: bool = False,
    script_root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    # -Logs exercises the launcher's real Compose argument construction without
    # starting containers or changing any environment files.
    isolated_root: tempfile.TemporaryDirectory[str] | None = None
    if script_root is None:
        isolated_root = tempfile.TemporaryDirectory(prefix="s3-cutover-launcher-")
        script_root = Path(isolated_root.name)
        shutil.copyfile(ROOT / "start-docker.ps1", script_root / "start-docker.ps1")
        for overlay in ROOT.glob("docker-compose.*.yml"):
            shutil.copyfile(overlay, script_root / overlay.name)
    script = script_root / "start-docker.ps1"
    if attestation is not None:
        attestation_path = script_root / ATTESTATION
        attestation_path.parent.mkdir(parents=True, exist_ok=True)
        attestation_path.write_text(attestation, encoding="utf-8")
    # These are fixed test switches, not user input. Named parameters must be
    # bare tokens in PowerShell; quoting them passes positional string values.
    command_args = " ".join(args)
    safety_barrier = (
        "function Test-Path { param($Path, $LiteralPath); "
        "if ($env:TEST_STOP_BEFORE_ENV_BOOTSTRAP -eq '1' -and "
        "$Path -eq '.env.docker') { throw 'TEST_BARRIER_BEFORE_ENV_BOOTSTRAP' }; "
        "Microsoft.PowerShell.Management\\Test-Path @PSBoundParameters }; "
        if stop_before_env_bootstrap
        else ""
    )
    command = (
        "function docker { "
        "$global:LASTEXITCODE = 0; "
        "if ($args[0] -eq 'info') { return }; "
        "if ($args[0] -eq 'volume') { "
        "[Console]::Error.WriteLine("
        "'DOCKER_VOLUME_QUERY=' + ($args | ConvertTo-Json -Compress)); "
        "if ($env:TEST_DOCKER_VOLUME_FAIL -eq '1') { $global:LASTEXITCODE = 7; return }; "
        "foreach ($name in ($env:TEST_DOCKER_VOLUMES -split ',')) { "
        "if ($name) { Write-Output $name } }; "
        "return }; "
        "Write-Output ('DOCKER_ARGV=' + ($args | ConvertTo-Json -Compress)) "
        "}; "
        f"{safety_barrier}"
        f"& '{script}' {command_args}"
    )
    env = os.environ.copy()
    # -NoProfile still uses the .NET startup cache on Unix.
    env["XDG_CACHE_HOME"] = str(script_root / ".powershell-cache")
    # Simulate an old shell still carrying the retired one-shot bypass.
    env["S3_CUTOVER_ACK"] = "VERIFIED_S3_CUTOVER"
    env.pop("COMPOSE_PROJECT_NAME", None)
    if project_name is not None:
        env["COMPOSE_PROJECT_NAME"] = project_name
    env["TEST_DOCKER_VOLUMES"] = ",".join(volumes)
    env["TEST_STOP_BEFORE_ENV_BOOTSTRAP"] = "1" if stop_before_env_bootstrap else "0"
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
        "launcher test unexpectedly changed local environment files"
    )
    if isolated_root is not None:
        isolated_root.cleanup()
    return result


def _passed_storage_guard(result: subprocess.CompletedProcess[str]) -> bool:
    # The barrier sits right after the guard, before any environment mutation.
    return "TEST_BARRIER_BEFORE_ENV_BOOTSTRAP" in result.stdout + result.stderr


def _start(
    *,
    attestation: str | None = None,
    volumes: tuple[str, ...] = (),
    project_name: str | None = None,
    volume_inspection_fails: bool = False,
) -> subprocess.CompletedProcess[str]:
    return run_launcher(
        "-Build",
        stop_before_env_bootstrap=True,
        attestation=attestation,
        volumes=volumes,
        project_name=project_name,
        volume_inspection_fails=volume_inspection_fails,
    )


def test_fresh_machine_starts_seaweedfs_without_acknowledgement() -> None:
    result = _start(project_name="university_ecosystem")

    assert _passed_storage_guard(result)
    query = json.loads(
        result.stderr.split("DOCKER_VOLUME_QUERY=", 1)[1].splitlines()[0]
    )
    assert query[:2] == ["volume", "ls"]


@pytest.mark.parametrize(
    "legacy", ["university_ecosystem_minio-data", "university_ecosystem_minio_data"]
)
def test_legacy_volume_without_storage_volume_refuses_before_env_bootstrap(
    legacy: str,
) -> None:
    result = _start(project_name="university_ecosystem", volumes=(legacy,))

    assert result.returncode != 0
    assert not _passed_storage_guard(result)
    assert _reports(result, legacy)
    assert _reports(result, RUNBOOK)
    assert _reports(result, ATTESTATION)


def test_existing_matching_target_without_attestation_still_refuses() -> None:
    result = _start(
        project_name="university_ecosystem",
        volumes=("university_ecosystem_minio-data", STORAGE_VOLUME),
    )
    assert result.returncode != 0
    assert not _passed_storage_guard(result)


def test_ephemeral_acknowledgement_does_not_bypass_the_guard() -> None:
    result = _start(
        project_name="university_ecosystem",
        volumes=("university_ecosystem_minio-data",),
    )
    assert result.returncode != 0
    assert not _passed_storage_guard(result)


def test_matching_attestation_and_target_allow_start_and_keep_legacy_volume() -> None:
    result = _start(
        project_name="university_ecosystem",
        volumes=("university_ecosystem_minio-data", STORAGE_VOLUME),
        attestation=(
            "schema_version=1\n"
            "project_name=university_ecosystem\n"
            "legacy_source_volumes=university_ecosystem_minio-data\n"
            f"target_volume={STORAGE_VOLUME}\n"
            "verified=VERIFIED_S3_CUTOVER\n"
        ),
    )
    assert _passed_storage_guard(result)


def test_attestation_must_include_every_matching_legacy_volume() -> None:
    legacy = (
        "university_ecosystem_minio-data",
        "university_ecosystem_minio_data",
        STORAGE_VOLUME,
    )
    incomplete = _start(
        project_name="university_ecosystem",
        volumes=legacy,
        attestation=(
            "schema_version=1\n"
            "project_name=university_ecosystem\n"
            "legacy_source_volumes=university_ecosystem_minio-data\n"
            f"target_volume={STORAGE_VOLUME}\n"
            "verified=VERIFIED_S3_CUTOVER\n"
        ),
    )
    assert not _passed_storage_guard(incomplete)

    complete = _start(
        project_name="university_ecosystem",
        volumes=legacy,
        attestation=(
            "schema_version=1\n"
            "project_name=university_ecosystem\n"
            "legacy_source_volumes=university_ecosystem_minio-data,university_ecosystem_minio_data\n"
            f"target_volume={STORAGE_VOLUME}\n"
            "verified=VERIFIED_S3_CUTOVER\n"
        ),
    )
    assert _passed_storage_guard(complete)


def test_legacy_volume_name_follows_the_compose_project() -> None:
    other = _start(
        project_name="other_project",
        volumes=("university_ecosystem_minio-data",),
    )
    assert _passed_storage_guard(other)

    refused = _start(
        project_name="other_project", volumes=("other_project_minio-data",)
    )
    assert not _passed_storage_guard(refused)
    assert _reports(refused, "other_project_minio-data")


def test_default_project_name_is_university_ecosystem() -> None:
    # Compose files retain the stable default project name in detached trees.
    result = _start(volumes=("university_ecosystem_minio-data",))
    assert not _passed_storage_guard(result)


def test_project_scoped_target_alone_does_not_prove_migration() -> None:
    result = _start(
        project_name="ue-live",
        volumes=("ue-live_minio-data", "ue-live_seaweedfs_data"),
    )
    assert not _passed_storage_guard(result)


@pytest.mark.parametrize(
    "attestation",
    [
        "schema_version=1\nproject_name=other\nlegacy_source_volumes=review_minio-data\ntarget_volume=review_seaweedfs_data\nverified=VERIFIED_S3_CUTOVER\n",  # pragma: allowlist secret -- attestation fixture
        "schema_version=1\nproject_name=review\nlegacy_source_volumes=review_minio_data\ntarget_volume=review_seaweedfs_data\nverified=VERIFIED_S3_CUTOVER\n",  # pragma: allowlist secret -- attestation fixture
        f"schema_version=1\nproject_name=review\nlegacy_source_volumes=review_minio-data\ntarget_volume={STORAGE_VOLUME}\nverified=VERIFIED_S3_CUTOVER\n",  # pragma: allowlist secret -- attestation fixture
        "schema_version=1\nproject_name=review\nlegacy_source_volumes=review_minio-data\ntarget_volume=review_seaweedfs_data\nverified=NO\n",  # pragma: allowlist secret -- attestation fixture
    ],
    ids=["project-mismatch", "source-mismatch", "target-mismatch", "unverified"],
)
def test_custom_project_rejects_mismatched_attestation(attestation: str) -> None:
    result = _start(
        project_name="review",
        volumes=("review_minio-data", "review_seaweedfs_data"),
        attestation=attestation,
    )
    assert not _passed_storage_guard(result)


def test_custom_project_requires_its_exact_target_volume() -> None:
    result = _start(
        project_name="review",
        volumes=("review_minio-data", STORAGE_VOLUME),
        attestation=(
            "schema_version=1\n"
            "project_name=review\n"
            "legacy_source_volumes=review_minio-data\n"
            "target_volume=review_seaweedfs_data\n"
            "verified=VERIFIED_S3_CUTOVER\n"
        ),
    )
    assert not _passed_storage_guard(result)


def test_volume_lookup_is_exact_not_substring() -> None:
    result = _start(
        project_name="university_ecosystem",
        volumes=("university_ecosystem_minio-data", f"{STORAGE_VOLUME}_copy"),
    )
    assert not _passed_storage_guard(result)


def test_local_attestation_is_ignored_by_git() -> None:
    result = subprocess.run(  # noqa: S603 - fixed read-only Git query
        [shutil.which("git") or "git", "check-ignore", "-q", "--", ATTESTATION],
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0


def test_start_fails_closed_when_volume_inspection_fails() -> None:
    result = _start(project_name="university_ecosystem", volume_inspection_fails=True)

    assert result.returncode != 0
    assert not _passed_storage_guard(result)
    assert _reports(result, "Cannot inspect Docker volumes")


def test_down_and_logs_do_not_inspect_storage() -> None:
    down = run_launcher("-Down", volumes=("university_ecosystem_minio-data",))
    assert down.returncode == 0, down.stdout + down.stderr
    assert compose_argv(down)[-1] == "down"
    assert "DOCKER_VOLUME_QUERY=" not in down.stderr

    logs = run_launcher("-Logs", volumes=("university_ecosystem_minio-data",))
    assert logs.returncode == 0, logs.stdout + logs.stderr
    assert "DOCKER_VOLUME_QUERY=" not in logs.stderr


def test_down_ignores_a_stale_lock_from_the_retired_cutover(tmp_path: Path) -> None:
    shutil.copyfile(ROOT / "start-docker.ps1", tmp_path / "start-docker.ps1")
    lock_dir = tmp_path / ".secrets" / "s3-storage-compose.lock"
    lock_dir.mkdir(parents=True)

    result = run_launcher("-Down", script_root=tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert compose_argv(result)[-1] == "down"
    assert lock_dir.is_dir(), "the launcher never removes directories it did not create"


def test_launcher_has_no_cutover_or_rollback_machinery() -> None:
    source = (ROOT / "start-docker.ps1").read_text(encoding="utf-8")

    for retired in (
        "[switch]$SeaweedFS",
        "docker-compose.seaweedfs-cutover.yml",
        "s3-seaweedfs-cutover-initiated",
        "s3-storage-compose.lock",
        "S3StorageComposeLock",
        "Assert-PlainS3RollbackGuard",
        "StorageIsSeaweedFS",
        "SeaweedFSStorage",
        "localhost:9001",
        "S3_CUTOVER_ACK",
    ):
        assert retired not in source, retired


def test_retired_cutover_switch_is_rejected_before_any_docker_call() -> None:
    result = run_launcher("-SeaweedFS", "-Logs")
    assert result.returncode != 0
    assert "DOCKER_ARGV=" not in result.stdout


def compose_argv(result: subprocess.CompletedProcess[str]) -> list[str]:
    calls = [
        line.split("=", 1)[1]
        for line in result.stdout.splitlines()
        if line.startswith("DOCKER_ARGV=")
    ]
    assert len(calls) == 1, result.stdout + result.stderr
    return json.loads(calls[0])


def test_logs_use_only_the_full_compose_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared_cache = tmp_path / "shared-cache"
    profile = shared_cache / "powershell" / "StartupProfileData-NonInteractive"
    profile.parent.mkdir(parents=True)
    sentinel = b"parent-process-startup-cache"
    profile.write_bytes(sentinel)
    monkeypatch.setenv("XDG_CACHE_HOME", str(shared_cache))
    parent_environment = os.environ.copy()

    result = run_launcher("-Logs")

    assert result.returncode == 0, result.stdout + result.stderr
    args = compose_argv(result)
    assert args[:3] == ["compose", "-f", "docker-compose.full.yml"]
    assert args.count("-f") == 2  # the compose file and the follow flag
    assert args[-2:] == ["logs", "-f"]
    assert profile.read_bytes() == sentinel
    assert os.environ == parent_environment


def _reports(result: subprocess.CompletedProcess[str], reason: str) -> bool:
    """Match an error despite PowerShell's ANSI colour and mid-word wrapping.

    On narrow terminals PowerShell breaks a long error across lines prefixed
    with ``|``, sometimes inside a word, so compare with layout removed.
    """
    text = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout + result.stderr)
    text = re.sub(r"\n\s*\|", "", text)
    return re.sub(r"\s+", "", reason) in re.sub(r"\s+", "", text)


def test_extra_compose_overlay_is_applied_last() -> None:
    result = run_launcher("-Logs", "-ExtraCompose", "docker-compose.observability.yml")
    assert result.returncode == 0, result.stdout + result.stderr
    args = compose_argv(result)
    assert args[:5] == [
        "compose",
        "-f",
        "docker-compose.full.yml",
        "-f",
        "docker-compose.observability.yml",
    ]
    assert args[-2:] == ["logs", "-f"]


@pytest.mark.parametrize(
    ("overlay", "reason"),
    [
        (r"..\docker-compose.evil.yml", "expected a docker-compose.<name>.yml"),
        (r"C:\docker-compose.evil.yml", "expected a docker-compose.<name>.yml"),
        ("sub/docker-compose.evil.yml", "expected a docker-compose.<name>.yml"),
        ("docker-compose.yaml", "expected a docker-compose.<name>.yml"),
        ("compose.live.yml", "expected a docker-compose.<name>.yml"),
        ("docker-compose.full.yml", "is the base Compose file"),
        ("docker-compose.seaweedfs-cutover.yml", "file not found"),
        ("docker-compose.missing-overlay.yml", "file not found"),
    ],
)
def test_extra_compose_rejects_unsafe_or_missing_overlays(
    overlay: str, reason: str
) -> None:
    result = run_launcher("-Logs", "-ExtraCompose", f"'{overlay}'")
    assert result.returncode != 0
    assert _reports(result, reason)
    assert "DOCKER_ARGV=" not in result.stdout


def test_extra_compose_rejects_a_repeated_overlay() -> None:
    result = run_launcher(
        "-Logs",
        "-ExtraCompose",
        "docker-compose.observability.yml,docker-compose.observability.yml",
    )
    assert result.returncode != 0
    assert _reports(result, "listed twice")
    assert "DOCKER_ARGV=" not in result.stdout
