"""Compose convenience wrappers keep the launcher's legacy-storage boundary.

Storage is always SeaweedFS (ADR-042). A wrapper `up` on a machine that still
holds an unmigrated MinIO volume would create an empty SeaweedFS volume, after
which no guard could tell that legacy objects were left behind. The wrappers
therefore refuse storage-starting commands in that state, exactly like
start-docker.ps1, unless a project/source/target-bound local attestation
records that migration was verified.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LEGACY = "university_ecosystem_minio-data"
STORAGE = "university_ecosystem_seaweedfs_data"
ATTESTATION = ".secrets/s3-cutover-attestation.txt"
POSIX_ONLY = pytest.mark.skipif(
    os.name == "nt", reason="POSIX shell integration runs on Linux CI"
)


@pytest.mark.parametrize("script", ["scripts/dc.ps1", "scripts/dc.sh"])
def test_wrappers_share_the_launcher_legacy_storage_guard(script: str) -> None:
    source = (ROOT / script).read_text(encoding="utf-8")
    assert "_minio-data" in source and "_minio_data" in source
    assert "_seaweedfs_data" in source
    assert ATTESTATION in source
    assert "verified=VERIFIED_S3_CUTOVER" in source
    assert "S3_CUTOVER_ACK" not in source
    assert "docs/runbooks/s3-seaweedfs-cutover.md" in source
    for retired in (
        "s3-seaweedfs-cutover-initiated",
        "s3-storage-compose.lock",
        "com.docker.compose.service=minio",
        "--rmi",
    ):
        assert retired not in source, retired


def _write_env(tmp_path: Path, env_project: str | None) -> None:
    (tmp_path / ".env.docker").write_text(
        f"COMPOSE_PROJECT_NAME='{env_project}'\n" if env_project else "",
        encoding="utf-8",
    )


def _environment(
    tmp_path: Path,
    volumes: tuple[str, ...],
    inspect_fails: bool,
    compose_fails: bool,
) -> dict[str, str]:
    env = os.environ.copy()
    env["TEST_COMPOSE_ROOT"] = str(tmp_path)
    env["TEST_VOLUMES"] = ",".join(volumes)
    env["TEST_INSPECTION_FAIL"] = "1" if inspect_fails else "0"
    env["TEST_COMPOSE_FAIL"] = "1" if compose_fails else "0"
    # Legacy sessions may keep the retired acknowledgement in their environment.
    env["S3_CUTOVER_ACK"] = "VERIFIED_S3_CUTOVER"
    env.pop("COMPOSE_PROJECT_NAME", None)
    return env


def _attestation(
    project: str,
    sources: tuple[str, ...],
    target: str,
    verified: str = "VERIFIED_S3_CUTOVER",
) -> str:
    return (
        "\n".join(
            (
                "schema_version=1",
                f"project_name={project}",
                f"legacy_source_volumes={','.join(sources)}",
                f"target_volume={target}",
                f"verified={verified}",
            )
        )
        + "\n"
    )


def _write_attestation(tmp_path: Path, content: str | None) -> None:
    if content is None:
        return
    path = tmp_path / ATTESTATION
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_powershell_wrapper(
    tmp_path: Path,
    *arguments: str,
    volumes: tuple[str, ...] = (),
    inspect_fails: bool = False,
    env_project: str | None = None,
    compose_fails: bool = False,
    attestation: str | None = None,
) -> subprocess.CompletedProcess[str]:
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.fail("PowerShell is required for Compose wrapper contracts")
    _write_env(tmp_path, env_project)
    command = (
        "function git { $env:TEST_COMPOSE_ROOT }; "
        "function docker { "
        "$global:LASTEXITCODE = 0; "
        "if ($args[0] -eq 'volume') { "
        "if ($env:TEST_INSPECTION_FAIL -eq '1') { $global:LASTEXITCODE = 7; return }; "
        "foreach ($name in ($env:TEST_VOLUMES -split ',')) { "
        "if ($name) { Write-Output $name } }; return }; "
        "Write-Output ('COMPOSE_CALLED=' + ($args -join ' ')); "
        "if ($env:TEST_COMPOSE_FAIL -eq '1') { $global:LASTEXITCODE = 9 } "
        "}; "
        f"& '{ROOT / 'scripts' / 'dc.ps1'}' {' '.join(arguments)}; "
        # `pwsh -Command` reports only success/failure; surface the script's code.
        "exit $LASTEXITCODE"
    )
    _write_attestation(tmp_path, attestation)
    env = _environment(tmp_path, volumes, inspect_fails, compose_fails)
    # -NoProfile still shares the .NET startup cache on Unix. Parallel children
    # can corrupt it (PowerShell/PowerShell#26528); keep it inside this test root.
    env["XDG_CACHE_HOME"] = str(tmp_path / ".powershell-cache")
    return subprocess.run(  # noqa: S603 - fixed interpreter/script with test-only switches
        [pwsh, "-NoProfile", "-Command", command],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def _run_shell_wrapper(
    tmp_path: Path,
    *arguments: str,
    volumes: tuple[str, ...] = (),
    inspect_fails: bool = False,
    env_project: str | None = None,
    compose_fails: bool = False,
    attestation: str | None = None,
) -> subprocess.CompletedProcess[str]:
    shell = shutil.which("sh")
    if shell is None:
        pytest.fail("POSIX shell is required for Compose wrapper contracts")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_env(tmp_path, env_project)
    git = bin_dir / "git"
    git.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_COMPOSE_ROOT"\n', encoding="utf-8")
    git.chmod(0o755)
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = volume ]; then\n'
        '  [ "$TEST_INSPECTION_FAIL" = 1 ] && exit 7\n'
        '  printf "%s\\n" "$TEST_VOLUMES" | tr "," "\\n"\n'
        "  exit 0\n"
        "fi\n"
        'printf "COMPOSE_CALLED=%s\\n" "$*"\n'
        '[ "$TEST_COMPOSE_FAIL" = 1 ] && exit 9\n'
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    _write_attestation(tmp_path, attestation)
    env = _environment(tmp_path, volumes, inspect_fails, compose_fails)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    return subprocess.run(  # noqa: S603 - fixed local shell and test-only stubs
        [shell, str(ROOT / "scripts" / "dc.sh"), *arguments],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


WRAPPERS = [
    pytest.param(_run_powershell_wrapper, id="powershell"),
    pytest.param(_run_shell_wrapper, id="shell", marks=POSIX_ONLY),
]


@POSIX_ONLY
def test_powershell_wrapper_preserves_the_inherited_startup_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared_cache = tmp_path / "shared-cache"
    profile = shared_cache / "powershell" / "StartupProfileData-NonInteractive"
    profile.parent.mkdir(parents=True)
    sentinel = b"parent-process-startup-cache"
    profile.write_bytes(sentinel)
    monkeypatch.setenv("XDG_CACHE_HOME", str(shared_cache))
    project = tmp_path / "project"
    project.mkdir()

    result = _run_powershell_wrapper(project, "up")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout
    assert profile.read_bytes() == sentinel
    assert os.environ["XDG_CACHE_HOME"] == str(shared_cache)


@pytest.mark.parametrize("run", WRAPPERS)
@pytest.mark.parametrize("verb", ["up", "start", "create", "run", "restart"])
@pytest.mark.parametrize("legacy", [LEGACY, "university_ecosystem_minio_data"])
def test_wrapper_refuses_storage_start_next_to_an_unmigrated_legacy_volume(
    tmp_path: Path, run, verb: str, legacy: str
) -> None:
    result = run(tmp_path, verb, volumes=(legacy,), env_project="university_ecosystem")
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout
    assert "s3-seaweedfs-cutover.md" in result.stderr


@pytest.mark.parametrize("run", WRAPPERS)
def test_wrapper_does_not_accept_an_ephemeral_acknowledgement(
    tmp_path: Path, run
) -> None:
    result = run(
        tmp_path, "up", volumes=(LEGACY, STORAGE), env_project="university_ecosystem"
    )
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


@pytest.mark.parametrize("run", WRAPPERS)
@pytest.mark.parametrize(
    ("volumes", "attestation"),
    [
        ((), None),
        (("other_project_minio-data",), None),
    ],
    ids=["fresh", "other-project"],
)
def test_wrapper_starts_storage_when_no_legacy_objects_can_be_orphaned(
    tmp_path: Path, run, volumes: tuple[str, ...], attestation: str | None
) -> None:
    result = run(
        tmp_path,
        "up",
        volumes=volumes,
        env_project="university_ecosystem",
        attestation=attestation,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout


@pytest.mark.parametrize("run", WRAPPERS)
def test_wrapper_fails_closed_when_docker_inspection_fails(tmp_path: Path, run) -> None:
    result = run(tmp_path, "create", inspect_fails=True)
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


@pytest.mark.parametrize("run", WRAPPERS)
def test_wrapper_reads_the_quoted_compose_project_name(tmp_path: Path, run) -> None:
    result = run(
        tmp_path,
        "up",
        volumes=("review_project_minio-data",),
        env_project="review_project",
    )
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


@pytest.mark.parametrize("run", WRAPPERS)
def test_wrapper_honours_an_explicit_project_name(tmp_path: Path, run) -> None:
    refused = run(tmp_path, "-p", "review", "up", volumes=("review_minio-data",))
    assert refused.returncode != 0
    assert "COMPOSE_CALLED=" not in refused.stdout

    # A project-scoped storage volume (the live stand's naming) is migrated.
    second = tmp_path / "second"
    second.mkdir()
    migrated = run(
        second,
        "--project-name=review",
        "up",
        volumes=("review_minio-data", "review_seaweedfs_data"),
        attestation=_attestation(
            "review", ("review_minio-data",), "review_seaweedfs_data"
        ),
    )
    assert migrated.returncode == 0, migrated.stdout + migrated.stderr
    assert "COMPOSE_CALLED=" in migrated.stdout


@pytest.mark.parametrize("run", WRAPPERS)
def test_default_project_requires_its_exact_target_and_attestation(
    tmp_path: Path, run
) -> None:
    unverified = run(tmp_path, "up", volumes=(LEGACY, STORAGE))
    assert unverified.returncode != 0
    assert "COMPOSE_CALLED=" not in unverified.stdout

    second = tmp_path / "verified"
    second.mkdir()
    verified = run(
        second,
        "up",
        volumes=(LEGACY, STORAGE),
        attestation=_attestation("university_ecosystem", (LEGACY,), STORAGE),
    )
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert "COMPOSE_CALLED=" in verified.stdout


@pytest.mark.parametrize("run", WRAPPERS)
def test_unrelated_global_target_does_not_prove_custom_project_migration(
    tmp_path: Path, run
) -> None:
    result = run(
        tmp_path,
        "-p",
        "review",
        "up",
        volumes=("review_minio-data", STORAGE),
    )
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


@pytest.mark.parametrize("run", WRAPPERS)
@pytest.mark.parametrize(
    "attestation",
    [
        _attestation("other", ("review_minio-data",), "review_seaweedfs_data"),
        _attestation("review", ("review_minio_data",), "review_seaweedfs_data"),
        _attestation("review", ("review_minio-data",), STORAGE),
        _attestation("review", ("review_minio-data",), "review_seaweedfs_data", "NO"),
    ],
    ids=["project-mismatch", "source-mismatch", "target-mismatch", "unverified"],
)
def test_wrapper_rejects_mismatched_local_attestation(
    tmp_path: Path, run, attestation: str
) -> None:
    result = run(
        tmp_path,
        "-p",
        "review",
        "up",
        volumes=("review_minio-data", "review_seaweedfs_data"),
        attestation=attestation,
    )
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


@pytest.mark.parametrize("run", WRAPPERS)
def test_wrapper_attestation_lists_every_matching_legacy_source(
    tmp_path: Path, run
) -> None:
    sources = (LEGACY, "university_ecosystem_minio_data")
    incomplete = run(
        tmp_path,
        "up",
        volumes=(*sources, STORAGE),
        env_project="university_ecosystem",
        attestation=_attestation("university_ecosystem", (LEGACY,), STORAGE),
    )
    assert incomplete.returncode != 0
    assert "COMPOSE_CALLED=" not in incomplete.stdout

    second = tmp_path / "both-sources"
    second.mkdir()
    complete = run(
        second,
        "up",
        volumes=(*sources, STORAGE),
        env_project="university_ecosystem",
        attestation=_attestation("university_ecosystem", sources, STORAGE),
    )
    assert complete.returncode == 0, complete.stdout + complete.stderr
    assert "COMPOSE_CALLED=" in complete.stdout


@pytest.mark.parametrize("run", WRAPPERS)
@pytest.mark.parametrize("verb", ["ps", "logs", "down", "stop", "config"])
def test_wrapper_keeps_diagnostics_and_shutdown_available(
    tmp_path: Path, run, verb: str
) -> None:
    result = run(tmp_path, verb, volumes=(LEGACY,), inspect_fails=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout


@pytest.mark.parametrize("run", WRAPPERS)
@pytest.mark.parametrize(
    "volume_flag", ["-v", "-v=true", "-v=1", "--volume", "--volume=true", "--volumes"]
)
def test_wrapper_never_offers_destructive_down(
    tmp_path: Path, run, volume_flag: str
) -> None:
    result = run(tmp_path, "down", volume_flag)
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


@pytest.mark.parametrize("run", WRAPPERS)
def test_wrapper_allows_image_cleanup_now_that_no_minio_image_is_used(
    tmp_path: Path, run
) -> None:
    # MinIO images are no longer part of any Compose model, so `down --rmi`
    # cannot remove the cached legacy image the migration runbook relies on.
    result = run(tmp_path, "down", "--rmi", "local")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout


@pytest.mark.parametrize("run", WRAPPERS)
@pytest.mark.parametrize("prefix", [("--ansi", "never"), ("--compatibility",)])
def test_wrapper_rejects_unknown_global_prefix_before_destructive_down(
    tmp_path: Path, run, prefix: tuple[str, ...]
) -> None:
    result = run(tmp_path, *prefix, "down", "-v")
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


@pytest.mark.parametrize("run", WRAPPERS)
@pytest.mark.parametrize(
    "arguments",
    [
        ("-f", "docker-compose.live.yml", "up"),
        ("--file=docker-compose.live.yml", "up"),
        ("--file", "docker-compose.live.yml", "up"),
        ("--project-directory", "other", "up"),
        ("--project-directory=other", "up"),
        ("--env-file", "other.env", "up"),
        ("--env-file=other.env", "up"),
        ("-pother", "up"),
        ("-p=other", "up"),
        ("up", "-f", "docker-compose.live.yml"),
        ("up", "--file", "docker-compose.live.yml"),
        ("up", "--project-directory", "other"),
        ("up", "--env-file", "other.env"),
    ],
)
def test_wrapper_rejects_topology_overrides(
    tmp_path: Path, run, arguments: tuple[str, ...]
) -> None:
    result = run(tmp_path, *arguments)
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


@pytest.mark.parametrize("run", WRAPPERS)
def test_wrapper_keeps_project_scoped_diagnostics(tmp_path: Path, run) -> None:
    result = run(tmp_path, "-p", "review", "ps", volumes=("review_minio-data",))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout


@pytest.mark.parametrize("run", WRAPPERS)
def test_wrapper_keeps_logs_follow_flag(tmp_path: Path, run) -> None:
    result = run(tmp_path, "logs", "-f", "backend")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout


@pytest.mark.parametrize("run", WRAPPERS)
def test_wrapper_keeps_exec_command_flags(tmp_path: Path, run) -> None:
    result = run(tmp_path, "exec", "backend", "tool", "-f")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout


@pytest.mark.parametrize("run", WRAPPERS)
@pytest.mark.parametrize(
    "payload_option", ["--file", "--project-directory", "--env-file"]
)
def test_wrapper_preserves_exec_program_options(
    tmp_path: Path, run, payload_option: str
) -> None:
    result = run(tmp_path, "exec", "backend", "tool", payload_option, "config")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout


@pytest.mark.parametrize("run", WRAPPERS)
def test_wrapper_rejects_topology_option_before_exec_program(
    tmp_path: Path, run
) -> None:
    result = run(tmp_path, "exec", "backend", "--file", "other")
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


@pytest.mark.parametrize("run", WRAPPERS)
def test_wrapper_ignores_a_stale_lock_from_the_retired_cutover(
    tmp_path: Path, run
) -> None:
    lock = tmp_path / ".secrets" / "s3-storage-compose.lock"
    lock.mkdir(parents=True)
    result = run(tmp_path, "up")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout
    assert lock.is_dir(), "wrappers never remove directories they did not create"


@pytest.mark.parametrize("run", WRAPPERS)
def test_wrapper_propagates_the_compose_exit_code(tmp_path: Path, run) -> None:
    result = run(tmp_path, "up", compose_fails=True)
    assert result.returncode == 9
