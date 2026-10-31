"""Fail-closed contracts for the trusted-main OSV release bootstrap."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import subprocess
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SBOM_WORKFLOW = ROOT / ".github" / "workflows" / "sbom.yml"
PAIR = re.compile(
    r'osv_scanner_version="(?P<version>v\d+\.\d+\.\d+)" '
    r'osv_scanner_sha256="(?P<digest>[0-9a-f]{64})"'
)


def _job_and_steps() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    workflow = yaml.safe_load(SBOM_WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["sbom-go"]
    installer = next(
        step for step in job["steps"] if step.get("name") == "Install osv-scanner"
    )
    scanner = next(
        step
        for step in job["steps"]
        if step.get("name") == "Scan Go modules for vulnerabilities + generate SBOM"
    )
    return job, installer, scanner


def _write_executable(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    return path


def _run_installer(
    tmp_path: Path,
    *,
    mode: str = "ok",
    runner_os: str = "Linux",
    runner_arch: str = "X64",
    kernel: str = "Linux",
    machine: str = "x86_64",
    version: str = "2.6.0",
    pin_version: str = "v2.6.0",
    wrong_digest: bool = False,
    malformed_digest: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
    _, installer, _ = _job_and_steps()
    script = installer["run"]
    matches = list(PAIR.finditer(script))
    assert len(matches) == 1, "installer must contain one version/checksum pair"

    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    tool_bin = tmp_path / "bin"
    tool_bin.mkdir()
    env_file = tmp_path / "github-env"
    env_file.write_text("", encoding="utf-8")
    event_log = tmp_path / "events"
    payload = _write_executable(
        tmp_path / "release-asset",
        "#!/bin/sh\n"
        'printf "version\\n" >> "$FAKE_EVENT_LOG"\n'
        '[ "$FAKE_MODE" != version-exit ] || exit 17\n'
        'printf "osv-scanner version: %s\\n" "$FAKE_VERSION"\n'
        'printf "osv-scalibr version: fixture\\n"\n',
    )
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    if wrong_digest:
        digest = hashlib.sha256(b"different release bytes").hexdigest()
    if malformed_digest:
        digest = "not-a-sha256"
    pair = f'osv_scanner_version="{pin_version}" osv_scanner_sha256="{digest}"'
    script = PAIR.sub(lambda _: pair, script, count=1)

    fake_curl = _write_executable(
        tool_bin / "curl",
        "#!/bin/sh\n"
        "set -eu\n"
        "output=''\n"
        "url=''\n"
        "protocol=''\n"
        "redirect_protocol=''\n"
        "max_time=''\n"
        "max_size=''\n"
        "fail_http=''\n"
        "follow_redirects=''\n"
        'while [ "$#" -gt 0 ]; do\n'
        '  case "$1" in\n'
        '    --output|-o) output="$2"; shift 2 ;;\n'
        '    --proto) protocol="$2"; shift 2 ;;\n'
        '    --proto-redir) redirect_protocol="$2"; shift 2 ;;\n'
        '    --max-time) max_time="$2"; shift 2 ;;\n'
        '    --max-filesize) max_size="$2"; shift 2 ;;\n'
        "    --fail|--fail-with-body) fail_http=yes; shift ;;\n"
        "    --location|-L) follow_redirects=yes; shift ;;\n"
        '    https://*) url="$1"; shift ;;\n'
        "    *) shift ;;\n"
        "  esac\n"
        "done\n"
        '[ -n "$output" ] && [ -n "$url" ] || exit 90\n'
        '[ "$protocol" = =https ] && [ "$redirect_protocol" = =https ] || exit 92\n'
        '[ "$fail_http" = yes ] && [ "$follow_redirects" = yes ] || exit 93\n'
        '[ "$max_time" -gt 0 ] && [ "$max_time" -le 180 ] || exit 94\n'
        '[ "$max_size" -gt 0 ] && [ "$max_size" -le 134217728 ] || exit 95\n'
        'case "$url" in\n'
        '  "https://github.com/google/osv-scanner/releases/download/$FAKE_PIN_VERSION/osv-scanner_linux_amd64")\n'
        '    printf "download-binary\\n" >> "$FAKE_EVENT_LOG"\n'
        '    case "$FAKE_MODE" in\n'
        "      download-failure) exit 22 ;;\n"
        "      missing) exit 0 ;;\n"
        '      empty) : > "$output"; exit 0 ;;\n'
        '      symlink) ln -s "$FAKE_PAYLOAD" "$output"; exit 0 ;;\n'
        '      cancelled) kill -TERM "$PPID"; exit 143 ;;\n'
        '      *) cp "$FAKE_PAYLOAD" "$output" ;;\n'
        "    esac ;;\n"
        "  *) exit 91 ;;\n"
        "esac\n",
    )
    fake_uname = _write_executable(
        tool_bin / "uname",
        "#!/bin/sh\n"
        'case "$1" in -s) printf "%s\\n" "$FAKE_KERNEL" ;; '
        '-m) printf "%s\\n" "$FAKE_MACHINE" ;; *) exit 1 ;; esac\n',
    )
    for original, replacement in (
        ("/usr/bin/curl", fake_curl),
        ("/usr/bin/uname", fake_uname),
    ):
        script = script.replace(original, str(replacement))

    env = {
        **os.environ,
        "PATH": f"{tool_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        "RUNNER_OS": runner_os,
        "RUNNER_ARCH": runner_arch,
        "RUNNER_TEMP": str(runner_temp),
        "GITHUB_ENV": str(env_file),
        "FAKE_EVENT_LOG": str(event_log),
        "FAKE_PAYLOAD": str(payload),
        "FAKE_MODE": mode,
        "FAKE_KERNEL": kernel,
        "FAKE_MACHINE": machine,
        "FAKE_VERSION": version,
        "FAKE_PIN_VERSION": pin_version,
    }
    env.pop("BASH_ENV", None)

    async def invoke() -> subprocess.CompletedProcess[str]:
        command = [
            "/bin/bash",
            "--noprofile",
            "--norc",
            "-e",
            "-o",
            "pipefail",
            "-c",
            script,
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=tmp_path,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
        except BaseException:
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
            await process.wait()
            raise
        assert process.returncode is not None
        return subprocess.CompletedProcess(
            command,
            process.returncode,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )

    result = asyncio.run(invoke())
    return result, runner_temp, env_file, event_log


def test_bootstrap_preserves_the_main_report_and_scanner_scope() -> None:
    job, installer, scanner = _job_and_steps()
    assert job["if"] == (
        "${{ github.ref == 'refs/heads/main' && github.event_name != 'pull_request' }}"
    )
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["permissions"] == {"contents": "read", "security-events": "write"}
    assert installer.get("continue-on-error") is not True
    assert "if" not in installer
    assert "go install github.com/google/osv-scanner" not in installer["run"]
    matches = list(PAIR.finditer(installer["run"]))
    assert len(matches) == 1
    assert matches[0]["version"] == "v2.6.0"
    max_size = re.search(r"--max-filesize\s+(\d+)", installer["run"])
    max_time = re.search(r"--max-time\s+(\d+)", installer["run"])
    assert max_size is not None and 0 < int(max_size.group(1)) <= 134_217_728
    assert max_time is not None and 0 < int(max_time.group(1)) <= 180
    assert "--proto-redir" in installer["run"]
    assert not re.search(r"(?m)^\s*(?:/usr/bin/)?sudo\b", installer["run"])
    assert "GITHUB_PATH" not in installer["run"]
    run = scanner["run"]
    assert '"$OSV_SCANNER_BIN" scan source --recursive --format sarif' in run
    assert "--output go-vuln.sarif" in run
    assert "./services/" in run
    assert scanner["id"] == "osv_scan"


def test_verified_asset_is_published_only_after_checksum_and_version_checks(
    tmp_path: Path,
) -> None:
    result, runner_temp, env_file, event_log = _run_installer(tmp_path)
    assert result.returncode == 0, result.stderr
    events = event_log.read_text(encoding="utf-8").splitlines()
    assert events.index("download-binary") < events.index("version")
    lines = env_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and lines[0].startswith("OSV_SCANNER_BIN=")
    executable = Path(lines[0].split("=", 1)[1])
    assert (
        executable.is_absolute()
        and executable.is_file()
        and not executable.is_symlink()
    )
    assert executable.is_relative_to(runner_temp) and os.access(executable, os.X_OK)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mode": "download-failure"},
        {"mode": "missing"},
        {"mode": "empty"},
        {"mode": "symlink"},
        {"mode": "cancelled"},
        {"mode": "version-exit"},
        {"wrong_digest": True},
        {"malformed_digest": True},
        {"runner_os": "Windows"},
        {"runner_arch": "ARM64"},
        {"kernel": "Darwin"},
        {"machine": "aarch64"},
        {"version": "2.5.1"},
        {"version": "2.6.0-unexpected"},
        {"pin_version": "v2.7.0"},
    ],
)
def test_invalid_inputs_fail_without_publishing_or_reusing_the_download(
    tmp_path: Path, kwargs: dict[str, Any]
) -> None:
    result, runner_temp, env_file, event_log = _run_installer(tmp_path, **kwargs)
    assert result.returncode != 0
    assert env_file.read_text(encoding="utf-8") == ""
    assert list(runner_temp.iterdir()) == []
    if kwargs.get("wrong_digest") or kwargs.get("malformed_digest"):
        assert not event_log.exists() or "version" not in event_log.read_text(
            encoding="utf-8"
        )
