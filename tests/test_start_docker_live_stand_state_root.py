"""PowerShell launcher coverage for owned in-place live-stand state roots."""

from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("pwsh")
PORT_NAMES = (
    "BACKEND",
    "FRONTEND",
    "POSTGRES",
    "GATEWAY",
    "WS_HUB",
    "TEMPORAL_GRPC",
    "TEMPORAL_WEB",
    "IMGPROXY",
    "GRAFANA",
    "PROMETHEUS",
    "ALLOY",
    "PYROSCOPE",
    "CADDY_HTTP",
    "CADDY_HTTPS",
    "MAILPIT",
)


def _fixture_project(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "source checkout"
    project.mkdir()
    shutil.copy2(ROOT / "start-docker.ps1", project / "start-docker.ps1")
    for name in ("docker-compose.full.yml", "docker-compose.live.yml"):
        shutil.copy2(ROOT / name, project / name)
    runtime_files = (
        "config/nats.conf.template",
        "services/temporal/config.yaml",
        "services/temporal/entrypoint.sh",
        "infrastructure/observability/prometheus.yml",
        "infrastructure/observability/alerts/gateway.yaml",
        "infrastructure/observability/tempo.yaml",
        "infrastructure/observability/loki.yaml",
        "infrastructure/observability/alloy/config.alloy",
        "infrastructure/observability/grafana/provisioning/datasources/datasources.yaml",
        "k8s/flagd/flags.json",
        "infrastructure/Caddyfile",
    )
    for relative in runtime_files:
        source = ROOT / relative
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return project, tmp_path / "temp" / "ue-live-acceptance" / "run-36854541120"


def _vapid_pair() -> tuple[str, str]:
    # The launcher validates key shape and the uncompressed P-256 public point.
    private = bytes.fromhex("01" * 32)
    public = b"\x04" + bytes.fromhex("02" * 64)
    return (
        base64.urlsafe_b64encode(public).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(private).decode("ascii").rstrip("="),
    )


def _owner_marker(project: Path, state_root: Path) -> dict[str, object]:
    payload: dict[str, object] = {
        "version": 7,
        "repository": str(project.resolve()),
        "worktree": str(state_root.resolve()),
        "project_name": "ue-live-36854541120abcd1",
        "published_ports": {
            name: 32000 + index for index, name in enumerate(PORT_NAMES)
        },
        "daemon_fingerprint": "d" * 64,
        "compose_resource_fingerprint": None,
        "resume_compose_resource_fingerprint": None,
        "source_sha": "a" * 40,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    key = b"owner-key-fixture-material-32bytes!"[:32]
    signature = hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return {**payload, "signature": signature}


def _secure_state_tree(state_root: Path) -> None:
    if os.name == "nt":
        whoami = shutil.which("whoami.exe") or shutil.which("whoami")
        icacls = shutil.which("icacls.exe") or shutil.which("icacls")
        assert whoami is not None and icacls is not None
        identity = subprocess.run(  # noqa: S603 - fixed Windows identity query
            [whoami, "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        row = next(csv.reader(identity.stdout.splitlines()))
        sid = row[-1]
        assert sid.startswith("S-1-")
        subprocess.run(  # noqa: S603 - fixed Windows ACL tool and pytest-owned temp path
            [icacls, str(state_root), "/reset", "/T", "/C"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        subprocess.run(  # noqa: S603 - fixed Windows ACL tool and validated SID
            [icacls, str(state_root), "/setowner", f"*{sid}", "/T", "/C"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        subprocess.run(  # noqa: S603 - fixed Windows ACL tool and validated SID
            [
                icacls,
                str(state_root),
                "/inheritance:r",
                "/grant:r",
                f"*{sid}:(OI)(CI)F",
                "*S-1-5-18:(OI)(CI)F",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return
    state_root.chmod(0o700)
    for path in state_root.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)


def _live_environment(state_root: Path, public: str, private: str) -> dict[str, str]:
    env = os.environ.copy()
    temp_root = state_root.parents[1]
    env["TEMP"] = str(temp_root)
    env["TMP"] = str(temp_root)
    if os.name != "nt":
        env["TMPDIR"] = str(temp_root)
    # -NoProfile still uses the .NET startup cache on Unix.
    env["XDG_CACHE_HOME"] = str(temp_root / ".powershell-cache")
    env["COMPOSE_PROJECT_NAME"] = "ue-live-36854541120abcd1"
    ports = {name: 32000 + index for index, name in enumerate(PORT_NAMES)}
    env["LIVE_BASE_URL"] = f"http://localhost:{ports['CADDY_HTTP']}"
    env["LIVE_VAPID_PUBLIC_KEY"] = public
    env["LIVE_VAPID_PRIVATE_KEY"] = private
    env["LIVE_STAND_SOURCE_SHA"] = "a" * 40
    for name, port in ports.items():
        if name == "MAILPIT":
            env["LIVE_MAILPIT_PORT"] = str(port)
        else:
            env[f"LIVE_HOST_PORT_{name}"] = str(port)
    return env


def _run_prepare(
    project: Path,
    state_root: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL is not None
    # Some callers supply stand_environment() instead of _live_environment().
    environment = env.copy()
    environment["XDG_CACHE_HOME"] = str(project / ".powershell-cache")
    return subprocess.run(  # noqa: S603 - fixed PowerShell file and constrained test arguments
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(project / "start-docker.ps1"),
            "-PrepareOnly",
            "-ExtraCompose",
            "docker-compose.live.yml",
            "-LiveStandStateRoot",
            str(state_root),
        ],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=40,
    )


def _windows_acl_summary(path: Path) -> dict[str, object]:
    powershell = shutil.which("pwsh") or shutil.which("powershell.exe")
    assert powershell is not None
    env = os.environ.copy()
    env["LIVE_STAND_ACL_TARGET"] = str(path)
    script = r"""
$ErrorActionPreference = 'Stop'
$acl = Get-Acl -LiteralPath $env:LIVE_STAND_ACL_TARGET
$ownerSid = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
$rules = @($acl.Access | ForEach-Object {
    [pscustomobject]@{
        Sid = $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
        Type = $_.AccessControlType.ToString()
        Rights = $_.FileSystemRights.ToString()
    }
})
[pscustomobject]@{ OwnerSid = $ownerSid; Rules = $rules } | ConvertTo-Json -Depth 5 -Compress
"""
    result = subprocess.run(  # noqa: S603 - fixed PowerShell executable and test temp path
        [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0
    return json.loads(result.stdout)


def _assert_windows_private_acl(path: Path) -> None:
    acl = _windows_acl_summary(path)
    identity = subprocess.run(  # noqa: S603 - fixed Windows identity query
        [shutil.which("whoami.exe") or "whoami", "/user", "/fo", "csv", "/nh"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    user_sid = next(csv.reader(identity.stdout.splitlines()))[-1]
    assert acl["OwnerSid"] == user_sid
    rules = acl["Rules"]
    assert isinstance(rules, list)
    allow_rules = [rule for rule in rules if rule["Type"] == "Allow"]
    assert {rule["Sid"] for rule in allow_rules} == {user_sid, "S-1-5-18"}
    assert all("FullControl" in rule["Rights"] for rule in allow_rules)


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell 7 (pwsh) is unavailable")
def test_launcher_refuses_state_root_outside_owned_temp_parent_without_writes(
    tmp_path: Path,
) -> None:
    project, state_root = _fixture_project(tmp_path)
    outside_root = tmp_path / "unowned-state"
    outside_root.mkdir()
    public, private = _vapid_pair()
    source_before = {
        name: (project / name).read_bytes()
        for name in (
            "start-docker.ps1",
            "docker-compose.full.yml",
            "docker-compose.live.yml",
        )
    }

    result = _run_prepare(
        project,
        outside_root,
        _live_environment(state_root, public, private),
    )

    assert result.returncode != 0
    assert "owned temporary" in (result.stdout + result.stderr).lower()
    assert not (project / ".env").exists()
    assert not (project / ".env.docker").exists()
    assert not (project / ".secrets").exists()
    assert {
        name: (project / name).read_bytes() for name in source_before
    } == source_before


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell 7 (pwsh) is unavailable")
def test_launcher_prepare_only_writes_live_configuration_under_owned_state_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared_cache = tmp_path / "shared-cache"
    profile = shared_cache / "powershell" / "StartupProfileData-NonInteractive"
    profile.parent.mkdir(parents=True)
    sentinel = b"parent-process-startup-cache"
    profile.write_bytes(sentinel)
    monkeypatch.setenv("XDG_CACHE_HOME", str(shared_cache))
    parent_environment = os.environ.copy()
    project, state_root = _fixture_project(tmp_path)
    state_root.mkdir(parents=True)
    secrets_root = state_root / ".secrets"
    secrets_root.mkdir()
    (secrets_root / "live-stand-owner.key").write_bytes(
        b"owner-key-fixture-material-32bytes!"[:32]
    )
    public, private = _vapid_pair()
    (secrets_root / "live-vapid.json").write_text(
        json.dumps({"public": public, "private": private}), encoding="utf-8"
    )
    (secrets_root / "live-stand.json").write_text(
        json.dumps(_owner_marker(project, state_root)), encoding="utf-8"
    )
    state_overlay = state_root / "docker-compose.live-state.yml"
    state_overlay.write_text("services: {}\n", encoding="utf-8")
    _secure_state_tree(state_root)
    env = _live_environment(state_root, public, private)

    result = _run_prepare(project, state_root, env)

    assert result.returncode == 0, result.stderr[-2000:]
    assert profile.read_bytes() == sentinel
    assert os.environ == parent_environment
    assert (state_root / ".env").is_file()
    assert (state_root / ".env.docker").is_file()
    assert (state_root / ".env.docker.workers").is_file()
    assert (secrets_root / "jwt_rs256.pem").is_file()
    assert (secrets_root / "jwt_rs256.pub.pem").is_file()
    assert (secrets_root / "temporal_api_key").is_file()
    assert state_overlay.read_text(encoding="utf-8") == "services: {}\n"
    assert not (project / ".env").exists()
    assert not (project / ".env.docker").exists()
    assert not (project / ".env.docker.workers").exists()
    assert not (project / ".secrets").exists()
    if os.name != "nt":
        assert stat.S_IMODE(state_root.stat().st_mode) == 0o700
        assert stat.S_IMODE(secrets_root.stat().st_mode) == 0o700
        for path in (
            state_root / ".env",
            state_root / ".env.docker",
            state_root / ".env.docker.workers",
        ):
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in (
            secrets_root / "jwt_rs256.pem",
            secrets_root / "jwt_rs256.pub.pem",
            secrets_root / "temporal_api_key",
        ):
            assert stat.S_IMODE(path.stat().st_mode) == 0o644
        for path in (
            secrets_root / "live-stand-owner.key",
            secrets_root / "live-vapid.json",
            secrets_root / "live-stand.json",
        ):
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
    else:
        for path in (
            state_root / ".env",
            state_root / ".env.docker",
            state_root / ".env.docker.workers",
            secrets_root / "jwt_rs256.pem",
            secrets_root / "jwt_rs256.pub.pem",
            secrets_root / "temporal_api_key",
        ):
            _assert_windows_private_acl(path)


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell 7 (pwsh) is unavailable")
def test_launcher_prepare_only_accepts_python_generated_in_place_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared_cache = tmp_path / "shared-cache"
    profile = shared_cache / "powershell" / "StartupProfileData-NonInteractive"
    profile.parent.mkdir(parents=True)
    sentinel = b"parent-process-startup-cache"
    profile.write_bytes(sentinel)
    monkeypatch.setenv("XDG_CACHE_HOME", str(shared_cache))
    parent_environment = os.environ.copy()
    project, _ = _fixture_project(tmp_path)
    state_root = (
        tmp_path
        / "temp"
        / "ue-live-acceptance"
        / f"run-prepare-only-{uuid.uuid4().hex}"
    )
    state_root.parent.mkdir(parents=True)
    spec = importlib.util.spec_from_file_location(
        "live_stand_prepare_only_proof", ROOT / "scripts" / "live_stand.py"
    )
    assert spec is not None and spec.loader is not None
    live_stand = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = live_stand
    spec.loader.exec_module(live_stand)
    live_stand.REPO_ROOT = project
    live_stand.WORKTREE = state_root
    live_stand.IN_PLACE_MODE = True
    live_stand.SOURCE_SHA = "a" * 40
    live_stand.docker_daemon_fingerprint = lambda: "d" * 64
    live_stand._ensure_private_state_directory(state_root, protect_new_windows=True)
    owner = live_stand.create_stand_owner(
        state_root,
        published_ports=live_stand.choose_published_ports(),
    )
    vapid = live_stand.load_or_create_vapid(state_root)
    live_stand._write_in_place_compose_override(state_root)
    environment = live_stand.stand_environment(
        vapid, owner.project_name, dict(owner.published_ports)
    )
    environment["TEMP"] = str(state_root.parents[1])
    environment["TMP"] = str(state_root.parents[1])
    if os.name != "nt":
        environment["TMPDIR"] = str(state_root.parents[1])

    result = _run_prepare(project, state_root, environment)

    assert result.returncode == 0, f"PrepareOnly exited with status {result.returncode}"
    assert profile.read_bytes() == sentinel
    assert os.environ == parent_environment
    assert (state_root / ".env").is_file()
    assert (state_root / ".env.docker").is_file()
    assert (state_root / ".env.docker.workers").is_file()
    if os.name == "nt":
        for path in (
            state_root,
            state_root / ".secrets",
            state_root / ".secrets" / "live-stand-owner.key",
            state_root / ".secrets" / "live-stand.json",
            state_root / ".secrets" / "live-vapid.json",
            state_root / "docker-compose.live-state.yml",
            state_root / ".env",
            state_root / ".env.docker",
            state_root / ".env.docker.workers",
            state_root / ".secrets" / "jwt_rs256.pem",
            state_root / ".secrets" / "jwt_rs256.pub.pem",
            state_root / ".secrets" / "temporal_api_key",
        ):
            _assert_windows_private_acl(path)


@pytest.mark.skipif(
    POWERSHELL is None or os.name == "nt",
    reason="requires POSIX permissions and PowerShell 7",
)
def test_launcher_rejects_permissive_owned_state_root_before_secret_reads(
    tmp_path: Path,
) -> None:
    project, state_root = _fixture_project(tmp_path)
    state_root.mkdir(parents=True)
    secrets_root = state_root / ".secrets"
    secrets_root.mkdir()
    (secrets_root / "live-stand-owner.key").write_bytes(
        b"owner-key-fixture-material-32bytes!"[:32]
    )
    public, private = _vapid_pair()
    (secrets_root / "live-vapid.json").write_text(
        json.dumps({"public": public, "private": private}), encoding="utf-8"
    )
    (secrets_root / "live-stand.json").write_text(
        json.dumps(_owner_marker(project, state_root)), encoding="utf-8"
    )
    (state_root / "docker-compose.live-state.yml").write_text(
        "services: {}\n", encoding="utf-8"
    )
    _secure_state_tree(state_root)
    state_root.chmod(0o755)

    result = _run_prepare(
        project,
        state_root,
        _live_environment(state_root, public, private),
    )

    assert result.returncode != 0
    assert "private permissions" in (result.stdout + result.stderr).lower()
    assert not (state_root / ".env").exists()
    assert not (state_root / ".env.docker").exists()


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell 7 (pwsh) is unavailable")
def test_launcher_rejects_compose_without_override_support_before_env_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared_cache = tmp_path / "shared-cache"
    profile = shared_cache / "powershell" / "StartupProfileData-NonInteractive"
    profile.parent.mkdir(parents=True)
    sentinel = b"parent-process-startup-cache"
    profile.write_bytes(sentinel)
    monkeypatch.setenv("XDG_CACHE_HOME", str(shared_cache))
    parent_environment = os.environ.copy()
    project, state_root = _fixture_project(tmp_path)
    state_root.mkdir(parents=True)
    secrets_root = state_root / ".secrets"
    secrets_root.mkdir()
    (secrets_root / "live-stand-owner.key").write_bytes(
        b"owner-key-fixture-material-32bytes!"[:32]
    )
    public, private = _vapid_pair()
    (secrets_root / "live-vapid.json").write_text(
        json.dumps({"public": public, "private": private}), encoding="utf-8"
    )
    (secrets_root / "live-stand.json").write_text(
        json.dumps(_owner_marker(project, state_root)), encoding="utf-8"
    )
    (state_root / "docker-compose.live-state.yml").write_text(
        "services: {}\n", encoding="utf-8"
    )
    _secure_state_tree(state_root)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    command_log = tmp_path / "docker-commands.txt"
    if os.name == "nt":
        fake_docker = fake_bin / "docker.cmd"
        fake_docker.write_text(
            "@echo off\r\n"
            '>>"%LIVE_STAND_DOCKER_LOG%" echo %*\r\n'
            'if "%1"=="compose" if "%2"=="version" echo v2.24.3\r\n'
            "exit /b 0\r\n",
            encoding="utf-8",
        )
    else:
        # PowerShell on Unix invokes native executables, not Windows batch files.
        fake_docker = fake_bin / "docker"
        fake_docker.write_text(
            "#!/bin/sh\n"
            'printf "%s\\n" "$*" >> "$LIVE_STAND_DOCKER_LOG"\n'
            'if [ "$1" = compose ] && [ "${2:-}" = version ]; then\n'
            '  printf "v2.24.3\\n"\n'
            "fi\nexit 0\n",
            encoding="utf-8",
        )
        fake_docker.chmod(0o700)
    env = _live_environment(state_root, public, private)
    env["PATH"] = os.pathsep.join((str(fake_bin), env.get("PATH", "")))
    env["LIVE_STAND_DOCKER_LOG"] = str(command_log)

    assert POWERSHELL is not None
    result = subprocess.run(  # noqa: S603 - fixed PowerShell file and test-owned launcher args
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(project / "start-docker.ps1"),
            "-Build",
            "-ExtraCompose",
            "docker-compose.live.yml",
            "-LiveStandStateRoot",
            str(state_root),
        ],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode != 0
    assert "Docker Compose 2.24.4 or newer" in (result.stdout + result.stderr)
    assert command_log.read_text(encoding="utf-8").splitlines() == [
        "info",
        "compose version --short",
    ]
    assert not (state_root / ".env").exists()
    assert not (state_root / ".env.docker").exists()
    assert not (project / ".env").exists()
    assert not (project / ".secrets").exists()
    assert profile.read_bytes() == sentinel
    assert os.environ == parent_environment
