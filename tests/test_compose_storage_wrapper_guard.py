"""Compose convenience wrappers must not bypass the S3 cutover boundary."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("script", ["scripts/dc.ps1", "scripts/dc.sh"])
def test_wrappers_check_persistent_cutover_state_before_mutating_storage(
    script: str,
) -> None:
    source = (ROOT / script).read_text(encoding="utf-8")
    assert "s3-seaweedfs-cutover-initiated" in source
    assert "university_ecosystem_seaweedfs_data" in source
    assert "com.docker.compose.service=minio" in source
    assert "ps" in source and "logs" in source and "down" in source


def _run_powershell_wrapper(
    tmp_path: Path,
    *arguments: str,
    marker: bool = False,
    volume: bool = False,
    existing_image: str = "",
    inspect_fails: bool = False,
    env_project: str | None = None,
    lock_preexists: bool = False,
    compose_fails: bool = False,
) -> subprocess.CompletedProcess[str]:
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell is unavailable on this runner")
    (tmp_path / ".env.docker").write_text(
        f"COMPOSE_PROJECT_NAME='{env_project}'\n" if env_project else "",
        encoding="utf-8",
    )
    if marker:
        marker_path = tmp_path / ".secrets" / "s3-seaweedfs-cutover-initiated"
        marker_path.parent.mkdir()
        marker_path.write_text("cutover", encoding="utf-8")
    if lock_preexists:
        (tmp_path / ".secrets" / "s3-storage-compose.lock").mkdir(
            parents=True, exist_ok=True
        )
    command = (
        "function git { $env:TEST_COMPOSE_ROOT }; "
        "function docker { "
        "$global:LASTEXITCODE = 0; "
        "if ($args[0] -eq 'ps') { "
        "if ($env:TEST_INSPECTION_FAIL -eq '1') { $global:LASTEXITCODE = 7; return }; "
        "if ($env:TEST_STORAGE_IMAGE) { Write-Output $env:TEST_STORAGE_IMAGE }; return }; "
        "if ($args[0] -eq 'volume') { "
        "if ($env:TEST_INSPECTION_FAIL -eq '1') { $global:LASTEXITCODE = 7; return }; "
        "if ($env:TEST_VOLUME_EXISTS -eq '1') { "
        "Write-Output 'university_ecosystem_seaweedfs_data' }; return }; "
        "Write-Output ('COMPOSE_CALLED=' + ($args -join ' ')); "
        "Write-Output ('LOCK_HELD=' + "
        "(Test-Path (Join-Path $env:TEST_COMPOSE_ROOT '.secrets/s3-storage-compose.lock'))); "
        "if ($env:TEST_COMPOSE_FAIL -eq '1') { $global:LASTEXITCODE = 9 } "
        "}; "
        f"& '{ROOT / 'scripts' / 'dc.ps1'}' {' '.join(arguments)}"
    )
    env = os.environ.copy()
    env["TEST_COMPOSE_ROOT"] = str(tmp_path)
    env["TEST_VOLUME_EXISTS"] = "1" if volume else "0"
    env["TEST_STORAGE_IMAGE"] = existing_image
    env["TEST_INSPECTION_FAIL"] = "1" if inspect_fails else "0"
    env["TEST_COMPOSE_FAIL"] = "1" if compose_fails else "0"
    env.pop("COMPOSE_PROJECT_NAME", None)
    return subprocess.run(  # noqa: S603 - fixed interpreter/script with test-only switches
        [pwsh, "-NoProfile", "-Command", command],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


@pytest.mark.parametrize("verb", ["up", "start", "create", "run", "restart"])
def test_powershell_wrapper_blocks_mutating_commands_after_cutover(
    tmp_path: Path, verb: str
) -> None:
    result = _run_powershell_wrapper(tmp_path, verb, marker=True)
    assert result.returncode != 0
    assert "cutover" in (result.stdout + result.stderr).lower()
    assert "COMPOSE_CALLED=" not in result.stdout


def test_powershell_wrapper_blocks_stale_marker_loss_by_volume(tmp_path: Path) -> None:
    result = _run_powershell_wrapper(tmp_path, "up", volume=True)
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


def test_powershell_wrapper_blocks_existing_seaweedfs_container(tmp_path: Path) -> None:
    result = _run_powershell_wrapper(
        tmp_path, "up", existing_image="ghcr.io/chrislusf/seaweedfs:4.47"
    )
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


def test_powershell_wrapper_fails_closed_when_docker_inspection_fails(
    tmp_path: Path,
) -> None:
    result = _run_powershell_wrapper(tmp_path, "create", inspect_fails=True)
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


def test_powershell_wrapper_reads_quoted_compose_project_name(tmp_path: Path) -> None:
    result = _run_powershell_wrapper(tmp_path, "up", env_project="review_project")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout


@pytest.mark.parametrize(
    "volume_flag", ["-v", "-v=true", "-v=1", "--volume", "--volume=true", "--volumes"]
)
def test_powershell_wrapper_blocks_down_that_deletes_legacy_volume_after_cutover(
    tmp_path: Path, volume_flag: str
) -> None:
    result = _run_powershell_wrapper(tmp_path, "down", volume_flag, marker=True)
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


@pytest.mark.parametrize(
    "volume_flag", ["-v", "-v=true", "-v=1", "--volume", "--volume=true", "--volumes"]
)
def test_powershell_wrapper_never_offers_destructive_down(
    tmp_path: Path, volume_flag: str
) -> None:
    result = _run_powershell_wrapper(tmp_path, "down", volume_flag)
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


@pytest.mark.parametrize("prefix", [("--ansi", "never"), ("--compatibility",)])
def test_powershell_wrapper_rejects_unknown_global_prefix_before_destructive_down(
    tmp_path: Path, prefix: tuple[str, ...]
) -> None:
    result = _run_powershell_wrapper(tmp_path, *prefix, "down", "-v")
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


@pytest.mark.parametrize(
    "arguments",
    [
        ("-f", "docker-compose.seaweedfs-cutover.yml", "up"),
        ("--file=docker-compose.seaweedfs-cutover.yml", "up"),
        ("--file", "docker-compose.seaweedfs-cutover.yml", "up"),
        ("--project-directory", "other", "up"),
        ("--project-directory=other", "up"),
        ("--env-file", "other.env", "up"),
        ("--env-file=other.env", "up"),
        ("-pother", "up"),
        ("-p=other", "up"),
        ("up", "-f", "docker-compose.seaweedfs-cutover.yml"),
        ("up", "--file", "docker-compose.seaweedfs-cutover.yml"),
        ("up", "--project-directory", "other"),
        ("up", "--env-file", "other.env"),
    ],
)
def test_powershell_wrapper_rejects_topology_overrides(
    tmp_path: Path, arguments: tuple[str, ...]
) -> None:
    result = _run_powershell_wrapper(tmp_path, *arguments)
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


def test_powershell_wrapper_keeps_project_scoped_diagnostics(
    tmp_path: Path,
) -> None:
    result = _run_powershell_wrapper(tmp_path, "-p", "review", "ps", marker=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout


def test_powershell_wrapper_keeps_logs_follow_flag_after_cutover(
    tmp_path: Path,
) -> None:
    result = _run_powershell_wrapper(tmp_path, "logs", "-f", "backend", marker=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout


def test_powershell_wrapper_keeps_exec_command_flags(tmp_path: Path) -> None:
    result = _run_powershell_wrapper(tmp_path, "exec", "backend", "tool", "-f")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout


@pytest.mark.parametrize(
    "payload_option", ["--file", "--project-directory", "--env-file"]
)
def test_powershell_wrapper_preserves_exec_program_options(
    tmp_path: Path, payload_option: str
) -> None:
    result = _run_powershell_wrapper(
        tmp_path, "exec", "backend", "tool", payload_option, "config"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout


def test_powershell_wrapper_rejects_topology_option_before_exec_program(
    tmp_path: Path,
) -> None:
    result = _run_powershell_wrapper(tmp_path, "exec", "backend", "--file", "other")
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


def test_powershell_wrapper_holds_and_releases_storage_lock(tmp_path: Path) -> None:
    result = _run_powershell_wrapper(tmp_path, "up")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "LOCK_HELD=True" in result.stdout
    assert not (tmp_path / ".secrets" / "s3-storage-compose.lock").exists()


@pytest.mark.parametrize("verb", ["up", "down", "stop"])
def test_powershell_wrapper_fails_closed_on_existing_storage_lock(
    tmp_path: Path, verb: str
) -> None:
    result = _run_powershell_wrapper(tmp_path, verb, lock_preexists=True)
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout
    assert (tmp_path / ".secrets" / "s3-storage-compose.lock").is_dir()


def test_powershell_wrapper_read_only_command_ignores_storage_lock(
    tmp_path: Path,
) -> None:
    result = _run_powershell_wrapper(tmp_path, "ps", lock_preexists=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout


@pytest.mark.parametrize("mode", ["marker", "compose_failure"])
def test_powershell_wrapper_releases_owned_lock_on_failure(
    tmp_path: Path, mode: str
) -> None:
    result = _run_powershell_wrapper(
        tmp_path, "up", marker=mode == "marker", compose_fails=mode == "compose_failure"
    )
    assert result.returncode != 0
    assert not (tmp_path / ".secrets" / "s3-storage-compose.lock").exists()


@pytest.mark.parametrize("verb", ["ps", "logs", "down", "config"])
def test_powershell_wrapper_preserves_nonmutating_or_shutdown_commands(
    tmp_path: Path, verb: str
) -> None:
    result = _run_powershell_wrapper(tmp_path, verb, marker=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell integration runs on Linux CI")
def _run_shell_wrapper(
    tmp_path: Path,
    *arguments: str,
    marker: bool = False,
    volume: bool = False,
    existing_image: str = "",
    inspect_fails: bool = False,
    lock_preexists: bool = False,
    compose_fails: bool = False,
) -> subprocess.CompletedProcess[str]:
    shell = shutil.which("sh")
    if shell is None:
        pytest.skip("POSIX shell is unavailable on this runner")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / ".env.docker").write_text("", encoding="utf-8")
    if marker:
        marker_path = tmp_path / ".secrets" / "s3-seaweedfs-cutover-initiated"
        marker_path.parent.mkdir()
        marker_path.write_text("cutover", encoding="utf-8")
    if lock_preexists:
        (tmp_path / ".secrets" / "s3-storage-compose.lock").mkdir(
            parents=True, exist_ok=True
        )
    git = bin_dir / "git"
    git.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_COMPOSE_ROOT"\n', encoding="utf-8")
    git.chmod(0o755)
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        "  ps)\n"
        '    [ "$TEST_INSPECTION_FAIL" = 1 ] && exit 7\n'
        '    [ -n "$TEST_STORAGE_IMAGE" ] && printf "%s\\n" "$TEST_STORAGE_IMAGE"\n'
        "    exit 0 ;;\n"
        "  volume)\n"
        '    [ "$TEST_INSPECTION_FAIL" = 1 ] && exit 7\n'
        '    [ "$TEST_VOLUME_EXISTS" = 1 ] && printf "%s\\n" '
        '"university_ecosystem_seaweedfs_data"\n'
        "    exit 0 ;;\n"
        "esac\n"
        'printf "COMPOSE_CALLED=%s\\n" "$*"\n'
        'if [ -d "$TEST_COMPOSE_ROOT/.secrets/s3-storage-compose.lock" ]; then\n'
        '  printf "LOCK_HELD=True\\n"\n'
        "fi\n"
        '[ "$TEST_COMPOSE_FAIL" = 1 ] && exit 9\n'
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    env = os.environ.copy()
    env["TEST_COMPOSE_ROOT"] = str(tmp_path)
    env["TEST_VOLUME_EXISTS"] = "1" if volume else "0"
    env["TEST_STORAGE_IMAGE"] = existing_image
    env["TEST_INSPECTION_FAIL"] = "1" if inspect_fails else "0"
    env["TEST_COMPOSE_FAIL"] = "1" if compose_fails else "0"
    env.pop("COMPOSE_PROJECT_NAME", None)
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


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell integration runs on Linux CI")
@pytest.mark.parametrize("verb", ["up", "start", "create", "run", "restart"])
def test_shell_wrapper_blocks_mutating_commands_after_cutover(
    tmp_path: Path, verb: str
) -> None:
    result = _run_shell_wrapper(tmp_path, verb, marker=True)
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell integration runs on Linux CI")
@pytest.mark.parametrize(
    "volume_flag", ["-v", "-v=true", "-v=1", "--volume", "--volume=true", "--volumes"]
)
def test_shell_wrapper_blocks_down_that_deletes_legacy_volume_after_cutover(
    tmp_path: Path, volume_flag: str
) -> None:
    result = _run_shell_wrapper(tmp_path, "down", volume_flag, marker=True)
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell integration runs on Linux CI")
@pytest.mark.parametrize(
    "volume_flag", ["-v", "-v=true", "-v=1", "--volume", "--volume=true", "--volumes"]
)
def test_shell_wrapper_never_offers_destructive_down(
    tmp_path: Path, volume_flag: str
) -> None:
    result = _run_shell_wrapper(tmp_path, "down", volume_flag)
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell integration runs on Linux CI")
@pytest.mark.parametrize("prefix", [("--ansi", "never"), ("--compatibility",)])
def test_shell_wrapper_rejects_unknown_global_prefix_before_destructive_down(
    tmp_path: Path, prefix: tuple[str, ...]
) -> None:
    result = _run_shell_wrapper(tmp_path, *prefix, "down", "-v")
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell integration runs on Linux CI")
@pytest.mark.parametrize(
    "arguments",
    [
        ("-f", "docker-compose.seaweedfs-cutover.yml", "up"),
        ("--file=docker-compose.seaweedfs-cutover.yml", "up"),
        ("--file", "docker-compose.seaweedfs-cutover.yml", "up"),
        ("--project-directory", "other", "up"),
        ("--project-directory=other", "up"),
        ("--env-file", "other.env", "up"),
        ("--env-file=other.env", "up"),
        ("-pother", "up"),
        ("-p=other", "up"),
        ("up", "-f", "docker-compose.seaweedfs-cutover.yml"),
        ("up", "--file", "docker-compose.seaweedfs-cutover.yml"),
        ("up", "--project-directory", "other"),
        ("up", "--env-file", "other.env"),
    ],
)
def test_shell_wrapper_rejects_topology_overrides(
    tmp_path: Path, arguments: tuple[str, ...]
) -> None:
    result = _run_shell_wrapper(tmp_path, *arguments)
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell integration runs on Linux CI")
def test_shell_wrapper_keeps_project_scoped_diagnostics(tmp_path: Path) -> None:
    result = _run_shell_wrapper(tmp_path, "-p", "review", "ps", marker=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell integration runs on Linux CI")
def test_shell_wrapper_keeps_logs_follow_flag_after_cutover(tmp_path: Path) -> None:
    result = _run_shell_wrapper(tmp_path, "logs", "-f", "backend", marker=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell integration runs on Linux CI")
def test_shell_wrapper_keeps_exec_command_flags(tmp_path: Path) -> None:
    result = _run_shell_wrapper(tmp_path, "exec", "backend", "tool", "-f")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell integration runs on Linux CI")
@pytest.mark.parametrize(
    "payload_option", ["--file", "--project-directory", "--env-file"]
)
def test_shell_wrapper_preserves_exec_program_options(
    tmp_path: Path, payload_option: str
) -> None:
    result = _run_shell_wrapper(
        tmp_path, "exec", "backend", "tool", payload_option, "config"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell integration runs on Linux CI")
def test_shell_wrapper_rejects_topology_option_before_exec_program(
    tmp_path: Path,
) -> None:
    result = _run_shell_wrapper(tmp_path, "exec", "backend", "--file", "other")
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell integration runs on Linux CI")
def test_shell_wrapper_holds_and_releases_storage_lock(tmp_path: Path) -> None:
    result = _run_shell_wrapper(tmp_path, "up")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "LOCK_HELD=True" in result.stdout
    assert not (tmp_path / ".secrets" / "s3-storage-compose.lock").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell integration runs on Linux CI")
@pytest.mark.parametrize("verb", ["up", "down", "stop"])
def test_shell_wrapper_fails_closed_on_existing_storage_lock(
    tmp_path: Path, verb: str
) -> None:
    result = _run_shell_wrapper(tmp_path, verb, lock_preexists=True)
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout
    assert (tmp_path / ".secrets" / "s3-storage-compose.lock").is_dir()


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell integration runs on Linux CI")
def test_shell_wrapper_read_only_command_ignores_storage_lock(tmp_path: Path) -> None:
    result = _run_shell_wrapper(tmp_path, "ps", lock_preexists=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell integration runs on Linux CI")
@pytest.mark.parametrize("mode", ["marker", "compose_failure"])
def test_shell_wrapper_releases_owned_lock_on_failure(
    tmp_path: Path, mode: str
) -> None:
    result = _run_shell_wrapper(
        tmp_path, "up", marker=mode == "marker", compose_fails=mode == "compose_failure"
    )
    assert result.returncode != 0
    assert not (tmp_path / ".secrets" / "s3-storage-compose.lock").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell integration runs on Linux CI")
@pytest.mark.parametrize("mode", ["volume", "image", "failure"])
def test_shell_wrapper_fails_closed_on_persistent_storage_state(
    tmp_path: Path, mode: str
) -> None:
    result = _run_shell_wrapper(
        tmp_path,
        "up",
        volume=mode == "volume",
        existing_image="ghcr.io/chrislusf/seaweedfs:4.47" if mode == "image" else "",
        inspect_fails=mode == "failure",
    )
    assert result.returncode != 0
    assert "COMPOSE_CALLED=" not in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell integration runs on Linux CI")
@pytest.mark.parametrize("verb", ["ps", "logs", "down", "config"])
def test_shell_wrapper_keeps_diagnostics_and_plain_down_available(
    tmp_path: Path, verb: str
) -> None:
    result = _run_shell_wrapper(tmp_path, verb, marker=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSE_CALLED=" in result.stdout
