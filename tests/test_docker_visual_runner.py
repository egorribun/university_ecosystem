"""Exercise the PowerShell visual wrapper with a fake external Docker command."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("pwsh")


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell 7 (pwsh) is unavailable")
@pytest.mark.parametrize("exit_code", [0, 17, 125])
@pytest.mark.parametrize("update", [False, True], ids=["verify", "update"])
def test_visual_wrapper_preserves_docker_exit_and_arguments(
    tmp_path: Path, exit_code: int, update: bool
) -> None:
    assert POWERSHELL is not None
    git = shutil.which("git")
    assert git is not None, "The wrapper requires Git"
    project = tmp_path / "project with spaces"
    project.mkdir()
    subprocess.run(  # noqa: S603 - initialize only the owned temporary repository
        [git, "init", "--quiet", str(project)], check=True, capture_output=True
    )
    script = project / "run-docker-visual-tests.ps1"
    shutil.copy2(ROOT / "scripts" / script.name, script)

    fake_bin = tmp_path / "fake bin"
    fake_bin.mkdir()
    command_log = tmp_path / "docker-arguments.json"
    fake_script = fake_bin / "record_docker.py"
    fake_script.write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['FAKE_DOCKER_LOG']).write_text(\n"
        "    json.dumps(sys.argv[1:]), encoding='utf-8')\n"
        "sys.exit(int(os.environ['FAKE_DOCKER_EXIT']))\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        executable = fake_bin / "docker.cmd"
        executable.write_text(
            '@echo off\n"%FAKE_DOCKER_PYTHON%" "%FAKE_DOCKER_SCRIPT%" %*\n'
            "exit /b %ERRORLEVEL%\n",
            encoding="utf-8",
        )
    else:
        executable = fake_bin / "docker"
        executable.write_text(
            '#!/bin/sh\nexec "$FAKE_DOCKER_PYTHON" "$FAKE_DOCKER_SCRIPT" "$@"\n',
            encoding="utf-8",
        )
        executable.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": os.pathsep.join((str(fake_bin), environment.get("PATH", ""))),
            "FAKE_DOCKER_PYTHON": sys.executable,
            "FAKE_DOCKER_SCRIPT": str(fake_script),
            "FAKE_DOCKER_LOG": str(command_log),
            "FAKE_DOCKER_EXIT": str(exit_code),
            # -NoProfile still uses the .NET startup cache on Unix.
            "XDG_CACHE_HOME": str(tmp_path / "powershell-cache"),
        }
    )
    completed = subprocess.run(  # noqa: S603 - actual wrapper, isolated fake Docker
        [
            POWERSHELL,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(script),
            *(["-Update"] if update else []),
        ],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    arguments = json.loads(command_log.read_text(encoding="utf-8"))
    assert arguments[:7] == [
        "run",
        "--rm",
        "-it",
        "-v",
        f"{str(project).replace('/', chr(92))}:/work",
        "-w",
        "/work/frontend",
    ]
    assert arguments[7].startswith("mcr.microsoft.com/playwright:")
    assert arguments[8:] == [
        "npx",
        "playwright",
        "test",
        "tests/e2e/visual.spec.ts",
        "--project=chromium",
        *(["--update-snapshots"] if update else []),
    ]
    assert completed.returncode == exit_code, completed.stdout + completed.stderr
    assert ("Visual command finished." in completed.stdout) == (exit_code == 0)
