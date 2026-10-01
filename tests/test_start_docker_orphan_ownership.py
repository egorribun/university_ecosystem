from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_POWERSHELL = shutil.which("pwsh")


def test_startup_does_not_remove_containers_without_run_ownership_proof() -> None:
    script = (ROOT / "start-docker.ps1").read_text(encoding="utf-8")
    startup_commands = [
        line.strip()
        for line in script.splitlines()
        if re.match(r"^\s*docker compose\b.*\bup\b", line)
    ]

    assert startup_commands
    assert all("--remove-orphans" not in command for command in startup_commands)


def test_down_cannot_follow_an_environment_selected_compose_project() -> None:
    script = (ROOT / "start-docker.ps1").read_text(encoding="utf-8")
    down_start = script.index("# -- Handle -Down")
    logs_start = script.index("# -- Handle -Logs", down_start)
    down_block = script[down_start:logs_start]

    assert "@($ExtraCompose).Count -gt 0" in down_block
    assert 'docker compose --project-name "university_ecosystem"' in down_block
    assert "@ComposeArgs @envArgs down" in down_block


def _prepare_isolated_project(tmp_path: Path, *, live_overlay: bool = False) -> Path:
    project = tmp_path / "isolated project"
    project.mkdir()
    shutil.copy2(ROOT / "start-docker.ps1", project / "start-docker.ps1")
    (project / "docker-compose.full.yml").write_text(
        "name: university_ecosystem\nservices: {}\n", encoding="utf-8"
    )
    if live_overlay:
        (project / "docker-compose.live.yml").write_text(
            "services: {}\n", encoding="utf-8"
        )
    return project


def _install_fake_docker(tmp_path: Path) -> tuple[Path, Path]:
    bin_directory = tmp_path / "fake-bin"
    bin_directory.mkdir()
    command_log = tmp_path / "docker-commands.txt"
    if os.name == "nt":
        executable = bin_directory / "docker.cmd"
        executable.write_text(
            '@echo off\r\n>>"%FAKE_DOCKER_COMMAND_LOG%" echo %*\r\nexit /b 0\r\n',
            encoding="utf-8",
        )
    else:
        executable = bin_directory / "docker"
        executable.write_text(
            '#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$FAKE_DOCKER_COMMAND_LOG"\nexit 0\n',
            encoding="utf-8",
        )
        executable.chmod(stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
    return bin_directory, command_log


def _run_isolated_powershell(
    project: Path,
    bin_directory: Path,
    command_log: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    if _POWERSHELL is None:
        pytest.skip("PowerShell 7 (pwsh) is unavailable")
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join(
        (str(bin_directory), environment.get("PATH", ""))
    )
    environment["FAKE_DOCKER_COMMAND_LOG"] = str(command_log)
    environment["COMPOSE_PROJECT_NAME"] = "foreign-project"
    return subprocess.run(  # noqa: S603 - fixed PowerShell script and synthetic arguments
        [
            _POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(project / "start-docker.ps1"),
            *arguments,
        ],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


@pytest.mark.skipif(_POWERSHELL is None, reason="PowerShell 7 (pwsh) is unavailable")
def test_down_pins_project_and_preserves_local_data_without_docker_side_effects(
    tmp_path: Path,
) -> None:
    project = _prepare_isolated_project(tmp_path)
    bin_directory, command_log = _install_fake_docker(tmp_path)
    protected_files = {
        ".env": b"SENTINEL=keep\n",
        ".env.docker": b"COMPOSE_PROJECT_NAME=foreign-project\n",  # pragma: allowlist secret -- synthetic Docker resource fixture bytes
        "backups/keep.dump": b"synthetic-backup-bytes",
    }
    for relative_path, content in protected_files.items():
        path = project / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    completed = _run_isolated_powershell(project, bin_directory, command_log, "-Down")

    assert completed.returncode == 0, completed.stderr
    commands = command_log.read_text(encoding="utf-8").splitlines()
    assert commands == [
        "info",
        "compose --project-name university_ecosystem -f docker-compose.full.yml --env-file .env.docker down",
    ]
    assert "--volumes" not in commands[-1]
    assert "--remove-orphans" not in commands[-1]
    assert {
        relative_path: (project / relative_path).read_bytes()
        for relative_path in protected_files
    } == protected_files


@pytest.mark.skipif(_POWERSHELL is None, reason="PowerShell 7 (pwsh) is unavailable")
def test_down_refuses_the_live_overlay_before_any_compose_lifecycle_command(
    tmp_path: Path,
) -> None:
    project = _prepare_isolated_project(tmp_path, live_overlay=True)
    bin_directory, command_log = _install_fake_docker(tmp_path)
    environment_files = {
        ".env": b"SENTINEL=keep\n",
        ".env.docker": b"LIVE_DATA=keep\n",
        "backups/keep.dump": b"synthetic-backup-bytes",
    }
    for relative_path, content in environment_files.items():
        path = project / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    completed = _run_isolated_powershell(
        project,
        bin_directory,
        command_log,
        "-Down",
        "-ExtraCompose",
        "docker-compose.live.yml",
    )

    assert completed.returncode != 0
    assert "only targets the default Compose project" in (
        completed.stdout + completed.stderr
    )
    assert command_log.read_text(encoding="utf-8").splitlines() == ["info"]
    assert {
        relative_path: (project / relative_path).read_bytes()
        for relative_path in environment_files
    } == environment_files
