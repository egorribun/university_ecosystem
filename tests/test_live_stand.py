"""Contracts for the owned live acceptance stand launcher."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
import yaml
from py_vapid import Vapid

from tests.helpers.synthetic_credentials import make_test_password

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "live_stand", ROOT / "scripts" / "live_stand.py"
)
assert _SPEC is not None and _SPEC.loader is not None
live_stand = importlib.util.module_from_spec(_SPEC)
sys.modules["live_stand"] = live_stand
_SPEC.loader.exec_module(live_stand)


@pytest.fixture(scope="session")
def git_executable() -> str:
    executable = shutil.which("git")
    if executable is None:
        pytest.fail("git is required for in-place source-guard tests", pytrace=False)
    return executable


def _initialize_git_repository(git_executable: str, repository: Path) -> None:
    subprocess.run(  # noqa: S603 - validated Git executable and fixed argv
        [git_executable, "init", "--quiet"],
        cwd=repository,
        check=True,
        capture_output=True,
    )


def _tracked_frontend_live_files(
    git_executable: str, *, working_directory: Path
) -> list[str]:
    repository_root = subprocess.run(  # noqa: S603 - validated Git executable and fixed argv
        [git_executable, "rev-parse", "--show-toplevel"],
        cwd=working_directory,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    return subprocess.run(  # noqa: S603 - validated Git executable and fixed argv
        [git_executable, "ls-files", "--", "frontend/tests/e2e-live"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()


def _unb64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _port_map(start: int = 24000) -> dict[str, int]:
    return {
        name: start + index
        for index, (name, _service, _container_port) in enumerate(
            live_stand.LIVE_PORT_SPECS
        )
    }


def _windows_acl_summary(path: Path) -> dict[str, object]:
    powershell = shutil.which("pwsh") or shutil.which("powershell.exe")
    assert powershell is not None
    env = os.environ.copy()
    env["LIVE_STAND_ACL_TARGET"] = str(path)
    script = r"""
$ErrorActionPreference = 'Stop'
$acl = Get-Acl -LiteralPath $env:LIVE_STAND_ACL_TARGET
$ownerSid = ([System.Security.Principal.NTAccount]::new($acl.Owner)).Translate([System.Security.Principal.SecurityIdentifier]).Value
$rules = @($acl.Access | ForEach-Object {
    [pscustomobject]@{
        Sid = $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
        Type = $_.AccessControlType.ToString()
        Rights = $_.FileSystemRights.ToString()
        Inheritance = $_.InheritanceFlags.ToString()
    }
})
[pscustomobject]@{ OwnerSid = $ownerSid; Rules = $rules } | ConvertTo-Json -Depth 5 -Compress
"""
    result = subprocess.run(  # noqa: S603 - fixed PowerShell executable and constant script
        [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0
    return json.loads(result.stdout)


def _assert_compose_port_environment(
    environment: dict[str, str], ports: dict[str, int] | tuple[tuple[str, int], ...]
) -> None:
    port_map = dict(ports)
    for name, _service, _target in live_stand.LIVE_PORT_SPECS:
        environment_name = (
            "LIVE_MAILPIT_PORT" if name == "MAILPIT" else f"LIVE_HOST_PORT_{name}"
        )
        assert environment[environment_name] == str(port_map[name])


def _make_windows_junction(link: Path, target: Path) -> None:
    # Fixed Windows builtin; paths are fresh pytest temporary-directory paths.
    result = subprocess.run(  # noqa: S603 -- fixed Windows builtin, temp paths only
        ["cmd.exe", "/c", "mklink", "/J", str(link), str(target)],  # noqa: S607
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        # QUALITY-123 @egorribun — temporary filesystem may not support junctions.
        pytest.skip("could not create a temporary Windows junction")


def test_vapid_keys_use_the_web_push_encoding_and_match() -> None:
    keys = live_stand.generate_vapid_keys()

    public = _unb64url(keys["public"])
    assert len(public) == 65 and public[0] == 0x04
    assert len(_unb64url(keys["private"])) == 32
    assert "=" not in keys["public"] + keys["private"]

    vapid = Vapid.from_string(keys["private"])
    derived = vapid.public_key.public_bytes(
        live_stand.serialization.Encoding.X962,
        live_stand.serialization.PublicFormat.UncompressedPoint,
    )
    assert derived == public


def test_vapid_keys_are_created_once_per_worktree(tmp_path: Path) -> None:
    first = live_stand.load_or_create_vapid(tmp_path)
    second = live_stand.load_or_create_vapid(tmp_path)

    assert first == second
    assert json.loads((tmp_path / ".secrets" / "live-vapid.json").read_text()) == first


def test_stand_admin_password_is_persisted_and_bound_to_its_owner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repository = tmp_path / "repository"
    worktree = tmp_path / "ue-live"
    repository.mkdir()
    worktree.mkdir()
    owner = live_stand.StandOwner(
        repository=str(repository.resolve()),
        worktree=str(worktree.resolve()),
        project_name="ue-live-0123456789abcdef",
        published_ports=tuple(_port_map().items()),
        schema_version=live_stand.OWNER_SCHEMA_VERSION,
    )
    generated_sizes: list[int] = []

    def generate_password(size: int) -> str:
        generated_sizes.append(size)
        return "owner-scoped-test-password-long-enough-for-testing"

    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand.secrets, "token_urlsafe", generate_password)

    first = live_stand.load_or_create_stand_admin_password(worktree, owner)
    second = live_stand.load_or_create_stand_admin_password(worktree, owner)
    saved = json.loads(
        (worktree / ".secrets" / "live-admin-password.json").read_text(encoding="utf-8")
    )

    if first != second or generated_sizes != [32]:
        pytest.fail("the same stand must reuse one persisted admin password")
    if (
        saved.get("project_name") != owner.project_name
        or saved.get("password") != first
    ):
        pytest.fail("the persisted credential must be bound to this stand")
    if os.name != "nt" and (
        (worktree / ".secrets" / "live-admin-password.json").stat().st_mode & 0o077
    ):
        pytest.fail("the persisted credential must not be group/world accessible")
    captured = capsys.readouterr()
    if first in captured.out or first in captured.err:
        pytest.fail("the stand admin credential must never be printed")


def test_stand_admin_password_rejects_credential_from_another_owner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    worktree = tmp_path / "ue-live"
    repository.mkdir()
    worktree.mkdir()
    original_owner = live_stand.StandOwner(
        repository=str(repository.resolve()),
        worktree=str(worktree.resolve()),
        project_name="ue-live-0123456789abcdef",
        published_ports=tuple(_port_map().items()),
        schema_version=live_stand.OWNER_SCHEMA_VERSION,
    )
    replacement_owner = live_stand.StandOwner(
        repository=original_owner.repository,
        worktree=original_owner.worktree,
        project_name="ue-live-fedcba9876543210",
        published_ports=original_owner.published_ports,
        schema_version=original_owner.schema_version,
    )
    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(
        live_stand.secrets,
        "token_urlsafe",
        lambda _size: "owner-scoped-test-password-long-enough-for-testing",
    )

    live_stand.load_or_create_stand_admin_password(worktree, original_owner)

    with pytest.raises(live_stand.StandError, match="different live stand"):
        live_stand.load_or_create_stand_admin_password(worktree, replacement_owner)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction and symlink behavior")
@pytest.mark.parametrize("operation", ["owner", "vapid"])
def test_secrets_junction_is_rejected_before_any_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, operation: str
) -> None:
    repo_root = tmp_path / "repo"
    git_dir = repo_root / ".git"
    worktree = tmp_path / "ue-live"
    outside = tmp_path / "outside"
    git_dir.mkdir(parents=True)
    worktree.mkdir()
    outside.mkdir()
    _make_windows_junction(worktree / ".secrets", outside)

    monkeypatch.setattr(live_stand, "REPO_ROOT", repo_root)
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "_git", lambda *_: ".git")

    with pytest.raises(live_stand.StandError, match="reparse point"):
        if operation == "owner":
            live_stand.create_stand_owner(worktree)
        else:
            live_stand.load_or_create_vapid(worktree)

    assert list(outside.iterdir()) == []
    assert list(git_dir.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_expected_worktree_rejects_windows_junction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "real-worktree"
    target.mkdir()
    junction = tmp_path / "ue-live"
    _make_windows_junction(junction, target)
    monkeypatch.setattr(live_stand, "WORKTREE", junction)

    with pytest.raises(live_stand.StandError, match="reparse point"):
        live_stand._expected_worktree(junction)


@pytest.mark.skipif(os.name != "nt", reason="Windows dangling symlink behavior")
def test_dangling_vapid_symlink_is_rejected_before_key_generation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secrets_dir = tmp_path / ".secrets"
    secrets_dir.mkdir()
    target = tmp_path / "external-vapid.json"
    vapid_path = secrets_dir / "live-vapid.json"
    try:
        vapid_path.symlink_to(target)
    except OSError as error:
        # QUALITY-123 @egorribun — Windows symlink privilege varies by runner.
        pytest.skip(f"symlink creation is unavailable: {error}")

    generated = False

    def generate() -> dict[str, str]:
        nonlocal generated
        generated = True
        return {"public": "public", "private": "private"}

    monkeypatch.setattr(live_stand, "WORKTREE", tmp_path)
    monkeypatch.setattr(live_stand, "generate_vapid_keys", generate)

    with pytest.raises(live_stand.StandError, match="reparse point"):
        live_stand.load_or_create_vapid(tmp_path)

    assert not generated
    assert not target.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows dangling symlink behavior")
def test_stand_path_preflight_rejects_dangling_env_symlink(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "external.env"
    env_file = tmp_path / ".env"
    try:
        env_file.symlink_to(target)
    except OSError as error:
        # QUALITY-123 @egorribun — Windows symlink privilege varies by runner.
        pytest.skip(f"symlink creation is unavailable: {error}")
    monkeypatch.setattr(live_stand, "WORKTREE", tmp_path)

    with pytest.raises(live_stand.StandError, match="reparse point"):
        live_stand._assert_stand_paths_safe(tmp_path)

    assert not target.exists()


def test_corrupt_vapid_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / ".secrets" / "live-vapid.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"public": "x"}))

    with pytest.raises(live_stand.StandError, match="does not hold a VAPID key pair"):
        live_stand.load_or_create_vapid(tmp_path)


def test_stand_environment_pins_the_project_and_keys() -> None:
    project_name = "ue-live-0123456789abcdef"
    ports = _port_map()
    env = live_stand.stand_environment(
        {"public": "pub", "private": "priv"}, project_name, ports
    )

    assert env["COMPOSE_PROJECT_NAME"] == project_name
    assert env["LIVE_VAPID_PUBLIC_KEY"] == "pub"
    assert env["LIVE_VAPID_PRIVATE_KEY"] == "priv"  # pragma: allowlist secret
    assert env["LIVE_BASE_URL"] == f"http://localhost:{ports['CADDY_HTTP']}"
    assert env["LIVE_MAILPIT_PORT"] == str(ports["MAILPIT"])
    for name, port in ports.items():
        if name != "MAILPIT":
            assert env[f"LIVE_HOST_PORT_{name}"] == str(port)


def test_trusted_proxy_configuration_keeps_refresh_scope_without_peer_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    owner = object()
    evidence = SimpleNamespace(fingerprint="stable-evidence")
    peer_addresses = ("synthetic-peer-secret-a", "synthetic-peer-secret-b")
    settings = {
        "TRUSTED_PROXIES": (),
        "GATEWAY_TRUSTED_PROXIES": peer_addresses,
        "WS_HUB_TRUSTED_PROXIES": peer_addresses,
    }
    addresses = {"caddy": "caddy", "gateway": "gateway", "ws-hub": "ws-hub"}
    network_ids = {"network": "stable-network"}

    monkeypatch.setattr(
        live_stand, "_assert_live_trusted_proxy_source_current", lambda *_args: None
    )
    monkeypatch.setattr(live_stand, "_require_owned_docker_daemon", lambda *_args: None)
    monkeypatch.setattr(
        live_stand,
        "_verify_stand_owner_compose_resources",
        lambda *_args: evidence,
    )
    monkeypatch.setattr(
        live_stand, "_require_live_trusted_proxy_http_health", lambda *_args: None
    )
    monkeypatch.setattr(
        live_stand,
        "_capture_live_trusted_proxy_inventory",
        lambda *_args: ({}, settings, addresses, network_ids),
    )
    refreshes: list[tuple[Mapping[str, object], str]] = []

    def capture_refresh(
        _owner: object,
        _environment: Mapping[str, str],
        actual_settings: Mapping[str, object],
        phase: str,
    ) -> None:
        refreshes.append((actual_settings, phase))

    monkeypatch.setattr(live_stand, "_run_live_trusted_proxy_refresh", capture_refresh)
    monkeypatch.setattr(
        live_stand, "_assert_live_trusted_proxy_container_delta", lambda *_args: None
    )
    monkeypatch.setattr(
        live_stand,
        "_assert_live_trusted_proxy_network_ids_unchanged",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        live_stand, "_assert_live_trusted_proxy_environment", lambda *_args: None
    )

    live_stand._configure_live_trusted_proxy_peers(owner, {}, evidence)

    expected_settings = {
        "TRUSTED_PROXIES": (),
        "GATEWAY_TRUSTED_PROXIES": peer_addresses,
        "WS_HUB_TRUSTED_PROXIES": peer_addresses,
    }
    assert refreshes == [
        (expected_settings, "edge"),
        (expected_settings, "backend"),
    ]
    assert capsys.readouterr().out == ""


def test_compose_command_targets_only_the_stand_project() -> None:
    assert live_stand.compose_command(
        "ps", project_name="ue-live-0123456789abcdef"
    ) == [
        "docker",
        "compose",
        "-p",
        "ue-live-0123456789abcdef",
        "--env-file",
        ".env.docker",
        "-f",
        "docker-compose.full.yml",
        "-f",
        "docker-compose.live.yml",
        "ps",
    ]


def test_in_place_compose_command_uses_the_shared_live_overlay(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    state_root = tmp_path / "state"
    state_root.mkdir()
    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", state_root)
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", True)

    command = live_stand.compose_command("ps", project_name="ue-live-0123456789abcdef")

    assert command[command.index("-f") + 1] == str(
        repository / "docker-compose.full.yml"
    )
    assert command[command.index("-f") + 3] == str(
        repository / "docker-compose.live.yml"
    )
    assert command[command.index("-f") + 5] == str(
        state_root / live_stand.IN_PLACE_OVERLAY
    )


def test_seed_cli_reuses_owner_scoped_password_only_for_the_admin_seed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    from contextlib import nullcontext

    worktree = tmp_path / "ue-live"
    worktree.mkdir()
    owner = live_stand.StandOwner(
        repository=str(ROOT),
        worktree=str(worktree),
        project_name="ue-live-0123456789abcdef",
        published_ports=tuple(_port_map().items()),
        schema_version=live_stand.OWNER_SCHEMA_VERSION,
    )
    runs: list[tuple[list[str], dict[str, str]]] = []
    token_sizes: list[int] = []
    original_token_urlsafe = live_stand.secrets.token_urlsafe
    inherited_password = original_token_urlsafe(32)
    base_environment = {"COMPOSE_PROJECT_NAME": owner.project_name}
    base_environment["TEST_PASSWORD"] = inherited_password

    def generate_token(size: int) -> str:
        token_sizes.append(size)
        return original_token_urlsafe(size)

    monkeypatch.setattr(live_stand.secrets, "token_urlsafe", generate_token)
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "stand_lifecycle_lock", nullcontext)
    monkeypatch.setattr(live_stand, "_require_worktree", lambda **_kwargs: None)
    monkeypatch.setattr(live_stand, "load_stand_owner", lambda _path: owner)
    daemon_checks: list[
        tuple[
            live_stand.StandOwner,
            float | None,
            live_stand._LiveDockerReadContext | None,
        ]
    ] = []

    def require_owned_docker_daemon(
        checked_owner: live_stand.StandOwner,
        *,
        deadline: float | None = None,
        docker_context: live_stand._LiveDockerReadContext | None = None,
    ) -> None:
        assert checked_owner == owner
        assert deadline is None
        assert docker_context is None
        daemon_checks.append((checked_owner, deadline, docker_context))

    monkeypatch.setattr(
        live_stand,
        "_require_owned_docker_daemon",
        require_owned_docker_daemon,
    )
    resource_checks: list[
        tuple[
            Path,
            live_stand.StandOwner,
            float | None,
            live_stand._LiveDockerReadContext | None,
        ]
    ] = []

    def verify_compose_resources(
        checked_worktree: Path,
        checked_owner: live_stand.StandOwner,
        *,
        deadline: float | None = None,
        docker_context: live_stand._LiveDockerReadContext | None = None,
    ) -> None:
        assert checked_worktree == worktree
        assert checked_owner == owner
        assert deadline is None
        assert docker_context is None
        resource_checks.append(
            (checked_worktree, checked_owner, deadline, docker_context)
        )

    monkeypatch.setattr(
        live_stand,
        "_verify_stand_owner_compose_resources",
        verify_compose_resources,
    )
    monkeypatch.setattr(
        live_stand,
        "load_vapid",
        lambda _path: {"public": "public-key", "private": "private-key"},
    )
    monkeypatch.setattr(
        live_stand,
        "stand_environment",
        lambda _keys, _project, _ports: dict(base_environment),
    )
    monkeypatch.setattr(
        live_stand,
        "compose_command",
        lambda *args, project_name: list(args),
    )
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, *, cwd, env: runs.append((list(command), dict(env))),
    )

    assert live_stand.main(["seed", "--demo"]) == 0
    assert live_stand.main(["seed", "--demo"]) == 0

    if len(runs) != 6 or token_sizes != [32]:
        pytest.fail("repeated seed invocations must reuse one owner-scoped password")

    admin_commands = [runs[1][0], runs[4][0]]
    admin_environments = [runs[1][1], runs[4][1]]
    non_admin_environments = [runs[index][1] for index in (0, 2, 3, 5)]
    expected_seed_environment = {
        "COMPOSE_PROJECT_NAME": owner.project_name,
        "LIVE_STAND_OWNER_VERIFIED": "1",
        "LIVE_STAND_SEED_PROJECT": owner.project_name,
    }
    for command, _environment in runs:
        for name, value in expected_seed_environment.items():
            if not any(
                command[index] == "--env"
                and index + 1 < len(command)
                and command[index + 1] == f"{name}={value}"
                for index in range(len(command))
            ):
                pytest.fail("live seed command omitted its verified owner target")
    if [check[0] for check in daemon_checks] != [owner] * 8:
        pytest.fail("each seed subprocess must reverify the owned Docker daemon")
    if [check[1] for check in resource_checks] != [owner] * 6:
        pytest.fail("each seed subprocess must verify signed Compose resources")
    if any("TEST_PASSWORD" in environment for environment in non_admin_environments):
        pytest.fail("only admin-account seeding may receive the admin password")

    generated_passwords = [
        environment.get("TEST_PASSWORD") for environment in admin_environments
    ]
    if not all(
        isinstance(password, str)
        and len(password) >= 44
        and any(character.isupper() for character in password)
        and any(character.islower() for character in password)
        and any(character.isdigit() for character in password)
        and any(not character.isalnum() for character in password)
        for password in generated_passwords
    ):
        pytest.fail("admin seeding must receive a strong generated password")
    if generated_passwords[0] != generated_passwords[1]:
        pytest.fail("separate seed invocations must reuse the persisted password")
    if any(password == inherited_password for password in generated_passwords):
        pytest.fail("admin seeding must replace inherited passwords with fresh values")
    if any(
        "-e" not in command
        or "TEST_PASSWORD" not in command
        or command.index("TEST_PASSWORD") > command.index("backend")
        for command in admin_commands
    ):
        pytest.fail("Compose must explicitly pass TEST_PASSWORD to the backend")

    captured = capsys.readouterr()
    if any(
        password in captured.out or password in captured.err
        for password in generated_passwords
        if password is not None
    ):
        pytest.fail("live-stand seed must not log the generated password")


def test_seed_refuses_ownership_metadata_changed_after_it_was_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = live_stand.StandOwner(
        repository=str(ROOT),
        worktree=str(live_stand.WORKTREE),
        project_name="ue-live-0123456789abcdef",
        published_ports=tuple(_port_map().items()),
        schema_version=live_stand.OWNER_SCHEMA_VERSION,
    )
    changed_owner = live_stand.StandOwner(
        repository=owner.repository,
        worktree=owner.worktree,
        project_name="ue-live-fedcba9876543210",
        published_ports=owner.published_ports,
        schema_version=owner.schema_version,
    )
    monkeypatch.setattr(live_stand, "_require_worktree", lambda: None)
    monkeypatch.setattr(live_stand, "load_stand_owner", lambda _path: changed_owner)

    def unexpected_daemon_check(
        checked_owner: live_stand.StandOwner,
        *,
        deadline: float | None = None,
        docker_context: live_stand._LiveDockerReadContext | None = None,
    ) -> None:
        assert checked_owner == changed_owner
        assert deadline is None
        assert docker_context is None
        pytest.fail("daemon check ran with stale ownership data")

    monkeypatch.setattr(
        live_stand,
        "_require_owned_docker_daemon",
        unexpected_daemon_check,
    )

    with pytest.raises(live_stand.StandError, match="metadata changed"):
        live_stand._seed_locked("", owner=owner)


@pytest.mark.parametrize("in_place_mode", [False, True], ids=["legacy", "in-place"])
def test_e2e_reuses_owner_scoped_admin_password_across_reruns(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    in_place_mode: bool,
) -> None:
    from contextlib import nullcontext

    if in_place_mode:
        monkeypatch.setattr(live_stand.tempfile, "gettempdir", lambda: str(tmp_path))
        worktree = tmp_path / live_stand.IN_PLACE_STATE_PARENT / "run-e2e-case"
        worktree.mkdir(parents=True)
    else:
        worktree = tmp_path / "ue-live"
        worktree.mkdir()
    port_map = _port_map()
    owner = live_stand.StandOwner(
        repository=str(ROOT),
        worktree=str(worktree),
        project_name="ue-live-0123456789abcdef",
        published_ports=tuple(port_map.items()),
        schema_version=(
            live_stand.IN_PLACE_OWNER_SCHEMA_VERSION
            if in_place_mode
            else live_stand.OWNER_SCHEMA_VERSION
        ),
    )
    runs: list[tuple[list[str], Path, dict[str, str]]] = []
    playwright_runs: list[tuple[Path, dict[str, str], str, bool, bool]] = []
    playwright_environment_objects: list[dict[str, str]] = []
    playwright_failures_remaining = 0
    probe_nonce = "f" * 32
    probe_correlation_ids = {"desktop": "a" * 32, "mobile": "b" * 32}
    docker_context = object()
    container_pin = ("c" * 64, "d" * 64)
    e2e_daemon_calls: list[tuple[float | None, object | None]] = []
    e2e_resource_calls: list[tuple[float | None, object | None]] = []
    caddy_pin_calls: list[tuple[float | None, object | None]] = []
    probe_log_calls: list[
        tuple[int, int, str, dict[str, str], tuple[str, str], object | None]
    ] = []
    dependency_runs: list[tuple[Path, dict[str, str]]] = []
    owner_marker_paths: list[Path] = []
    event_order: list[str] = []
    token_sizes: list[int] = []
    original_token_urlsafe = live_stand.secrets.token_urlsafe
    ambient_password = original_token_urlsafe(32)
    vapid_keys = live_stand.generate_vapid_keys()
    base_environment = {
        "COMPOSE_PROJECT_NAME": owner.project_name,
        "LIVE_VAPID_PUBLIC_KEY": vapid_keys["public"],
        "LIVE_VAPID_PRIVATE_KEY": vapid_keys["private"],
        "LIVE_HOST_PORT_CADDY_HTTP": str(port_map["CADDY_HTTP"]),
        "LIVE_MAILPIT_PORT": str(port_map["MAILPIT"]),
        "TEST_PASSWORD": ambient_password,
    }
    forwarded_secret_names = (
        "CHROMATIC_PROJECT_TOKEN",
        "GH_TOKEN",
        "ACTIONS_RUNTIME_TOKEN",
        "GITHUB_TOKEN",
        "NPM_TOKEN",
        "NODE_AUTH_TOKEN",
        "UNRELATED_API_KEY",
        "NODE_OPTIONS",
        "NPM_CONFIG_REGISTRY",
    )
    caller_repository_root = "C:/caller-controlled-primary-root"
    caller_state_root = "C:/caller-controlled-state-root"
    forwarded_secret_values = {
        name: f"caller-sentinel-{index}"
        for index, name in enumerate(forwarded_secret_names)
    }
    inherited_npm_config_names = (
        "NPM_CONFIG_USERCONFIG",
        "NPM_CONFIG_GLOBALCONFIG",
    )
    inherited_npm_config_values = {
        name: f"caller-config-sentinel-{index}"
        for index, name in enumerate(inherited_npm_config_names)
    }

    def generate_token(size: int) -> str:
        token_sizes.append(size)
        return original_token_urlsafe(size)

    def capture_run(
        command: list[str], *, cwd: Path, env: dict[str, str] | None
    ) -> None:
        print("+", " ".join(command))
        runs.append((list(command), cwd, dict(env or {})))
        event_order.append("seed")

    def capture_dependency_bootstrap(
        frontend: Path, environment: dict[str, str]
    ) -> None:
        dependency_runs.append((frontend, dict(environment)))
        event_order.append("bootstrap")

    def capture_playwright(
        *, cwd: Path, environment: dict[str, str], mode: str = "full"
    ) -> None:
        nonlocal playwright_failures_remaining
        if mode != "full":
            pytest.fail("the default E2E mode must continue to run the full suite")
        print("+", " ".join(live_stand._live_e2e_command(mode=mode)))
        event_order.append("playwright")
        playwright_environment_objects.append(environment)
        output_directory = environment.get("LIVE_E2E_OUTPUT_DIR", "")
        output_path = Path(output_directory)
        if environment.get("PLAYWRIGHT_TEST_OUTPUT_DIR") != output_directory:
            pytest.fail("Playwright output aliases must share one owned directory")
        owner_marker = output_path.parent / live_stand.LIVE_E2E_OUTPUT_OWNER_MARKER
        if (
            not owner_marker.is_file()
            or owner_marker.read_bytes()
            != live_stand.LIVE_E2E_OUTPUT_OWNER_MARKER_CONTENT.encode("utf-8")
        ):
            pytest.fail("Playwright output must have a temporary ownership marker")
        owner_marker_paths.append(owner_marker)
        # Playwright clears its outputDir before execution; npm configs must survive.
        output_path.rmdir()
        output_path.mkdir()
        admin_password = environment.get("TEST_PASSWORD", "")
        config_paths = (
            Path(environment.get("NPM_CONFIG_USERCONFIG", "")),
            Path(environment.get("NPM_CONFIG_GLOBALCONFIG", "")),
        )
        configs_are_empty = all(
            path.is_file() and path.read_bytes() == b"" for path in config_paths
        )
        playwright_runs.append(
            (
                cwd,
                dict(environment),
                admin_password,
                bool(output_directory and Path(output_directory).is_dir()),
                configs_are_empty,
            )
        )
        if playwright_failures_remaining:
            playwright_failures_remaining -= 1
            raise live_stand.StandError("synthetic live Playwright failure")

    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", in_place_mode)
    monkeypatch.setenv("TEST_PASSWORD", ambient_password)
    monkeypatch.setenv("LIVE_PRIMARY_REPOSITORY_ROOT", caller_repository_root)
    monkeypatch.setenv("LIVE_STAND_STATE_ROOT", caller_state_root)
    for name, value in forwarded_secret_values.items():
        monkeypatch.setenv(name, value)
    for name, value in inherited_npm_config_values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(live_stand.secrets, "token_urlsafe", generate_token)
    monkeypatch.setattr(live_stand, "stand_lifecycle_lock", nullcontext)
    monkeypatch.setattr(live_stand, "_require_worktree", lambda: None)
    monkeypatch.setattr(live_stand, "load_stand_owner", lambda _path: owner)

    def require_owned_docker_daemon(
        checked_owner: live_stand.StandOwner,
        *,
        deadline: float | None = None,
        docker_context: object | None = None,
    ) -> None:
        assert checked_owner == owner
        e2e_daemon_calls.append((deadline, docker_context))

    def verify_compose_resources(
        checked_worktree: Path,
        checked_owner: live_stand.StandOwner,
        *,
        deadline: float | None = None,
        docker_context: object | None = None,
    ) -> None:
        assert checked_worktree == worktree
        assert checked_owner == owner
        e2e_resource_calls.append((deadline, docker_context))

    def verify_caddy_pin(
        checked_owner: live_stand.StandOwner,
        *,
        deadline: float | None = None,
        docker_context: object | None = None,
    ) -> tuple[str, str]:
        assert checked_owner == owner
        assert deadline is not None
        assert docker_context is expected_docker_context
        caddy_pin_calls.append((deadline, docker_context))
        return container_pin

    def verify_probe_log(
        checked_owner: live_stand.StandOwner,
        output_directory: Path,
        *,
        started_at_ms: int,
        finished_at_ms: int,
        password_nonce: str,
        correlation_ids: Mapping[str, str],
        container_pin: tuple[str, str],
        docker_context: object | None = None,
    ) -> None:
        assert checked_owner == owner
        assert output_directory.is_dir()
        assert finished_at_ms >= started_at_ms
        assert password_nonce == probe_nonce
        assert dict(correlation_ids) == probe_correlation_ids
        assert container_pin == expected_container_pin
        assert docker_context is expected_docker_context
        probe_log_calls.append(
            (
                started_at_ms,
                finished_at_ms,
                password_nonce,
                dict(correlation_ids),
                container_pin,
                docker_context,
            )
        )

    expected_docker_context = docker_context
    expected_container_pin = container_pin
    monkeypatch.setattr(
        live_stand, "_new_live_docker_read_context", lambda: expected_docker_context
    )
    monkeypatch.setattr(
        live_stand,
        "_new_live_caddy_probe_values",
        lambda: (probe_nonce, dict(probe_correlation_ids)),
    )
    monkeypatch.setattr(live_stand, "_verified_live_caddy_container", verify_caddy_pin)
    monkeypatch.setattr(live_stand, "_verify_live_caddy_probe_log", verify_probe_log)
    monkeypatch.setattr(
        live_stand, "_require_owned_docker_daemon", require_owned_docker_daemon
    )
    monkeypatch.setattr(
        live_stand,
        "_verify_stand_owner_compose_resources",
        verify_compose_resources,
    )
    monkeypatch.setattr(
        live_stand,
        "load_vapid",
        lambda _path: {"public": "public-key", "private": "private-key"},
    )
    monkeypatch.setattr(
        live_stand,
        "stand_environment",
        lambda _keys, _project, _ports: dict(base_environment),
    )
    monkeypatch.setattr(
        live_stand,
        "compose_command",
        lambda *args, project_name: list(args),
    )
    monkeypatch.setattr(live_stand, "_run", capture_run)
    monkeypatch.setattr(
        live_stand, "_ensure_live_e2e_dependencies", capture_dependency_bootstrap
    )
    monkeypatch.setattr(live_stand, "_run_live_playwright", capture_playwright)

    e2e_arguments = ["e2e"]
    if in_place_mode:
        e2e_arguments.extend(("--in-place", "--state-dir", str(worktree)))

    try:
        if live_stand.main(e2e_arguments) != 0:
            pytest.fail("the E2E orchestration command should complete successfully")
        if live_stand.main(e2e_arguments) != 0:
            pytest.fail("a second E2E run against the preserved stand should succeed")

        if (
            len(runs) != 6
            or len(dependency_runs) != 2
            or len(playwright_runs) != 2
            or token_sizes != [32]
        ):
            pytest.fail(
                "two E2E runs must reuse one persisted password and each run all seeds"
            )
        if event_order != [
            "seed",
            "seed",
            "seed",
            "bootstrap",
            "playwright",
            "seed",
            "seed",
            "seed",
            "bootstrap",
            "playwright",
        ]:
            pytest.fail("locked dependencies must be ready before Playwright starts")
        if len(e2e_daemon_calls) != 10 or len(e2e_resource_calls) != 8:
            pytest.fail("legacy fixture callbacks must retain each optional read pin")
        if len(caddy_pin_calls) != 2 or len(probe_log_calls) != 2:
            pytest.fail("each successful probe run must verify its pinned Caddy log")
        for run_index, (deadline, context) in enumerate(caddy_pin_calls):
            if deadline is None or context is not expected_docker_context:
                pytest.fail(
                    "each probe must reuse its pinned Docker context and deadline"
                )
            if e2e_daemon_calls[run_index * 5 + 4] != (deadline, context):
                pytest.fail("the E2E daemon check must share the probe deadline")
            if e2e_resource_calls[run_index * 4 + 3] != (deadline, context):
                pytest.fail("the E2E Compose check must share the probe deadline")
            if any(
                call != (None, None)
                for call in e2e_daemon_calls[run_index * 5 : run_index * 5 + 4]
            ):
                pytest.fail(
                    "seed daemon checks must retain the ordinary no-deadline path"
                )
            if any(
                call != (None, None)
                for call in e2e_resource_calls[run_index * 4 : run_index * 4 + 3]
            ):
                pytest.fail(
                    "seed Compose checks must retain the ordinary no-deadline path"
                )
        if any(
            environment.get("LIVE_CADDY_LOG_PROBE") != probe_nonce
            or json.loads(environment.get("LIVE_CADDY_PROBE_IDS", "{}"))
            != probe_correlation_ids
            for _cwd, environment, _password, _output, _configs in playwright_runs
        ):
            pytest.fail(
                "the Playwright child must receive only this run's probe values"
            )
        if any(marker.exists() for marker in owner_marker_paths):
            pytest.fail(
                "the output ownership marker must be removed with its temp root"
            )
        if any(
            "LIVE_STAND_STATE_ROOT" in environment
            for environment in playwright_environment_objects
        ):
            pytest.fail("the in-place state root must be removed after Playwright")

        demo_command, _demo_cwd, demo_env = runs[0]
        admin_command, _admin_cwd, admin_env = runs[1]
        authorization_command, _authorization_cwd, authorization_env = runs[2]
        second_admin_env = runs[4][2]
        dependency_frontend, dependency_environment = dependency_runs[0]
        (
            e2e_cwd,
            e2e_env,
            playwright_password,
            output_dir_existed,
            npm_configs_empty,
        ) = playwright_runs[0]
        generated_password = admin_env.get("TEST_PASSWORD")
        if not isinstance(generated_password, str):
            pytest.fail("the admin seed must receive its generated password via env")
        if second_admin_env.get("TEST_PASSWORD") != generated_password:
            pytest.fail("a rerun must reuse the persisted stand admin password")
        password_file = worktree / ".secrets" / "live-admin-password.json"
        try:
            stored_password = json.loads(password_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pytest.fail("the owner-scoped admin password must persist across runs")
        if (
            stored_password.get("project_name") != owner.project_name
            or stored_password.get("password") != generated_password
        ):
            pytest.fail("the persisted admin password must belong to this stand")
        if "TEST_PASSWORD" in demo_env or "TEST_PASSWORD" in authorization_env:
            pytest.fail("only the admin account seed may receive the admin password")
        if e2e_env.get("TEST_PASSWORD") != generated_password:
            pytest.fail("the Playwright child must receive the same per-run password")
        if playwright_password != generated_password:
            pytest.fail("the orchestrator must retain only the password for this run")
        if playwright_runs[1][2] != generated_password:
            pytest.fail("a rerun's Playwright login must use the seeded password")
        if generated_password == ambient_password:
            pytest.fail("the E2E command must ignore an inherited password")
        if (
            "scripts/seed_demo_data.py" not in demo_command
            or "scripts/seed_admin_data.py" not in admin_command
            or "scripts/seed_live_authorization.py" not in authorization_command
        ):
            pytest.fail("the E2E command must run demo, admin, and authorization seeds")
        if (
            "-e" not in admin_command
            or "TEST_PASSWORD" not in admin_command
            or any(generated_password in part for part in admin_command)
        ):
            pytest.fail(
                "Compose argv must contain only the variable name, never its value"
            )
        if live_stand.LIVE_E2E_COMMAND != ("npm", "run", "test:e2e:live"):
            pytest.fail(
                "the E2E command must invoke the repository live Playwright script"
            )
        expected_frontend = (ROOT if in_place_mode else worktree) / "frontend"
        if e2e_cwd != expected_frontend:
            pytest.fail("Playwright must run from the selected frontend checkout")
        if dependency_frontend != expected_frontend:
            pytest.fail("dependency bootstrap must use the selected frontend checkout")
        if "TEST_PASSWORD" in dependency_environment:
            pytest.fail("npm bootstrap must not receive the generated admin password")
        if any(
            key in dependency_environment
            for key in (
                "LIVE_BASE_URL",
                "LIVE_MAILPIT_URL",
                "LIVE_PRIMARY_REPOSITORY_ROOT",
            )
        ):
            pytest.fail("npm bootstrap must not receive live endpoints or repo paths")
        expected_live = {
            "LIVE_BASE_URL": f"http://localhost:{port_map['CADDY_HTTP']}",
            "LIVE_MAILPIT_URL": f"http://127.0.0.1:{port_map['MAILPIT']}",
        }
        if any(e2e_env.get(key) != value for key, value in expected_live.items()):
            pytest.fail("Playwright endpoints must come from the owned port metadata")
        expected_repository_root = str(live_stand.REPO_ROOT.resolve(strict=True))
        if e2e_env.get("LIVE_PRIMARY_REPOSITORY_ROOT") != expected_repository_root:
            pytest.fail(
                "Playwright must receive the primary repository path from its launcher"
            )
        if caller_repository_root in e2e_env.values():
            pytest.fail("caller-controlled repository paths must not reach Playwright")
        if in_place_mode:
            if e2e_env.get("LIVE_STAND_STATE_ROOT") != str(
                worktree.resolve(strict=True)
            ):
                pytest.fail("in-place Playwright must receive its owned state root")
        elif (
            "LIVE_STAND_STATE_ROOT" in e2e_env or caller_state_root in e2e_env.values()
        ):
            pytest.fail("legacy Playwright must not receive a caller state root")
        if any(
            key.startswith(("LIVE_VAPID_", "LIVE_HOST_PORT_", "COMPOSE_"))
            for key in e2e_env
        ):
            pytest.fail("Playwright must not inherit Compose or VAPID credentials")
        if any(
            name in e2e_env or value in e2e_env.values()
            for name, value in forwarded_secret_values.items()
        ):
            pytest.fail(
                "caller tokens, API keys, and arbitrary JS options must stay private"
            )
        if "PATH" not in e2e_env:
            pytest.fail("the Playwright child must receive PATH to launch npm and Node")
        output_dir = e2e_env.get("LIVE_E2E_OUTPUT_DIR")
        if e2e_env.get("PLAYWRIGHT_TEST_OUTPUT_DIR") != output_dir:
            pytest.fail("Playwright must receive both aliases for its owned output")
        if not output_dir_existed or not output_dir or Path(output_dir).exists():
            pytest.fail(
                "Playwright output must use a temporary directory removed after exit"
            )
        expected_npm_configs = {
            "NPM_CONFIG_USERCONFIG": Path(output_dir).parent / "npm-userconfig",
            "NPM_CONFIG_GLOBALCONFIG": Path(output_dir).parent / "npm-globalconfig",
        }
        for name, path in expected_npm_configs.items():
            configured_path = e2e_env.get(name)
            if configured_path != str(path) or path.exists():
                pytest.fail(
                    "npm configs must survive output cleanup and then be removed"
                )
            if configured_path in inherited_npm_config_values.values():
                pytest.fail(
                    "caller npm config paths must not reach the Playwright child"
                )
        if not npm_configs_empty:
            pytest.fail("the temporary npm user and global configs must be empty files")
        if {name for name in e2e_env if name.startswith("NPM_CONFIG_")} != set(
            expected_npm_configs
        ):
            pytest.fail(
                "only the wrapper's empty npm config paths may reach Playwright"
            )
        if generated_password in repr([command for command, _, _ in runs]):
            pytest.fail("the generated password must never appear in subprocess argv")
        captured = capsys.readouterr()
        if generated_password in captured.out or generated_password in captured.err:
            pytest.fail("the E2E command must not print the generated password")
        if os.environ.get("TEST_PASSWORD") != ambient_password:
            pytest.fail("the E2E command must not mutate the caller's environment")

        playwright_failures_remaining = 1
        if live_stand.main(e2e_arguments) != 2:
            pytest.fail("a Playwright failure must use the stand error exit code")
        if len(runs) != 9 or len(dependency_runs) != 3 or len(playwright_runs) != 3:
            pytest.fail("the failure-path E2E run must reach Playwright after seeding")
        if len(e2e_daemon_calls) != 15 or len(e2e_resource_calls) != 12:
            pytest.fail(
                "the failure path must retain all deadline and context arguments"
            )
        if len(caddy_pin_calls) != 3 or len(probe_log_calls) != 2:
            pytest.fail("failed Playwright must not produce a Caddy log proof")
        failure_environment = playwright_runs[-1][1]
        if in_place_mode:
            if failure_environment.get("LIVE_STAND_STATE_ROOT") != str(
                worktree.resolve(strict=True)
            ):
                pytest.fail("the failing in-place child must receive its owned root")
        elif (
            "LIVE_STAND_STATE_ROOT" in failure_environment
            or caller_state_root in failure_environment.values()
        ):
            pytest.fail("the failing legacy child must not receive a caller root")
        if any(
            "LIVE_STAND_STATE_ROOT" in environment
            for environment in playwright_environment_objects
        ):
            pytest.fail("the in-place state root must be removed after failure")
        if any(marker.exists() for marker in owner_marker_paths):
            pytest.fail("the failing Playwright output marker must be cleaned up")
        if Path(failure_environment["LIVE_E2E_OUTPUT_DIR"]).exists():
            pytest.fail("the failing Playwright output directory must be cleaned up")
        failure_output = capsys.readouterr()
        if "live_stand: synthetic live Playwright failure" not in failure_output.err:
            pytest.fail("the failure path must report the expected stand error")
        if (
            generated_password in failure_output.out
            or generated_password in failure_output.err
        ):
            pytest.fail("the failure path must not print the generated password")
    finally:
        for _command, _cwd, environment in runs:
            environment.pop("TEST_PASSWORD", None)
        for (
            _cwd,
            environment,
            _password,
            _output_dir_existed,
            _npm_configs_empty,
        ) in playwright_runs:
            environment.pop("TEST_PASSWORD", None)
            environment.pop("LIVE_E2E_OUTPUT_DIR", None)
            environment.pop("PLAYWRIGHT_TEST_OUTPUT_DIR", None)


def test_live_e2e_runtime_environment_only_copies_explicit_platform_allowlist() -> None:
    source = {
        name: f"allowed-runtime-{name.lower()}"
        for name in (
            "PATH",
            "PLAYWRIGHT_BROWSERS_PATH",
            *live_stand.LIVE_E2E_WINDOWS_ENVIRONMENT,
            *live_stand.LIVE_E2E_UNIX_ENVIRONMENT,
            *live_stand.LIVE_E2E_CI_ENVIRONMENT,
        )
    }
    private_names = (
        "CHROMATIC_PROJECT_TOKEN",
        "GH_TOKEN",
        "ACTIONS_RUNTIME_TOKEN",
        "GITHUB_TOKEN",
        "NPM_TOKEN",
        "NODE_AUTH_TOKEN",
        "UNRELATED_API_KEY",
        "DATABASE_URL",
        "NODE_OPTIONS",
        "NPM_CONFIG_REGISTRY",
        "NPM_CONFIG_USERCONFIG",
        "NPM_CONFIG_GLOBALCONFIG",
        "LIVE_VAPID_PRIVATE_KEY",
        "COMPOSE_PROJECT_NAME",
        "TEST_PASSWORD",
        "LIVE_PRIMARY_REPOSITORY_ROOT",
        "LIVE_E2E_OUTPUT_DIR",
        "PLAYWRIGHT_TEST_OUTPUT_DIR",
    )
    private_values = {
        name: f"private-sentinel-{index}" for index, name in enumerate(private_names)
    }
    source.update(private_values)

    for platform, runtime_names in (
        (
            "nt",
            (
                "PATH",
                "PLAYWRIGHT_BROWSERS_PATH",
                *live_stand.LIVE_E2E_WINDOWS_ENVIRONMENT,
                *live_stand.LIVE_E2E_CI_ENVIRONMENT,
            ),
        ),
        (
            "posix",
            (
                "PATH",
                "PLAYWRIGHT_BROWSERS_PATH",
                *live_stand.LIVE_E2E_UNIX_ENVIRONMENT,
                *live_stand.LIVE_E2E_CI_ENVIRONMENT,
            ),
        ),
    ):
        expected = {name: source[name] for name in runtime_names}
        child_environment = live_stand._live_e2e_runtime_environment(
            source, platform=platform
        )
        if child_environment != expected:
            pytest.fail(
                "the child environment must match the explicit platform allowlist"
            )
        if any(
            value in child_environment.values() for value in private_values.values()
        ):
            pytest.fail(
                "caller secrets and unrelated environment values must be excluded"
            )


def test_playwright_browser_cache_uses_existing_local_override_and_preserves_default(
    tmp_path: Path,
) -> None:
    profile = tmp_path / "profile"
    selected_cache = tmp_path / "private-browser-cache"
    selected_cache.mkdir()

    assert live_stand._playwright_browser_cache_path(
        {"HOME": str(profile), "LOCALAPPDATA": str(profile)}
    ) == profile / ("ms-playwright" if os.name == "nt" else ".cache/ms-playwright")
    assert live_stand._playwright_browser_cache_path(
        {
            "HOME": str(profile),
            "LOCALAPPDATA": str(profile),
            "PLAYWRIGHT_BROWSERS_PATH": str(selected_cache),
        }
    ) == selected_cache.resolve(strict=True)


def test_live_e2e_environment_uses_override_and_rejects_blank_before_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(live_stand.tempfile, "gettempdir", lambda: str(tmp_path))
    cache = tmp_path / "selected-cache"
    cache.mkdir()
    config_root = tmp_path / "ue-live-playwright-valid"
    output_directory = config_root / "playwright-output"
    output_directory.mkdir(parents=True)

    environment = live_stand._live_e2e_environment(
        output_directory=str(output_directory),
        npm_config_directory=str(config_root),
        source_environment={
            "PATH": "runtime-path",
            "PLAYWRIGHT_BROWSERS_PATH": str(cache),
        },
    )
    assert environment["PLAYWRIGHT_BROWSERS_PATH"] == str(cache.resolve())
    assert (config_root / live_stand.LIVE_E2E_OUTPUT_OWNER_MARKER).is_file()

    invalid_config = tmp_path / "ue-live-playwright-invalid"
    invalid_output = invalid_config / "playwright-output"
    invalid_output.mkdir(parents=True)
    with pytest.raises(live_stand.StandError, match="PLAYWRIGHT_BROWSERS_PATH"):
        live_stand._live_e2e_environment(
            output_directory=str(invalid_output),
            npm_config_directory=str(invalid_config),
            source_environment={
                "PATH": "runtime-path",
                "PLAYWRIGHT_BROWSERS_PATH": "",
            },
        )
    assert not (invalid_config / live_stand.LIVE_E2E_OUTPUT_OWNER_MARKER).exists()
    assert not (invalid_config / "npm-userconfig").exists()


@pytest.mark.parametrize(
    "override",
    [
        "",
        " ",
        "0",
        ".",
        "relative-cache",
        "//server/share/cache",
        "\\\\server\\share\\cache",
    ],
)
def test_playwright_browser_cache_rejects_invalid_override(
    tmp_path: Path, override: str
) -> None:
    with pytest.raises(live_stand.StandError, match="PLAYWRIGHT_BROWSERS_PATH"):
        live_stand._playwright_browser_cache_path(
            {"PLAYWRIGHT_BROWSERS_PATH": override}
        )


def test_playwright_browser_cache_rejects_nonexistent_override(tmp_path: Path) -> None:
    missing_cache = tmp_path / "missing-cache"
    with pytest.raises(live_stand.StandError, match="PLAYWRIGHT_BROWSERS_PATH"):
        live_stand._playwright_browser_cache_path(
            {"PLAYWRIGHT_BROWSERS_PATH": str(missing_cache)}
        )


def test_playwright_browser_cache_rejects_reparse_override(tmp_path: Path) -> None:
    target = tmp_path / "target-cache"
    target.mkdir()
    link = tmp_path / "linked-cache"
    if os.name == "nt":
        _make_windows_junction(link, target)
    else:
        link.symlink_to(target, target_is_directory=True)

    with pytest.raises(live_stand.StandError, match="reparse point"):
        live_stand._playwright_browser_cache_path(
            {"PLAYWRIGHT_BROWSERS_PATH": str(link)}
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows mapped-drive classification")
def test_playwright_browser_cache_rejects_remote_drive_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache = tmp_path / "remote-cache"
    cache.mkdir()
    monkeypatch.setattr(
        live_stand.ctypes.windll.kernel32,
        "GetDriveTypeW",
        lambda _root: 4,
    )
    with pytest.raises(live_stand.StandError, match="local directory"):
        live_stand._playwright_browser_cache_path(
            {"PLAYWRIGHT_BROWSERS_PATH": str(cache)}
        )


def test_live_e2e_npm_ci_uses_static_platform_commands() -> None:
    assert live_stand._live_e2e_npm_ci_command(platform="nt") == (
        "cmd.exe",
        "/d",
        "/s",
        "/c",
        "npm ci",
    )
    assert live_stand._live_e2e_npm_ci_command(platform="posix") == ("npm", "ci")


def test_live_e2e_dependency_bootstrap_installs_only_stale_locked_dependencies_and_checks_cached_chromium(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert live_stand.LIVE_E2E_REQUIRED_PACKAGES == (
        "@playwright/test",
        "playwright",
        "playwright-core",
    )
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    package_json_path = frontend / "package.json"
    package_json = {
        "name": "university-ecosystem-frontend",
        "version": "1.0.0",
        "devDependencies": {
            "@playwright/test": "1.63.0",
            "playwright": "1.63.0",
        },
    }
    package_json_path.write_text(json.dumps(package_json), encoding="utf-8")
    lock_path = frontend / "package-lock.json"
    lock_data = {
        "lockfileVersion": 3,
        "packages": {
            "": {
                "devDependencies": {
                    "@playwright/test": "1.63.0",
                    "playwright": "1.63.0",
                }
            },
            "node_modules/@playwright/test": {"version": "1.63.0"},
            "node_modules/playwright": {"version": "1.63.0"},
            "node_modules/playwright-core": {"version": "1.63.0"},
        },
    }
    lock_path.write_text(json.dumps(lock_data), encoding="utf-8")
    output_path = tmp_path / "playwright-output"
    output_path.mkdir()
    browser_cache = tmp_path / "selected-browser-cache"
    browser_cache.mkdir()
    config_root = tmp_path / "npm-config"
    config_root.mkdir()
    user_config = config_root / "npm-userconfig"
    global_config = config_root / "npm-globalconfig"
    user_config.write_bytes(b"")
    global_config.write_bytes(b"")
    runtime_source = {
        "PATH": "runtime-path-marker",
        "PLAYWRIGHT_BROWSERS_PATH": str(browser_cache),
        "HOME": str(tmp_path / "profile"),
        "LOCALAPPDATA": str(tmp_path / "profile"),
        "SYSTEMROOT": "runtime-systemroot-marker",
        "TEMP": str(tmp_path),
        "TMP": str(tmp_path),
        "USERPROFILE": str(tmp_path / "profile"),
        "TMPDIR": str(tmp_path),
        "CI": "true",
        "GITHUB_ACTIONS": "true",
        "TEST_PASSWORD": make_test_password(
            length=23, required_classes=frozenset({"lower", "symbol"})
        ),
        "LIVE_BASE_URL": "http://sensitive-endpoint.invalid",
        "LIVE_MAILPIT_URL": "http://sensitive-mail.invalid",
        "LIVE_E2E_OUTPUT_DIR": str(output_path),
        "PLAYWRIGHT_TEST_OUTPUT_DIR": str(output_path),
        "LIVE_PRIMARY_REPOSITORY_ROOT": "caller-controlled-root-sentinel",
        "CHROMATIC_PROJECT_TOKEN": "chromatic-secret-sentinel",
        "GH_TOKEN": "github-secret-sentinel",
        "ACTIONS_RUNTIME_TOKEN": "actions-secret-sentinel",
        "UNRELATED_API_KEY": make_test_password(
            length=16, required_classes=frozenset({"lower", "symbol"})
        ),
        "NODE_OPTIONS": "--require=untrusted.js",
        "NPM_CONFIG_REGISTRY": "https://private-registry.invalid",
        "NPM_CONFIG_USERCONFIG": "caller-userconfig-sentinel",
        "NPM_CONFIG_GLOBALCONFIG": "caller-globalconfig-sentinel",
    }
    runtime_environment = live_stand._live_e2e_runtime_environment(runtime_source)
    browser_cache = live_stand._playwright_browser_cache_path(runtime_environment)
    chromium_executable = browser_cache / "chromium-1243" / "chrome" / "chrome"
    chromium_executable.parent.mkdir(parents=True)
    chromium_executable.write_bytes(b"cached chromium marker")
    environment = {
        **runtime_environment,
        "LIVE_E2E_OUTPUT_DIR": str(output_path),
        "PLAYWRIGHT_TEST_OUTPUT_DIR": str(output_path),
        "LIVE_PRIMARY_REPOSITORY_ROOT": runtime_source["LIVE_PRIMARY_REPOSITORY_ROOT"],
        "NPM_CONFIG_USERCONFIG": str(user_config),
        "NPM_CONFIG_GLOBALCONFIG": str(global_config),
        "TEST_PASSWORD": runtime_source["TEST_PASSWORD"],
        "LIVE_BASE_URL": runtime_source["LIVE_BASE_URL"],
        "LIVE_MAILPIT_URL": runtime_source["LIVE_MAILPIT_URL"],
        "CHROMATIC_PROJECT_TOKEN": runtime_source["CHROMATIC_PROJECT_TOKEN"],
        "GH_TOKEN": runtime_source["GH_TOKEN"],
        "ACTIONS_RUNTIME_TOKEN": runtime_source["ACTIONS_RUNTIME_TOKEN"],
        "UNRELATED_API_KEY": runtime_source["UNRELATED_API_KEY"],
        "NODE_OPTIONS": runtime_source["NODE_OPTIONS"],
        "NPM_CONFIG_REGISTRY": runtime_source["NPM_CONFIG_REGISTRY"],
    }
    calls: list[tuple[tuple[str, ...], Path, dict[str, str]]] = []
    install_output = "bootstrap-output-secret-sentinel"

    def fake_run(
        command: tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str],
        check: bool,
        capture_output: bool,
        text: bool,
        encoding: str,
        errors: str,
    ) -> subprocess.CompletedProcess[str]:
        assert check is False and capture_output and text and encoding == "utf-8"
        assert errors == "replace"
        calls.append((command, cwd, dict(env)))
        assert user_config.is_file() and user_config.read_bytes() == b""
        assert global_config.is_file() and global_config.read_bytes() == b""
        if command in {
            live_stand.LIVE_E2E_NPM_CI_COMMAND,
            live_stand.LIVE_E2E_WINDOWS_NPM_CI_COMMAND,
        }:
            installed_packages = frontend / "node_modules"
            for package_name in live_stand.LIVE_E2E_REQUIRED_PACKAGES:
                package = installed_packages / package_name
                package.mkdir(parents=True, exist_ok=True)
                package_version = lock_data["packages"][f"node_modules/{package_name}"][
                    "version"
                ]
                (package / "package.json").write_text(
                    json.dumps({"version": package_version}), encoding="utf-8"
                )
            return subprocess.CompletedProcess(
                command, 0, install_output, "installer-stderr-secret-sentinel"
            )
        if command == live_stand.LIVE_E2E_CHROMIUM_PROBE_COMMAND:
            return subprocess.CompletedProcess(
                command, 0, str(chromium_executable), "probe-stderr-sentinel"
            )
        pytest.fail("dependency bootstrap used an unexpected command")

    monkeypatch.setattr(live_stand.subprocess, "run", fake_run)

    live_stand._ensure_live_e2e_dependencies(frontend, environment)
    live_stand._ensure_live_e2e_dependencies(frontend, environment)

    package_json["scripts"] = {"test:e2e:live": "playwright test"}
    package_json_path.write_text(json.dumps(package_json), encoding="utf-8")
    live_stand._ensure_live_e2e_dependencies(frontend, environment)

    lock_data["packages"]["node_modules/@playwright/test"]["version"] = "1.64.0"
    lock_data["packages"]["node_modules/playwright"]["version"] = "1.64.0"
    lock_data["packages"]["node_modules/playwright-core"]["version"] = "1.64.0"
    lock_data["packages"][""]["devDependencies"]["@playwright/test"] = "1.64.0"
    lock_data["packages"][""]["devDependencies"]["playwright"] = "1.64.0"
    lock_path.write_text(json.dumps(lock_data), encoding="utf-8")
    package_json["devDependencies"]["@playwright/test"] = "1.64.0"
    package_json["devDependencies"]["playwright"] = "1.64.0"
    package_json_path.write_text(json.dumps(package_json), encoding="utf-8")
    live_stand._ensure_live_e2e_dependencies(frontend, environment)

    npm_calls = [
        call
        for call in calls
        if call[0]
        in {
            live_stand.LIVE_E2E_NPM_CI_COMMAND,
            live_stand.LIVE_E2E_WINDOWS_NPM_CI_COMMAND,
        }
    ]
    probe_calls = [
        call for call in calls if call[0] == live_stand.LIVE_E2E_CHROMIUM_PROBE_COMMAND
    ]
    assert len(npm_calls) == 3
    assert len(probe_calls) == 4
    for command, cwd, child_environment in calls:
        assert cwd == frontend
        assert command not in (live_stand.LIVE_E2E_COMMAND,)
        assert child_environment["PATH"] == runtime_source["PATH"]
        assert child_environment["PLAYWRIGHT_BROWSERS_PATH"] == str(browser_cache)
        assert child_environment["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"] == "1"
        assert child_environment["NPM_CONFIG_USERCONFIG"] == str(user_config)
        assert child_environment["NPM_CONFIG_GLOBALCONFIG"] == str(global_config)
        assert "TEST_PASSWORD" not in child_environment
        assert "LIVE_BASE_URL" not in child_environment
        assert "LIVE_MAILPIT_URL" not in child_environment
        assert "LIVE_E2E_OUTPUT_DIR" not in child_environment
        assert "PLAYWRIGHT_TEST_OUTPUT_DIR" not in child_environment
        for secret_name in (
            "CHROMATIC_PROJECT_TOKEN",
            "GH_TOKEN",
            "ACTIONS_RUNTIME_TOKEN",
            "UNRELATED_API_KEY",
            "LIVE_PRIMARY_REPOSITORY_ROOT",
            "NODE_OPTIONS",
            "NPM_CONFIG_REGISTRY",
        ):
            assert secret_name not in child_environment
            assert runtime_source[secret_name] not in child_environment.values()
    expected_runtime = live_stand._live_e2e_runtime_environment(runtime_source)
    for _command, _cwd, child_environment in calls:
        assert {
            key: child_environment[key] for key in expected_runtime
        } == expected_runtime
        assert set(child_environment) == {
            *expected_runtime,
            "NPM_CONFIG_USERCONFIG",
            "NPM_CONFIG_GLOBALCONFIG",
            "PLAYWRIGHT_BROWSERS_PATH",
            "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD",
        }
    stored_fingerprint = (
        (frontend / "node_modules" / live_stand.LIVE_E2E_MANIFEST_FINGERPRINT)
        .read_text(encoding="utf-8")
        .strip()
    )
    assert stored_fingerprint != hashlib.sha256(lock_path.read_bytes()).hexdigest()
    captured = capsys.readouterr()
    for private_value in (
        install_output,
        "installer-stderr-secret-sentinel",
        "probe-stderr-sentinel",
        str(chromium_executable),
        runtime_source["TEST_PASSWORD"],
    ):
        assert private_value not in captured.out
        assert private_value not in captured.err


def test_live_playwright_never_emits_child_credentials_or_call_logs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    password = live_stand.secrets.token_urlsafe(32) + "!Aa0"
    reset_token = live_stand.secrets.token_urlsafe(32)
    registration_password = make_test_password(length=22)
    student_password = make_test_password(
        length=24, required_classes=frozenset({"lower", "symbol"})
    )
    teacher_password = make_test_password(
        length=24,
        required_classes=frozenset({"lower", "symbol"}),
        excluding=(student_password,),
    )
    stdout = (
        "1 failed (3.2s)\n"
        "2 passed (9.1s)\n"
        "Call log:\n"
        f'  - locator.fill("{registration_password}")\n'
        f'  - locator.fill("{student_password}")\n'
        f"navigation failed: http://localhost/reset-password?token={reset_token}\n"
    )
    stderr = (
        f'  - locator.fill("{teacher_password}")\n'
        f'  - locator.fill("{password}")\n'
        f"failed reset URL https://localhost/reset-password?token={reset_token}\n"
    )
    captured_calls: list[dict[str, object]] = []

    def fake_subprocess_run(
        command: Sequence[str], **kwargs: object
    ) -> subprocess.CompletedProcess:
        captured_calls.append({"command": command, **kwargs})
        return subprocess.CompletedProcess(
            command, 1, stdout=stdout.encode(), stderr=stderr.encode()
        )

    monkeypatch.setattr(live_stand.subprocess, "run", fake_subprocess_run)

    with pytest.raises(live_stand.StandError, match="exit code 1"):
        live_stand._run_live_playwright(
            cwd=tmp_path,
            environment={"TEST_PASSWORD": password},
        )

    printed = capsys.readouterr()
    for sensitive_value in (
        password,
        reset_token,
        registration_password,
        student_password,
        teacher_password,
    ):
        if sensitive_value in printed.out or sensitive_value in printed.err:
            pytest.fail(
                "live Playwright output must not expose submitted credentials or tokens"
            )
    if (
        "Call log:" in printed.out + printed.err
        or "locator.fill" in printed.out + printed.err
    ):
        pytest.fail("raw browser call logs must not be forwarded")
    if "live E2E counts passed=2 failed=1" not in printed.out:
        pytest.fail("the wrapper may expose aggregate counts without test diagnostics")
    if "live E2E outcome=failed exit_code=1" not in printed.out:
        pytest.fail("the wrapper must retain a safe exit summary")
    if len(captured_calls) != 1:
        pytest.fail("the live runner should launch Playwright once")

    call = captured_calls[0]
    command = call["command"]
    if not isinstance(command, (list, tuple)) or any(
        password in part for part in command
    ):
        pytest.fail("the admin password must not appear in Playwright argv")
    if tuple(command) != live_stand._live_e2e_command():
        pytest.fail("the runner must use the platform-specific fixed npm launcher")
    if call.get("capture_output") is not True or call.get("text") is not False:
        pytest.fail("Playwright output must be captured before diagnostics are emitted")
    assert "encoding" not in call and "errors" not in call


@pytest.mark.parametrize(
    ("label", "key"),
    [
        ("passed", "passed"),
        ("failed", "failed"),
        ("skipped", "skipped"),
        ("flaky", "flaky"),
        ("interrupted", "interrupted"),
        ("did not run", "did_not_run"),
    ],
)
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_live_playwright_counts_accept_all_bounded_summary_categories(
    label: str, key: str, newline: str
) -> None:
    assert live_stand._live_playwright_counts(f"  1 {label}{newline}") == {key: 1}
    assert live_stand._live_playwright_counts(f"  99999 {label}{newline}") == {
        key: 99999
    }


@pytest.mark.parametrize("duration", ["12ms", "3.2s", "1.5m", "2.1h", "1.2d"])
def test_live_playwright_counts_accept_numeric_durations(duration: str) -> None:
    assert live_stand._live_playwright_counts(f"  2 passed ({duration})\n") == {
        "passed": 2
    }


_LIVE_SKIP_SOURCE_RULES = (
    (
        "tests/e2e-live/auth-roles.live.spec.ts",
        "testInfo.project.name !== project",
        ("desktop", "mobile"),
        1,
    ),
    (
        "tests/e2e-live/navbar-layout-stability.live.spec.ts",
        'testInfo.project.name !== "desktop"',
        ("mobile",),
        1,
    ),
    (
        "tests/e2e-live/schedule-grid-keyboard.live.spec.ts",
        'testInfo.project.name !== "desktop"',
        ("mobile",),
        1,
    ),
    (
        "tests/e2e-live/schedule-200-equivalent-reflow.live.spec.ts",
        'testInfo.project.name !== "desktop"',
        ("mobile",),
        1,
    ),
    (
        "tests/e2e-live/map-gesture-isolation.live.spec.ts",
        "page.viewportSize()?.width ?? 0) < 640",
        ("mobile",),
        2,
    ),
    (
        "tests/e2e-live/map-gesture-isolation.live.spec.ts",
        "page.viewportSize()?.width ?? 0) >= 640",
        ("desktop",),
        1,
    ),
)


def _source_derived_live_skip_identities() -> list[tuple[str, str, int]]:
    skip_call = "test." + "skip("
    identities: list[tuple[str, str, int]] = []
    for source, marker, projects, expected_matches in _LIVE_SKIP_SOURCE_RULES:
        lines = (ROOT / "frontend" / source).read_text(encoding="utf-8").splitlines()
        matches = [index for index, line in enumerate(lines) if marker in line]
        assert len(matches) == expected_matches
        if source.endswith("auth-roles.live.spec.ts"):
            assert all(
                lines.count(f'    project: "{project}",') == 1 for project in projects
            )
        for match_index in matches:
            if source.endswith("auth-roles.live.spec.ts"):
                assert (
                    lines[match_index].strip() == "testInfo.project.name !== project,"
                )
                assert lines[match_index - 1].strip() == skip_call
            else:
                expression = (
                    f"{skip_call}({marker},"
                    if marker.startswith("page.viewportSize")
                    else f"{skip_call}{marker},"
                )
                assert lines[match_index].strip().startswith(expression)
            declarations = [
                index
                for index in range(match_index)
                if lines[index].lstrip().startswith("test(")
            ]
            assert declarations
            for project in projects:
                identities.append((project, source, declarations[-1] + 1))
    return sorted(identities)


def _live_skip_reporter_rows(
    identities: Sequence[tuple[str, str, int]], *, title: str
) -> str:
    rows: list[str] = []
    for index, (project, source, line_number) in enumerate(identities, start=1):
        declaration = (
            (ROOT / "frontend" / source)
            .read_text(encoding="utf-8")
            .splitlines()[line_number - 1]
        )
        column = len(declaration) - len(declaration.lstrip()) + 1
        rows.append(
            f"  -  {index:>3} [{project}] \u203a "
            f"{source}:{line_number}:{column} \u203a {title}\n"
        )
    return "".join(rows)


def test_live_playwright_skip_map_matches_current_project_guard_declarations() -> None:
    assert _source_derived_live_skip_identities() == sorted(
        live_stand._PLAYWRIGHT_EXPECTED_SKIP_IDENTITIES
    )


def test_live_playwright_verifies_exact_full_suite_skip_identities(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    identities = sorted(live_stand._PLAYWRIGHT_EXPECTED_SKIP_IDENTITIES)
    private_title = "private skip title token=do-not-print"
    stdout = (
        _live_skip_reporter_rows(identities, title=private_title)
        + "212 passed (3m)\n8 skipped\n"
    ).encode("utf-8")
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(), 0, stdout=stdout, stderr=b""
    )
    monkeypatch.setattr(
        live_stand.subprocess,
        "run",
        lambda *_args, **_kwargs: completed,
    )

    live_stand._run_live_playwright(cwd=ROOT / "frontend", environment={})

    printed = capsys.readouterr()
    expected_output = [
        "+ " + " ".join(live_stand._live_e2e_command()),
        "live E2E counts passed=212 skipped=8",
        *(
            f"live E2E skipped project={project} source={source} line={line_number}"
            for project, source, line_number in identities
        ),
        "live E2E skip accounting=verified count=8",
        "live E2E outcome=passed exit_code=0",
    ]
    assert printed.out.splitlines() == expected_output
    assert printed.err == ""
    assert private_title not in printed.out + printed.err
    assert completed.stdout == completed.stderr == b""


@pytest.mark.parametrize("extra_summary", ["flaky", "interrupted"])
def test_live_playwright_canonical_full_rejects_flaky_or_interrupted_counts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    extra_summary: str,
) -> None:
    identities = sorted(live_stand._PLAYWRIGHT_EXPECTED_SKIP_IDENTITIES)
    newline = chr(10)
    stdout = (
        _live_skip_reporter_rows(identities, title="private title")
        + f"212 passed{newline}8 skipped{newline}1 {extra_summary}{newline}"
    ).encode("utf-8")
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(), 0, stdout=stdout, stderr=b""
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )

    with pytest.raises(live_stand.StandError, match="skip identity accounting"):
        live_stand._run_live_playwright(cwd=ROOT / "frontend", environment={})

    printed = capsys.readouterr()
    assert "skip accounting=verified" not in printed.out
    assert "live E2E outcome=failed exit_code=0" in printed.out
    assert "private title" not in printed.out


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_live_playwright_canonical_full_rejects_missing_or_duplicate_skip_rows(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mutation: str,
) -> None:
    identities = sorted(live_stand._PLAYWRIGHT_EXPECTED_SKIP_IDENTITIES)
    observed = (
        identities[:-1] if mutation == "missing" else [*identities, identities[0]]
    )
    newline = chr(10)
    stdout = (
        _live_skip_reporter_rows(observed, title="private title")
        + f"212 passed{newline}8 skipped{newline}"
    ).encode("utf-8")
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(), 0, stdout=stdout, stderr=b""
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )

    with pytest.raises(live_stand.StandError, match="skip identity accounting"):
        live_stand._run_live_playwright(cwd=ROOT / "frontend", environment={})

    printed = capsys.readouterr()
    expected_count = 7 if mutation == "missing" else 9
    assert f"skip accounting=failed observed={expected_count} " in printed.out
    assert "private title" not in printed.out


def test_live_playwright_rejects_same_count_with_unexpected_skip_identity(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    identities = sorted(live_stand._PLAYWRIGHT_EXPECTED_SKIP_IDENTITIES)
    substituted = list(identities)
    substituted[-1] = substituted[0]
    private_title = "private skip title token=do-not-print"
    stdout = (
        _live_skip_reporter_rows(substituted, title=private_title)
        + "212 passed (3m)\n8 skipped\n"
    ).encode("utf-8")
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(), 0, stdout=stdout, stderr=b""
    )
    monkeypatch.setattr(
        live_stand.subprocess,
        "run",
        lambda *_args, **_kwargs: completed,
    )

    with pytest.raises(live_stand.StandError, match="skip identity accounting"):
        live_stand._run_live_playwright(cwd=ROOT / "frontend", environment={})

    printed = capsys.readouterr()
    assert "live E2E counts passed=212 skipped=8" in printed.out
    assert (
        "live E2E skip accounting=failed observed=8 rejected=0 overflow=false"
        in printed.out
    )
    assert "live E2E outcome=failed exit_code=0" in printed.out
    assert "verified count=8" not in printed.out
    assert printed.err == ""
    assert private_title not in printed.out + printed.err
    assert completed.stdout == completed.stderr == b""


@pytest.mark.parametrize(
    ("passed", "accepted"),
    [
        pytest.param(212, True, id="current-220-instance-inventory"),
        pytest.param(210, False, id="obsolete-218-instance-inventory"),
        pytest.param(190, False, id="obsolete-198-instance-inventory"),
        pytest.param(209, False, id="three-passes-missing"),
        pytest.param(211, False, id="one-pass-missing"),
        pytest.param(213, False, id="one-pass-extra"),
    ],
)
def test_live_playwright_full_count_matches_collected_inventory(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    passed: int,
    accepted: bool,
) -> None:
    identities = _source_derived_live_skip_identities()
    assert len(identities) == 8
    private_title = "private inventory title not for logs"
    stdout = (
        _live_skip_reporter_rows(identities, title=private_title)
        + f"{passed} passed (3m)\n8 skipped\n"
    ).encode("utf-8")
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(), 0, stdout=stdout, stderr=b""
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )

    if accepted:
        live_stand._run_live_playwright(cwd=ROOT / "frontend", environment={})
    else:
        with pytest.raises(live_stand.StandError, match="skip identity accounting"):
            live_stand._run_live_playwright(cwd=ROOT / "frontend", environment={})

    printed = capsys.readouterr()
    assert f"live E2E counts passed={passed} skipped=8" in printed.out
    if accepted:
        assert "live E2E skip accounting=verified count=8" in printed.out
        assert "live E2E outcome=passed exit_code=0" in printed.out
    else:
        assert "skip accounting=verified" not in printed.out
        assert "live E2E outcome=failed exit_code=0" in printed.out
    assert private_title not in printed.out + printed.err
    assert printed.err == ""
    assert completed.stdout == completed.stderr == b""


@pytest.mark.parametrize(
    ("index", "accepted"),
    [
        pytest.param(198, True, id="previous-boundary"),
        pytest.param(199, True, id="above-previous-boundary"),
        pytest.param(216, True, id="current-boundary"),
        pytest.param(217, False, id="above-current-boundary"),
    ],
)
def test_live_playwright_skip_index_matches_collected_inventory(
    index: int,
    accepted: bool,
) -> None:
    identity = _source_derived_live_skip_identities()[0]
    row = _live_skip_reporter_rows([identity], title="private title")
    assert row.startswith("  -    1 ")
    row = row.replace("  -    1 ", f"  -  {index:>3} ", 1)

    identities, rejected, overflow = live_stand._live_playwright_skipped_identities(
        row, cwd=ROOT / "frontend"
    )

    assert identities == ([identity] if accepted else [])
    assert rejected == (0 if accepted else 1)
    assert overflow is False


@pytest.mark.parametrize(
    ("project", "route", "newline"),
    [("desktop", "profile", "\n"), ("mobile", "other", "\r\n")],
)
def test_live_playwright_profile_save_diagnostics_accept_closed_records(
    project: str, route: str, newline: str
) -> None:
    record = (
        f"UE_LIVE_PROFILE_SAVE_V1 project={project} status=422 detail=array detail_count=1 "
        f"detail_msg=true alert_count=0 save_disabled=false route={route} "
        f"page_error_count=0 page_error=none{newline}"
    )
    assert live_stand._live_playwright_profile_save_diagnostics(record) == [
        (project, 422, "array", 1, True, 0, False, route, 0, "none")
    ]


@pytest.mark.parametrize(
    "replacement",
    [
        ("project=desktop", "project=private-project"),
        ("status=422", "status=600"),
        ("detail=array", "detail=private-body"),
        ("detail_count=1", "detail_count=1000"),
        ("detail_msg=true", "detail_msg=true private-message"),
        ("alert_count=0", "alert_count=0 private-input"),
        ("save_disabled=false", "save_disabled=unknown-url"),
        ("route=profile", "route=/profile?token=secret"),
        ("page_error=none", "page_error=TypeError:secret"),
        ("page_error_count=0", "page_error_count=-1"),
        ("\n", ""),
        ("\n", "\r\r\n"),
        ("\n", "\x00\n"),
        ("\n", "\x1b[0m\n"),
        ("\n", "\u202e\n"),
        ("UE_LIVE", "private\rUE_LIVE"),
    ],
)
def test_live_playwright_profile_save_diagnostics_reject_malformed_records(
    replacement: tuple[str, str],
) -> None:
    record = (
        "UE_LIVE_PROFILE_SAVE_V1 project=desktop status=422 detail=array detail_count=1 "
        "detail_msg=true alert_count=0 save_disabled=false route=profile "
        "page_error_count=0 page_error=none\n"
    )
    assert (
        live_stand._live_playwright_profile_save_diagnostics(
            record.replace(*replacement)
        )
        == []
    )


def test_live_playwright_profile_save_diagnostics_deduplicate_and_bound_records() -> (
    None
):
    output = "".join(
        f"UE_LIVE_PROFILE_SAVE_V1 project=desktop status={status} detail=array detail_count=0 "
        "detail_msg=false alert_count=0 save_disabled=false route=profile "
        "page_error_count=0 page_error=none\n" * 5
        for status in range(400, 410)
    )
    assert live_stand._live_playwright_profile_save_diagnostics(output) == [
        ("desktop", status, "array", 0, False, 0, False, "profile", 0, "none")
        for status in range(400, 404)
    ]


def test_live_playwright_emits_only_validated_profile_save_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    sentinel = (
        "UE_LIVE_PROFILE_SAVE_V1 project=desktop status=422 detail=array detail_count=1 "
        "detail_msg=true alert_count=0 save_disabled=false route=profile "
        "page_error_count=1 page_error=type-error\n"
    )
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"),
        1,
        stdout=(
            b"private-response-body private-validation-message https://private.invalid/?token=x\n"
            + sentinel.encode()
            + b"UE_LIVE_PROFILE_SAVE_V1 project=mobile status=422 detail=array detail_count=1 "
            b"detail_msg=true alert_count=0 save_disabled=false route=/profile?token=x "
            b"page_error_count=0 page_error=none\n"
        ),
        stderr=b"private-stack private-credential\n",
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    with pytest.raises(live_stand.StandError):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E profile save project=desktop status=422 detail=array detail_count=1 "
        "detail_msg=true alert_count=0 save_disabled=false route=profile "
        "page_error_count=1 page_error=type-error",
        "live E2E outcome=failed exit_code=1",
    ]
    assert printed.err == ""
    assert not any(
        marker in printed.out + printed.err
        for marker in (
            "private-response-body",
            "private-validation-message",
            "private.invalid",
            "private-stack",
            "private-credential",
            "token=x",
        )
    )


@pytest.mark.parametrize(
    "line",
    [
        "  1 unknown\n",
        "  1 did_not_run\n",
        "  -1 flaky\n",
        "  1.2 flaky\n",
        "  01 flaky\n",
        "  100000 passed\n",
        "  " + "9" * 5000 + " passed\n",
        "  ١ passed\n",
        "  1 PASSED\n",
        "  1 did  not run\n",
        "  1 passed secret\n",
        "secret 1 passed\n",
        "  1 passed (private-token)\n",
        "  1 passed (https://private.invalid/reset?token=private)\n",
        "  1 passed (" + "9" * 5000 + "s)\n",
        "  1 passed (2.1s) private\n",
        "  1 passed\x1b[31m\n",
        "private\r  1 passed\n",
        "private\v  1 passed\n",
        "private\x85  1 passed\n",
        "  1 passed\x00\n",
        "  1 passed\u202e\n",
    ],
)
def test_live_playwright_counts_reject_malformed_summary_records(line: str) -> None:
    assert live_stand._live_playwright_counts(line) == {}


@pytest.mark.parametrize("project", ["desktop", "mobile"])
@pytest.mark.parametrize("route", ["dashboard", "settings"])
@pytest.mark.parametrize("ratio_milli", [0, 1, 4_500, 20_999, 21_000])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_live_playwright_a11y_contrast_accepts_bounded_closed_records(
    project: str, route: str, ratio_milli: int, newline: str
) -> None:
    row = (
        f"UE_LIVE_A11Y_CONTRAST_V1 project={project} route={route} "
        f"fg=#A1b2C3 bg=#000000 ratio_milli={ratio_milli}{newline}"
    )
    assert live_stand._live_playwright_a11y_contrasts(row) == [
        (project, route, "#a1b2c3", "#000000", ratio_milli)
    ]


@pytest.mark.parametrize(
    "line",
    [
        "UE_LIVE_A11Y_CONTRAST_V1 project=private route=settings fg=#ffffff bg=#000000 ratio_milli=1000\n",
        "UE_LIVE_A11Y_CONTRAST_V1 project=desktop route=private fg=#ffffff bg=#000000 ratio_milli=1000\n",
        "UE_LIVE_A11Y_CONTRAST_V1 project=desktop route=settings fg=white bg=#000000 ratio_milli=1000\n",
        "UE_LIVE_A11Y_CONTRAST_V1 project=desktop route=settings fg=#ffffff bg=#000000 ratio_milli=21001\n",
        "UE_LIVE_A11Y_CONTRAST_V1 project=desktop route=settings fg=#ffffff bg=#000000 ratio_milli=02100\n",
        "UE_LIVE_A11Y_CONTRAST_V1 project=desktop route=settings fg=#ffffff bg=#000000 ratio_milli=-1\n",
        "UE_LIVE_A11Y_CONTRAST_V1 project=desktop route=settings fg=#ffffff bg=#000000 ratio_milli=1000 private-token\n",
        "prefix UE_LIVE_A11Y_CONTRAST_V1 project=desktop route=settings fg=#ffffff bg=#000000 ratio_milli=1000\n",
        "UE_LIVE_A11Y_CONTRAST_V1 project=desktop route=settings fg=#ffffff bg=#000000 ratio_milli=1000",
        "UE_LIVE_A11Y_CONTRAST_V1 project=desktop route=settings fg=#ffffff bg=#000000 ratio_milli=1000\x1b[0m\n",
        "UE_LIVE_A11Y_CONTRAST_V1 project=desktop route=settings fg=#ffffff bg=#000000 ratio_milli="
        + "1" * 5000
        + "\n",
    ],
)
def test_live_playwright_a11y_contrast_rejects_malformed_records(line: str) -> None:
    assert live_stand._live_playwright_a11y_contrasts(line) == []


def test_live_playwright_a11y_contrast_deduplicates_and_caps_each_project_route() -> (
    None
):
    output = "".join(
        f"UE_LIVE_A11Y_CONTRAST_V1 project=desktop route=settings fg=#ffffff "
        f"bg=#000000 ratio_milli={ratio}\n"
        for ratio in range(8)
    )
    output += (
        "UE_LIVE_A11Y_CONTRAST_V1 project=desktop route=dashboard fg=#ffffff "
        "bg=#000000 ratio_milli=1000\n"
        "UE_LIVE_A11Y_CONTRAST_V1 project=mobile route=settings fg=#ffffff "
        "bg=#000000 ratio_milli=1000\n"
    )
    records = live_stand._live_playwright_a11y_contrasts(output)
    assert records == [
        ("desktop", "settings", "#ffffff", "#000000", ratio) for ratio in range(4)
    ] + [
        ("desktop", "dashboard", "#ffffff", "#000000", 1000),
        ("mobile", "settings", "#ffffff", "#000000", 1000),
    ]


def test_live_playwright_emits_only_bounded_a11y_contrast_values(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    sentinel = (
        "UE_LIVE_A11Y_CONTRAST_V1 project=desktop route=settings "
        "fg=#aabbcc bg=#000000 ratio_milli=2850\n"
    )
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"),
        1,
        stdout=(sentinel + sentinel.rstrip() + " private-token\n").encode(),
        stderr=b"private body and credential",
    )
    monkeypatch.setattr(live_stand.subprocess, "run", lambda *_args, **_kw: completed)
    with pytest.raises(live_stand.StandError, match="exit code 1"):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")

    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E a11y contrast project=desktop route=settings fg=#aabbcc "
        "bg=#000000 ratio_milli=2850",
        "live E2E outcome=failed exit_code=1",
    ]
    assert "private" not in printed.out
    assert "credential" not in printed.out
    assert printed.err == ""


def _a11y_paint_row(**overrides: str) -> str:
    fields = {
        "project": "desktop",
        "route": "settings",
        "axe_fg": "#8691a3",
        "axe_bg": "#f8fafc",
        "ratio_milli": "3040",
        "css_fg": "#8691a3",
        "text_color": "opaque",
        "css_alpha_milli": "1000",
        "node_opacity_milli": "800",
        "ancestor_opacity_milli": "750",
        "opacity_tag": "multiple",
        "page_ready": "true",
        "page_opacity_milli": "900",
        "layout_opacity_milli": "800",
        "animation": "opacity",
        "active_animations": "2",
    }
    fields.update(overrides)
    return (
        f"UE_LIVE_A11Y_PAINT_V1 project={fields['project']} route={fields['route']} "
        f"axe_fg={fields['axe_fg']} axe_bg={fields['axe_bg']} ratio_milli={fields['ratio_milli']} "
        f"css_fg={fields['css_fg']} text_color={fields['text_color']} "
        f"css_alpha_milli={fields['css_alpha_milli']} "
        f"node_opacity_milli={fields['node_opacity_milli']} "
        f"ancestor_opacity_milli={fields['ancestor_opacity_milli']} "
        f"opacity_tag={fields['opacity_tag']} "
        f"page_ready={fields['page_ready']} page_opacity_milli={fields['page_opacity_milli']} "
        f"layout_opacity_milli={fields['layout_opacity_milli']} animation={fields['animation']} "
        f"active_animations={fields['active_animations']}\n"
    )


def _a11y_phase_row(**overrides: str) -> str:
    fields = {
        "project": "desktop",
        "route": "settings",
        "phase": "before_axe",
        "page_ready": "true",
        "page_opacity_milli": "900",
        "root_opacity_milli": "1000",
        "layout_opacity_milli": "800",
        "animation": "opacity",
        "active_animations": "2",
    }
    fields.update(overrides)
    return (
        "UE_LIVE_A11Y_PHASE_V1 "
        + " ".join(f"{name}={value}" for name, value in fields.items())
        + "\n"
    )


def _footer_geometry_row(**overrides: str) -> str:
    fields = {
        "project": "mobile",
        "req_w_milli": "390000",
        "req_h_milli": "844000",
        "inner_w_milli": "390000",
        "inner_h_milli": "844000",
        "client_w_milli": "390000",
        "scroll_w_milli": "390000",
        "nav_left_milli": "0",
        "nav_right_milli": "390000",
        "nav_top_milli": "780000",
        "nav_bottom_milli": "844000",
        "nav_width_milli": "390000",
        "nav_transform_present": "false",
        "nav_tx_milli": "0",
        "nav_ty_milli": "0",
        "fixed_cb_found": "false",
        "fixed_cb_depth": "0",
        "cb_left_milli": "0",
        "cb_right_milli": "0",
        "cb_top_milli": "0",
        "cb_bottom_milli": "0",
    }
    fields.update(overrides)
    return (
        "UE_LIVE_FOOTER_GEOM_V1 "
        + " ".join(f"{name}={value}" for name, value in fields.items())
        + "\n"
    )


def _news_viewport_row(**overrides: str) -> str:
    fields = {
        "project": "desktop",
        "language": "ru",
        "width": "390",
        "viewportHeight": "900",
        "scrollY": "-12",
        "top": "-4",
        "bottom": "22",
        "left": "0",
        "right": "390",
    }
    fields.update(overrides)
    return (
        "UE_LIVE_NEWS_VIEWPORT_V1 "
        + " ".join(f"{name}={value}" for name, value in fields.items())
        + "\n"
    )


def _page_error_detail_row(**overrides: str) -> str:
    fields = {
        "project": "desktop",
        "check": "map-gesture",
        "page": "map",
        "type": "type-error",
        "source": "map-worker",
        "line": "17",
        "column": "4",
        "count": "2",
    }
    fields.update(overrides)
    return (
        "UE_LIVE_PAGE_ERROR_DETAIL_V1 "
        + " ".join(f"{name}={value}" for name, value in fields.items())
        + "\n"
    )


def test_live_playwright_news_viewport_accepts_bounded_crlf_row() -> None:
    row = _news_viewport_row().replace("\n", "\r\n")
    assert live_stand._live_playwright_news_viewports(row) == [
        ("desktop", "ru", 390, 900, -12, -4, 22, 0, 390)
    ]


@pytest.mark.parametrize(
    "row",
    [
        _news_viewport_row(project="private-project"),
        _news_viewport_row(language="fr"),
        _news_viewport_row(width="391"),
        _news_viewport_row(viewportHeight="0"),
        _news_viewport_row(viewportHeight="1000000"),
        _news_viewport_row(scrollY="1000000"),
        _news_viewport_row(scrollY="-1000000"),
        _news_viewport_row(top="-1000000"),
        _news_viewport_row(bottom="-5"),
        _news_viewport_row(right="-1"),
        _news_viewport_row(bottom="not-a-number"),
        _news_viewport_row().replace("right=390", "right=390 private-token"),
        _news_viewport_row().rstrip("\n"),
        _news_viewport_row().replace("\n", "\x00\n"),
    ],
)
def test_live_playwright_news_viewport_rejects_malformed_or_private_rows(
    row: str,
) -> None:
    assert live_stand._live_playwright_news_viewports(row) == []


def test_live_playwright_news_viewport_deduplicates_and_caps_allowed_tuples() -> None:
    rows = "".join(
        _news_viewport_row(project=project, language=language, width=str(width))
        for project in ("desktop", "mobile")
        for language in ("ru", "en")
        for width in (360, 390, 768, 1024, 1440)
    )
    parsed = live_stand._live_playwright_news_viewports(rows + rows)
    assert len(parsed) == 20
    assert {(record[0], record[1], record[2]) for record in parsed} == {
        (project, language, width)
        for project in ("desktop", "mobile")
        for language in ("ru", "en")
        for width in (360, 390, 768, 1024, 1440)
    }


def test_live_playwright_a11y_phase_parser_accepts_two_fixed_phases_per_route() -> None:
    rows = (
        _a11y_phase_row()
        + _a11y_phase_row(page_opacity_milli="700")
        + _a11y_phase_row(
            phase="after_axe",
            page_opacity_milli="1000",
            animation="none",
            active_animations="0",
        )
    )
    assert live_stand._live_playwright_a11y_phase_states(rows) == [
        ("desktop", "settings", "before_axe", True, 900, 1000, 800, "opacity", 2),
        ("desktop", "settings", "after_axe", True, 1000, 1000, 800, "none", 0),
    ]


@pytest.mark.parametrize(
    "row",
    [
        _a11y_phase_row(project="private-project"),
        _a11y_phase_row(phase="private-phase"),
        _a11y_phase_row(page_opacity_milli="1001"),
        _a11y_phase_row(root_opacity_milli="1001"),
        _a11y_phase_row(animation="private-css-property"),
        _a11y_phase_row(active_animations="1000"),
        _a11y_phase_row().rstrip("\n"),
        _a11y_phase_row().replace("\n", "\x1b[0m\n"),
        _a11y_phase_row()[:-1] + " private-selector\n",
    ],
)
def test_live_playwright_a11y_phase_parser_rejects_malformed_rows(row: str) -> None:
    assert live_stand._live_playwright_a11y_phase_states(row) == []


def test_live_playwright_a11y_paint_parser_accepts_closed_finite_tags() -> None:
    row = _a11y_paint_row().replace("#8691a3", "#A1b2C3")
    assert live_stand._live_playwright_a11y_paint_states(row) == [
        (
            "desktop",
            "settings",
            "#a1b2c3",
            "#f8fafc",
            3040,
            "#a1b2c3",
            "opaque",
            1000,
            800,
            750,
            "multiple",
            True,
            900,
            800,
            "opacity",
            2,
        )
    ]
    assert (
        live_stand._live_playwright_a11y_paint_states(
            _a11y_paint_row(page_ready="false")
        )[0][11]
        is False
    )


@pytest.mark.parametrize(
    "row",
    [
        _a11y_paint_row(project="private-project"),
        _a11y_paint_row(text_color="private-token"),
        _a11y_paint_row(opacity_tag="opacity=0.5"),
        _a11y_paint_row(animation="private-css-property"),
        _a11y_paint_row(active_animations="1000"),
        _a11y_paint_row(css_alpha_milli="1001"),
        _a11y_paint_row(ratio_milli="21001"),
        _a11y_paint_row().rstrip("\n"),
        _a11y_paint_row().replace("\n", "\x1b[0m\n"),
        _a11y_paint_row()[:-1] + " private-response-token\n",
    ],
)
def test_live_playwright_a11y_paint_parser_rejects_malformed_rows(row: str) -> None:
    assert live_stand._live_playwright_a11y_paint_states(row) == []


def test_live_playwright_a11y_paint_parser_deduplicates_and_caps_per_route() -> None:
    rows = "".join(_a11y_paint_row(ratio_milli=str(value)) for value in range(8))
    rows += _a11y_paint_row(route="dashboard")
    rows += _a11y_paint_row(project="mobile")
    parsed = live_stand._live_playwright_a11y_paint_states(rows)
    assert len(parsed) == 6
    assert [row[4] for row in parsed[:4]] == [0, 1, 2, 3]
    assert [(row[0], row[1]) for row in parsed[4:]] == [
        ("desktop", "dashboard"),
        ("mobile", "settings"),
    ]


def test_live_playwright_footer_parser_bounds_geometry_and_fixed_block_flags() -> None:
    row = _footer_geometry_row().replace("\n", "\r\n")
    parsed = live_stand._live_playwright_footer_geometries(row)
    assert parsed == [
        (
            "mobile",
            390000,
            844000,
            390000,
            844000,
            390000,
            390000,
            0,
            390000,
            780000,
            844000,
            390000,
            False,
            0,
            0,
            False,
            0,
            0,
            0,
            0,
            0,
        )
    ]
    containing_block = _footer_geometry_row(
        project="desktop",
        nav_left_milli="-11250",
        nav_right_milli="400000",
        nav_width_milli="411250",
        nav_transform_present="true",
        nav_tx_milli="-11250",
        fixed_cb_found="true",
        fixed_cb_depth="2",
        cb_left_milli="-12000",
        cb_right_milli="412000",
        cb_bottom_milli="800000",
    )
    assert live_stand._live_playwright_footer_geometries(containing_block)[0][
        15:17
    ] == (True, 2)


@pytest.mark.parametrize(
    "row",
    [
        _footer_geometry_row(project="private-project"),
        _footer_geometry_row(req_w_milli="0"),
        _footer_geometry_row(inner_w_milli="0"),
        _footer_geometry_row(inner_h_milli="0"),
        _footer_geometry_row(nav_width_milli="-1"),
        _footer_geometry_row(nav_left_milli="5000001"),
        _footer_geometry_row(fixed_cb_found="true"),
        _footer_geometry_row(fixed_cb_depth="33"),
        _footer_geometry_row(cb_left_milli="1"),
        _footer_geometry_row().rstrip("\n"),
        _footer_geometry_row()[:-1] + " private-selector\n",
        _footer_geometry_row().replace("\n", "\x00\n"),
    ],
)
def test_live_playwright_footer_parser_rejects_malformed_rows(row: str) -> None:
    assert live_stand._live_playwright_footer_geometries(row) == []


def test_live_playwright_emits_only_closed_paint_and_footer_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    paint = _a11y_paint_row()
    footer = _footer_geometry_row()
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"),
        1,
        stdout=(
            paint
            + footer
            + "private response body password=not-for-output\n"
            + _a11y_paint_row(text_color="private-token")
        ).encode(),
        stderr=b"private traceback and credential\n" + _footer_geometry_row().encode(),
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    with pytest.raises(live_stand.StandError, match="exit code 1"):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")

    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E a11y paint project=desktop route=settings axe_fg=#8691a3 "
        "axe_bg=#f8fafc ratio_milli=3040 css_fg=#8691a3 text_color=opaque "
        "css_alpha_milli=1000 node_opacity_milli=800 ancestor_opacity_milli=750 "
        "opacity_tag=multiple page_ready=true page_opacity_milli=900 "
        "layout_opacity_milli=800 animation=opacity active_animations=2",
        "live E2E footer geometry project=mobile req_w_milli=390000 req_h_milli=844000 "
        "inner_w_milli=390000 inner_h_milli=844000 client_w_milli=390000 "
        "scroll_w_milli=390000 nav_left_milli=0 nav_right_milli=390000 "
        "nav_top_milli=780000 nav_bottom_milli=844000 nav_width_milli=390000 "
        "nav_transform_present=false nav_tx_milli=0 nav_ty_milli=0 "
        "fixed_cb_found=false fixed_cb_depth=0 cb_left_milli=0 cb_right_milli=0 "
        "cb_top_milli=0 cb_bottom_milli=0",
        "live E2E outcome=failed exit_code=1",
    ]
    assert "private" not in printed.out + printed.err
    assert "credential" not in printed.out + printed.err
    assert printed.err == ""
    assert completed.stdout == completed.stderr == b""


@pytest.mark.parametrize("project", ["desktop", "mobile"])
@pytest.mark.parametrize(
    "check",
    [
        "admin-users",
        "admin-feature-flags",
        "admin-feature-flags-ui",
        "password-reset-replay",
        "messenger-message-send",
        "chat-attachment-create",
    ],
)
@pytest.mark.parametrize("status", [100, 200, 403, 500, 599])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_live_playwright_http_status_accepts_only_fixed_domains(
    project: str, check: str, status: int, newline: str
) -> None:
    sentinel = f"UE_LIVE_HTTP_STATUS_V1 project={project} check={check} status={status}{newline}"
    assert live_stand._live_playwright_http_statuses(sentinel) == [
        (project, check, status)
    ]


@pytest.mark.parametrize(
    "check",
    ["auth-login", "auth-logout", "auth-session-preflight"],
)
@pytest.mark.parametrize("project", ["desktop", "mobile"])
@pytest.mark.parametrize("status", [100, 200, 403, 500, 599])
def test_live_playwright_http_status_accepts_auth_status_checks(
    project: str, check: str, status: int
) -> None:
    sentinel = (
        f"UE_LIVE_HTTP_STATUS_V1 project={project} check={check} status={status}\n"
    )
    assert live_stand._live_playwright_http_statuses(sentinel) == [
        (project, check, status)
    ]


@pytest.mark.parametrize("project", ["desktop", "mobile"])
@pytest.mark.parametrize(
    "check",
    [
        "email-otp-register",
        "email-otp-verification-start",
        "email-otp-verification-wrong-code",
        "email-otp-verification-resend",
        "email-otp-verification-stale-code",
        "email-otp-verification-accept",
        "email-mfa-register",
        "email-mfa-initial-login",
        "email-mfa-sibling-login",
        "email-mfa-verification-start",
        "email-mfa-verification-accept",
        "email-mfa-enable-start",
        "email-mfa-enable-accept",
        "email-mfa-enabled-login",
        "email-mfa-login-resend-early",
        "email-mfa-login-accept",
    ],
)
@pytest.mark.parametrize(("status", "newline"), [(202, "\n"), (429, "\r\n")])
def test_live_playwright_email_otp_and_mfa_http_statuses_are_closed(
    project: str, check: str, status: int, newline: str
) -> None:
    row = f"UE_LIVE_HTTP_STATUS_V1 project={project} check={check} status={status}{newline}"
    assert live_stand._live_playwright_http_statuses(row) == [(project, check, status)]
    assert (
        live_stand._live_playwright_http_statuses(
            row.replace(f"check={check}", "check=email-mfa-login-accept-private")
        )
        == []
    )


@pytest.mark.parametrize("project", ["desktop", "mobile"])
def test_live_playwright_http_status_auth_session_cap_requires_exact_forbidden_status(
    project: str,
) -> None:
    accepted = (
        f"UE_LIVE_HTTP_STATUS_V1 project={project} check=auth-session-cap status=403\n"
    )
    assert live_stand._live_playwright_http_statuses(accepted) == [
        (project, "auth-session-cap", 403)
    ]
    for status in (200, 401, 429, 500):
        rejected = accepted.replace("status=403", f"status={status}")
        assert live_stand._live_playwright_http_statuses(rejected) == []


@pytest.mark.parametrize("project", ["desktop", "mobile"])
@pytest.mark.parametrize(
    ("limit", "remaining", "expected_limit", "expected_remaining", "newline"),
    [
        ("1", "0", 1, 0, "\n"),
        ("100000", "100000", 100000, 100000, "\r\n"),
        ("invalid", "0", None, 0, "\n"),
        ("5", "invalid", 5, None, "\r\n"),
    ],
)
def test_live_playwright_rate_limit_metadata_accepts_bounded_logout_headers(
    project: str,
    limit: str,
    remaining: str,
    expected_limit: int | None,
    expected_remaining: int | None,
    newline: str,
) -> None:
    row = (
        f"UE_LIVE_RATE_LIMIT_V1 project={project} check=auth-logout "
        f"x_ratelimit_limit={limit} x_ratelimit_remaining={remaining}" + newline
    )
    assert live_stand._live_playwright_rate_limit_headers(row) == [
        (project, expected_limit, expected_remaining)
    ]


@pytest.mark.parametrize(
    "row",
    [
        "UE_LIVE_RATE_LIMIT_V1 project=private check=auth-logout x_ratelimit_limit=5 x_ratelimit_remaining=0\n",
        "UE_LIVE_RATE_LIMIT_V1 project=desktop check=password-reset-replay x_ratelimit_limit=5 x_ratelimit_remaining=0\n",
        "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout x_ratelimit_limit=0 x_ratelimit_remaining=0\n",
        "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout x_ratelimit_limit=100001 x_ratelimit_remaining=0\n",
        "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout x_ratelimit_limit=01 x_ratelimit_remaining=0\n",
        "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout x_ratelimit_limit=5 x_ratelimit_remaining=100001\n",
        "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout x_ratelimit_limit=5 x_ratelimit_remaining=01\n",
        "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout x_ratelimit_limit=5 x_ratelimit_remaining=6\n",
        "private-token UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout x_ratelimit_limit=5 x_ratelimit_remaining=0\n",
        "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout x_ratelimit_limit=5 x_ratelimit_remaining=0 private-token\n",
        "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout x_ratelimit_limit=5 x_ratelimit_remaining=0",
    ],
)
def test_live_playwright_rate_limit_metadata_rejects_malformed_or_unterminated_rows(
    row: str,
) -> None:
    assert live_stand._live_playwright_rate_limit_headers(row) == []


def test_live_playwright_rate_limit_metadata_deduplicates_and_caps_records() -> None:
    rows = "".join(
        "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout "
        f"x_ratelimit_limit=100 x_ratelimit_remaining={remaining}\n"
        for remaining in range(40)
    )
    records = live_stand._live_playwright_rate_limit_headers(rows + rows)
    assert records == [("desktop", 100, remaining) for remaining in range(32)]


@pytest.mark.parametrize("project", ["desktop", "mobile"])
@pytest.mark.parametrize(
    "check",
    ["auth-logout", "password-reset-replay", "email-mfa-enabled-login"],
)
@pytest.mark.parametrize("retry_after", [1, 40, 60])
@pytest.mark.parametrize("decision", ["retry", "declined-deadline"])
def test_live_playwright_retry_diagnostics_accept_bounded_integer_decisions(
    project: str, check: str, retry_after: int, decision: str
) -> None:
    row = (
        f"UE_LIVE_RETRY_V1 project={project} check={check} "
        f"retry_after_seconds={retry_after} decision={decision} remaining_ms=12345\n"
    )
    assert live_stand._live_playwright_retry_decisions(row) == [
        (project, check, retry_after, decision, 12345)
    ]


@pytest.mark.parametrize("project", ["desktop", "mobile"])
@pytest.mark.parametrize(
    "check",
    ["auth-logout", "email-otp-verification-wrong-code", "email-mfa-enabled-login"],
)
def test_live_playwright_retry_diagnostic_accepts_closed_check_values(
    project: str, check: str
) -> None:
    row = (
        f"UE_LIVE_RETRY_V1 project={project} check={check} "
        "retry_after_seconds=invalid decision=declined-header remaining_ms=0\n"
    )
    assert live_stand._live_playwright_retry_decisions(row) == [
        (project, check, None, "declined-header", 0)
    ]


@pytest.mark.parametrize("retry_after", [None, 61, 600])
def test_live_playwright_stale_code_throttle_diagnostic_is_not_retried(
    retry_after: int | None,
) -> None:
    retry_after_text = "invalid" if retry_after is None else str(retry_after)
    row = (
        "UE_LIVE_RETRY_V1 project=desktop check=email-otp-verification-stale-code "
        f"retry_after_seconds={retry_after_text} decision=not-retried remaining_ms=12345\n"
    )
    assert live_stand._live_playwright_retry_decisions(row) == [
        (
            "desktop",
            "email-otp-verification-stale-code",
            retry_after,
            "not-retried",
            12345,
        )
    ]


@pytest.mark.parametrize(
    "row",
    [
        "UE_LIVE_RETRY_V1 project=private check=auth-logout retry_after_seconds=1 decision=retry remaining_ms=10\n",
        "UE_LIVE_RETRY_V1 project=desktop check=private retry_after_seconds=1 decision=retry remaining_ms=10\n",
        "UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=0 decision=retry remaining_ms=10\n",
        "UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=61 decision=retry remaining_ms=10\n",
        "UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=01 decision=retry remaining_ms=10\n",
        "UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=1 decision=declined-header remaining_ms=10\n",
        "UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=invalid decision=declined-deadline remaining_ms=10\n",
        "UE_LIVE_RETRY_V1 project=desktop check=email-otp-verification-stale-code retry_after_seconds=601 decision=not-retried remaining_ms=10\n",
        "UE_LIVE_RETRY_V1 project=desktop check=email-mfa-enabled-login retry_after_seconds=17 decision=not-retried remaining_ms=10\n",
        "UE_LIVE_RETRY_V1 project=desktop check=email-mfa-enabled-login retry_after_seconds=61 decision=retry remaining_ms=10\n",
        "UE_LIVE_RETRY_V1 project=desktop check=email-mfa-enabled-login-private retry_after_seconds=17 decision=retry remaining_ms=10\n",
        "UE_LIVE_RETRY_V1 project=desktop check=email-otp-verification-stale-code retry_after_seconds=61 decision=retry remaining_ms=10\n",
        "UE_LIVE_RETRY_V1 project=desktop check=email-otp-verification-stale-code retry_after_seconds=61 decision=declined-deadline remaining_ms=10\n",
        "UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=61 decision=not-retried remaining_ms=10\n",
        "UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=1 decision=retry remaining_ms=60001\n",
        "UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=1 decision=retry remaining_ms=99999\n",
        "UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=1 decision=retry remaining_ms=10 credential\n",
        "UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=1 decision=retry remaining_ms=0\n",
    ],
)
def test_live_playwright_retry_diagnostics_reject_malformed_records(row: str) -> None:
    assert live_stand._live_playwright_retry_decisions(row) == []


def test_live_playwright_retry_diagnostics_deduplicate_and_bound_records() -> None:
    output = "".join(
        "UE_LIVE_RETRY_V1 project=desktop check=auth-logout "
        f"retry_after_seconds=1 decision=retry remaining_ms={remaining}\n"
        for remaining in range(1, 41)
    )
    records = live_stand._live_playwright_retry_decisions(output + output)
    assert records == [
        ("desktop", "auth-logout", 1, "retry", remaining) for remaining in range(1, 33)
    ]


@pytest.mark.parametrize("project", ["desktop", "mobile"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize(
    ("permission", "ready", "state", "controller", "subscription", "matches"),
    [
        ("default", "resolved", "installing", "0", "0", "0"),
        ("granted", "timeout", "installed", "1", "1", "1"),
        ("denied", "error", "activating", "0", "1", "0"),
        ("unsupported", "resolved", "activated", "1", "0", "1"),
        ("default", "timeout", "redundant", "0", "1", "0"),
        ("granted", "error", "missing", "1", "0", "1"),
        ("denied", "resolved", "error", "0", "0", "0"),
    ],
)
def test_live_playwright_push_observation_accepts_closed_records(
    project: str,
    newline: str,
    permission: str,
    ready: str,
    state: str,
    controller: str,
    subscription: str,
    matches: str,
) -> None:
    row = (
        f"UE_LIVE_PUSH_OBS_V1 project={project} permission={permission} "
        f"ready={ready} state={state} controller={controller} "
        f"subscription={subscription} matches={matches}" + newline
    )
    assert live_stand._live_playwright_push_observations(row) == [
        (
            project,
            permission,
            ready,
            state,
            controller == "1",
            subscription == "1",
            int(matches),
        )
    ]


def test_live_playwright_push_observation_rejects_malformed_records() -> None:
    valid = (
        "UE_LIVE_PUSH_OBS_V1 project=desktop permission=granted ready=resolved "
        "state=activated controller=1 subscription=1 matches=1\n"
    )
    malformed = (
        valid.replace("project=desktop", "project=private-project"),
        valid.replace("permission=granted", "permission=private"),
        valid.replace("ready=resolved", "ready=private"),
        valid.replace("state=activated", "state=private"),
        valid.replace("controller=1", "controller=true"),
        valid.replace("matches=1", "matches=2"),
        valid[:-1] + " private-url\n",
        "private " + valid,
        valid[:-1] + " \n",
        valid[:-1],
        valid.replace("permission=granted", "permission=granted\x1b[0m"),
        valid.replace("matches=1\n", "matches=1\u202e\n"),
        valid[:-1] + " " + "x" * 300 + "\n",
    )
    for row in malformed:
        assert live_stand._live_playwright_push_observations(row) == []


def test_live_playwright_push_observation_caps_and_deduplicates() -> None:
    rows = [
        "UE_LIVE_PUSH_OBS_V1 project=desktop permission=default "
        "ready=resolved state=activated controller=1 subscription=1 matches=0\n",
        "UE_LIVE_PUSH_OBS_V1 project=desktop permission=granted "
        "ready=resolved state=activated controller=1 subscription=1 matches=0\n",
        "UE_LIVE_PUSH_OBS_V1 project=desktop permission=denied "
        "ready=resolved state=activated controller=1 subscription=1 matches=0\n",
        "UE_LIVE_PUSH_OBS_V1 project=desktop permission=unsupported "
        "ready=resolved state=activated controller=1 subscription=1 matches=0\n",
        "UE_LIVE_PUSH_OBS_V1 project=mobile permission=default "
        "ready=resolved state=activated controller=1 subscription=1 matches=0\n",
    ]
    parsed = live_stand._live_playwright_push_observations(
        rows[0] + rows[1] + rows[0] + rows[2] + rows[3] + rows[4]
    )
    assert parsed == [
        ("desktop", "default", "resolved", "activated", True, True, 0),
        ("desktop", "granted", "resolved", "activated", True, True, 0),
        ("desktop", "denied", "resolved", "activated", True, True, 0),
        ("desktop", "unsupported", "resolved", "activated", True, True, 0),
    ]


def test_live_playwright_emits_only_validated_push_observations_from_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    row = (
        "UE_LIVE_PUSH_OBS_V1 project=mobile permission=granted ready=timeout "
        "state=activated controller=1 subscription=1 matches=0\n"
    )
    private = "private push endpoint notification-id message-content raw-error"
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"),
        1,
        stdout=(row + private + "\n").encode(),
        stderr=(row + private + "\n").encode(),
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    with pytest.raises(live_stand.StandError, match="exit code 1"):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")

    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E push project=mobile permission=granted ready=timeout "
        "state=activated controller=true subscription=true matches=0",
        "live E2E outcome=failed exit_code=1",
    ]
    assert private not in printed.out + printed.err
    assert printed.err == ""
    assert completed.stdout == completed.stderr == b""


_STORY_MEMORY_EVENT_KEYS = (
    "appinstalled",
    "beforeinstallprompt",
    "visibilitychange",
    "focus",
    "blur",
    "focusin",
    "focusout",
    "keydown",
    "keyup",
    "click",
    "ecosystem:push-education-requested",
    "mousedown",
    "mouseup",
    "pointerdown",
    "pointerup",
    "touchstart",
    "touchend",
    "online",
    "offline",
    "pwa:need-refresh",
    "resize",
    "scroll",
    "other",
)


def _story_memory_record(
    *, project: str = "desktop", status: str = "available", count: int = 1
) -> dict[str, Any]:
    unavailable = status == "unavailable"
    dom: dict[str, int | None] = {
        "documents": None if unavailable else count,
        "nodes": None if unavailable else count + 1,
        "jsEventListeners": None if unavailable else count + 2,
    }
    listener_counts: dict[str, int | None] = {
        "total": None if unavailable else count,
        **{
            key: None if unavailable else (count if index == 0 else 0)
            for index, key in enumerate(_STORY_MEMORY_EVENT_KEYS)
        },
    }
    listeners = {
        "window": listener_counts.copy(),
        "document": listener_counts.copy(),
        "documentTree": listener_counts.copy(),
    }
    return {
        "schema": 2,
        "project": project,
        "phase": "cycle0-after-settle-before-assertion",
        "diagnosticStatus": status,
        "warmDOM": dom.copy(),
        "cycle0DOM": dom.copy(),
        "warmListeners": listeners,
        "cycle0Listeners": {
            target: counts.copy() for target, counts in listeners.items()
        },
    }


def _story_memory_row(record: dict[str, Any], newline: str = "\n") -> str:
    return "STORY_MEMORY_DIAG " + json.dumps(record, separators=(",", ":")) + newline


@pytest.mark.parametrize("project", ["desktop", "mobile"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_live_playwright_story_memory_parser_accepts_closed_available_records(
    project: str, newline: str
) -> None:
    record = _story_memory_record(project=project, count=7)
    assert live_stand._live_playwright_story_memory_records(
        _story_memory_row(record, newline)
    ) == [record]


def test_live_playwright_story_memory_accepts_unavailable_records() -> None:
    record = _story_memory_record(project="mobile", status="unavailable")
    assert live_stand._live_playwright_story_memory_records(
        _story_memory_row(record)
    ) == [record]


def test_live_playwright_story_memory_accepts_the_install_prompt_event_buckets() -> (
    None
):
    record = _story_memory_record(count=1)
    window_counts = record["warmListeners"]["window"]
    for event_name in (
        "appinstalled",
        "beforeinstallprompt",
        "ecosystem:push-education-requested",
        "pwa:need-refresh",
    ):
        window_counts[event_name] = 1
    window_counts["total"] += 3

    assert live_stand._live_playwright_story_memory_records(
        _story_memory_row(record)
    ) == [record]


def test_live_playwright_story_memory_rejects_malformed_records() -> None:
    valid = _story_memory_record()
    malformed: list[dict[str, object]] = []
    for key, value in (
        ("schema", True),
        ("schema", 1),
        ("schema", 3),
        ("project", "private-project"),
        ("phase", "before-assertion"),
        ("diagnosticStatus", "error with private details"),
        ("extra", "credential-shaped-private-value"),
    ):
        record = json.loads(json.dumps(valid))
        record[key] = value
        malformed.append(record)

    record = json.loads(json.dumps(valid))
    record["warmDOM"]["nodes"] = None
    malformed.append(record)
    record = json.loads(json.dumps(valid))
    record["warmDOM"]["nodes"] = -1
    malformed.append(record)
    record = json.loads(json.dumps(valid))
    record["warmDOM"]["nodes"] = 9_007_199_254_740_992
    malformed.append(record)
    record = json.loads(json.dumps(valid))
    record["warmDOM"]["nodes"] = True
    malformed.append(record)
    record = json.loads(json.dumps(valid))
    record["warmDOM"]["nodes"] = 1.0
    malformed.append(record)
    record = json.loads(json.dumps(valid))
    record["warmListeners"]["window"]["private-event-name"] = 1
    malformed.append(record)
    unavailable = _story_memory_record(status="unavailable")
    unavailable["cycle0Listeners"]["documentTree"]["click"] = 1
    malformed.append(unavailable)
    inconsistent_total = _story_memory_record()
    inconsistent_total["warmListeners"]["window"]["focus"] = 1
    malformed.append(inconsistent_total)

    for record in malformed:
        assert (
            live_stand._live_playwright_story_memory_records(_story_memory_row(record))
            == []
        )

    row = _story_memory_row(valid)
    malformed_rows = (
        row.rstrip("\n"),
        row[:-1] + " private-url\n",
        "private title " + row,
        row.replace("\n", "\x00\n"),
        row[:-1].replace('"schema":2', '"schema":2,"schema":2') + "\n",
        row[:-1].replace('"nodes":2', '"nodes":NaN') + "\n",
        "STORY_MEMORY_DIAG " + " " * 8200 + row.split(" ", 1)[1],
    )
    for malformed_row in malformed_rows:
        assert live_stand._live_playwright_story_memory_records(malformed_row) == []


def test_live_playwright_story_memory_parser_deduplicates_and_caps_records() -> None:
    records = [
        _story_memory_record(project="desktop", count=number) for number in range(5)
    ]
    rows = (
        _story_memory_row(records[0])
        + _story_memory_row(records[1])
        + _story_memory_row(records[0])
        + _story_memory_row(records[2])
        + _story_memory_row(records[3])
        + _story_memory_row(records[4])
    )
    assert live_stand._live_playwright_story_memory_records(rows) == records[:4]


def test_live_playwright_emits_only_validated_story_memory_records_from_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    record = _story_memory_record(project="mobile", count=5)
    valid = _story_memory_row(record)
    private = "private listener function token=not-for-output https://private.invalid"
    malformed = _story_memory_row({**record, "phase": private})
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"),
        1,
        stdout=(valid + malformed + private + "\n").encode(),
        stderr=(valid + private + "\n").encode(),
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    with pytest.raises(live_stand.StandError, match="exit code 1"):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")

    printed = capsys.readouterr()
    expected = json.dumps(record, separators=(",", ":"))
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E story memory " + expected,
        "live E2E outcome=failed exit_code=1",
    ]
    assert private not in printed.out + printed.err
    assert printed.err == ""
    assert completed.stdout == completed.stderr == b""


@pytest.mark.parametrize("project", ["desktop", "mobile"])
@pytest.mark.parametrize("newline", [chr(10), chr(13) + chr(10)])
@pytest.mark.parametrize(
    ("check", "status"),
    [
        ("auth-login", 401),
        ("auth-session-cap", 403),
        ("auth-logout", 401),
        ("auth-session-preflight", 403),
    ],
)
def test_live_playwright_auth_status_rows_accept_lf_and_crlf(
    project: str, newline: str, check: str, status: int
) -> None:
    row = (
        f"UE_LIVE_HTTP_STATUS_V1 project={project} check={check} status={status}"
        + newline
    )
    assert live_stand._live_playwright_http_statuses(row) == [(project, check, status)]


@pytest.mark.parametrize(
    "line",
    [
        "UE_LIVE_HTTP_STATUS_V1 project=private-project check=admin-users status=200\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=email-mfa-login-accept-private status=200\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=email-otp-register status=600\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=private-check status=200\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=messenger-message-send status=503 url=https://private.invalid/path\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=99\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=600\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=-200\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=0200\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=200.0\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=２００\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=200 private-token\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=200 \n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=auth-session-cap status=403 detail=too_many_sessions\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=auth-login status=401 extra=private\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=auth-session-cap status=429\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=auth-login status=401\x1b[0m\n",
        " UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=200\n",
        "title UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=200\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=200",
        "UE_LIVE_HTTP_STATUS_V2 project=desktop check=admin-users status=200\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=200\r\r\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=200\x00\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=200\x1b[0m\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=200\u202e\n",
        "private\vUE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=200\n",
        "private\rUE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=200\n",
        "private\u0085UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=200\n",
        "private\u2028UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=200\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status="
        + "9" * 5000
        + "\n",
    ],
)
def test_live_playwright_http_status_rejects_malformed_records(line: str) -> None:
    assert live_stand._live_playwright_http_statuses(line) == []


def test_live_playwright_emits_only_closed_email_otp_and_mfa_http_statuses(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    checks = (
        "email-otp-register",
        "email-otp-verification-start",
        "email-otp-verification-wrong-code",
        "email-otp-verification-resend",
        "email-otp-verification-stale-code",
        "email-otp-verification-accept",
        "email-mfa-register",
        "email-mfa-initial-login",
        "email-mfa-sibling-login",
        "email-mfa-verification-start",
        "email-mfa-verification-accept",
        "email-mfa-enable-start",
        "email-mfa-enable-accept",
        "email-mfa-enabled-login",
        "email-mfa-login-resend-early",
        "email-mfa-login-accept",
    )
    rows = "".join(
        f"UE_LIVE_HTTP_STATUS_V1 project=desktop check={check} status=202\n"
        for check in checks
    )
    private = "private OTP response code=do-not-print token=secret"
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"),
        1,
        stdout=(rows + private + "\n").encode(),
        stderr=(rows + private + "\n").encode(),
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    with pytest.raises(live_stand.StandError, match="exit code 1"):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")

    printed = capsys.readouterr()
    output_rows = printed.out.splitlines()[1:-1]
    assert output_rows == [
        f"live E2E HTTP project=desktop check={check} status=202" for check in checks
    ]
    assert private not in printed.out + printed.err
    assert printed.err == ""
    assert completed.stdout == completed.stderr == b""


def test_live_playwright_http_status_deduplicates_and_bounds_records() -> None:
    output = "".join(
        f"UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status={status}\n"
        * 10
        for status in range(100, 600)
    )
    assert live_stand._live_playwright_http_statuses(output) == [
        ("desktop", "admin-users", status) for status in range(100, 204)
    ]


def test_live_playwright_http_status_discards_rows_after_the_closed_cap() -> None:
    output = "".join(
        f"UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status={status}\n"
        for status in range(100, 205)
    )
    output += "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=205 private-url\n"
    records = live_stand._live_playwright_http_statuses(output)
    assert len(records) == 104
    assert records[0] == ("desktop", "admin-users", 100)
    assert records[-1] == ("desktop", "admin-users", 203)
    assert ("desktop", "admin-users", 204) not in records
    assert ("desktop", "admin-users", 205) not in records


def test_live_playwright_http_status_retains_retry_after_eight_initial_records() -> (
    None
):
    initial = [
        (project, check, 400 if check == "password-reset-replay" else 200)
        for project in ("desktop", "mobile")
        for check in (
            "admin-users",
            "admin-feature-flags",
            "admin-feature-flags-ui",
            "password-reset-replay",
        )
    ]
    # Synthetic status proves retention without guessing the omitted live status.
    retry = ("mobile", "password-reset-replay", 429)
    output = "".join(
        f"UE_LIVE_HTTP_STATUS_V1 project={project} check={check} status={status}\n"
        for project, check, status in [*initial, retry, retry]
    )
    assert live_stand._live_playwright_http_statuses(output) == [*initial, retry]


@pytest.mark.parametrize("return_code", [0, 1, 23])
def test_live_playwright_emits_only_bounded_status_and_retry_metadata(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    return_code: int,
) -> None:
    sentinel = "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=503\n"
    auth_sentinels = (
        "UE_LIVE_HTTP_STATUS_V1 project=mobile check=auth-login status=401\n"
        "UE_LIVE_HTTP_STATUS_V1 project=mobile check=auth-session-cap status=403\n"
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=auth-logout status=401\n"
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=auth-session-preflight status=403\n"
    )
    retry_sentinels = (
        "UE_LIVE_RETRY_V1 project=mobile check=auth-logout "
        "retry_after_seconds=40 decision=retry remaining_ms=30000\n"
        "UE_LIVE_RETRY_V1 project=mobile check=email-otp-verification-wrong-code "
        "retry_after_seconds=2 decision=retry remaining_ms=1200\n"
        "UE_LIVE_RETRY_V1 project=mobile check=email-mfa-enabled-login "
        "retry_after_seconds=17 decision=retry remaining_ms=59999\n"
        "UE_LIVE_RETRY_V1 project=desktop check=password-reset-replay "
        "retry_after_seconds=invalid decision=declined-header remaining_ms=0\n"
    )
    rate_limit_sentinel = (
        "UE_LIVE_RATE_LIMIT_V1 project=mobile check=auth-logout "
        "x_ratelimit_limit=5 x_ratelimit_remaining=0\n"
        "UE_LIVE_RATE_LIMIT_V1 project=mobile check=auth-logout "
        "x_ratelimit_limit=5 x_ratelimit_remaining=0 private-token\n"
    )
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"),
        return_code,
        stdout=(
            "private-title https://private.invalid/?token=private-token\n"
            + sentinel * 20
            + auth_sentinels
            + retry_sentinels
            + rate_limit_sentinel
            + "UE_LIVE_HTTP_STATUS_V1 project=mobile check=admin-feature-flags status=403\n"
            + "UE_LIVE_HTTP_STATUS_V1 project=mobile check=admin-users status="
        ).encode(),
        stderr=(
            b"401\n"
            b"UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout x_ratelimit_limit=9 x_ratelimit_remaining=0\n"
            b"UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=500\n"
            b"private-body private-credential private-browser-state\n"
        ),
    )
    monkeypatch.setattr(live_stand.subprocess, "run", lambda *_args, **_kw: completed)
    if return_code:
        with pytest.raises(live_stand.StandError, match=f"exit code {return_code}"):
            live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    else:
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")

    printed = capsys.readouterr()
    outcome = "failed" if return_code else "passed"
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E HTTP project=desktop check=admin-users status=503",
        "live E2E HTTP project=mobile check=auth-login status=401",
        "live E2E HTTP project=mobile check=auth-session-cap status=403",
        "live E2E HTTP project=desktop check=auth-logout status=401",
        "live E2E HTTP project=desktop check=auth-session-preflight status=403",
        "live E2E HTTP project=mobile check=admin-feature-flags status=403",
        "live E2E retry project=mobile check=auth-logout retry_after_seconds=40 decision=retry remaining_ms=30000",
        "live E2E retry project=mobile check=email-otp-verification-wrong-code retry_after_seconds=2 decision=retry remaining_ms=1200",
        "live E2E retry project=mobile check=email-mfa-enabled-login retry_after_seconds=17 decision=retry remaining_ms=59999",
        "live E2E retry project=desktop check=password-reset-replay retry_after_seconds=invalid decision=declined-header remaining_ms=0",
        "live E2E rate-limit project=mobile check=auth-logout x_ratelimit_limit=5 x_ratelimit_remaining=0",
        f"live E2E outcome={outcome} exit_code={return_code}",
    ]
    assert printed.err == ""
    assert completed.stdout == completed.stderr == b""


@pytest.mark.parametrize("project", ["desktop", "mobile"])
@pytest.mark.parametrize(
    "page",
    ["register", "login", "forgot-password", "reset-password", "dashboard", "other"],
)
@pytest.mark.parametrize(
    "kind",
    [
        "error",
        "type-error",
        "reference-error",
        "syntax-error",
        "range-error",
        "uri-error",
        "eval-error",
        "aggregate-error",
        "abort-error",
        "security-error",
        "invalid-state-error",
        "other",
    ],
)
@pytest.mark.parametrize("count", [1, 999])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_live_playwright_page_errors_accept_only_fixed_domains(
    project: str, page: str, kind: str, count: int, newline: str
) -> None:
    sentinel = (
        f"UE_LIVE_PAGE_ERROR_V1 project={project} check=password-reset page={page} "
        f"type={kind} count={count}{newline}"
    )
    assert live_stand._live_playwright_page_errors(sentinel) == [
        (project, "password-reset", page, kind, count)
    ]


@pytest.mark.parametrize("project", ["desktop", "mobile"])
@pytest.mark.parametrize("page", ["admin-notifications", "dashboard", "login"])
@pytest.mark.parametrize("kind", ["react-418", "invalid-state-error", "other"])
@pytest.mark.parametrize("count", [1, 999])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_live_playwright_page_errors_accept_admin_hydration_domains(
    project: str, page: str, kind: str, count: int, newline: str
) -> None:
    sentinel = (
        f"UE_LIVE_PAGE_ERROR_V1 project={project} check=admin-notifications "
        f"page={page} type={kind} count={count}{newline}"
    )
    assert live_stand._live_playwright_page_errors(sentinel) == [
        (project, "admin-notifications", page, kind, count)
    ]


@pytest.mark.parametrize(
    ("project", "page", "kind", "count", "newline"),
    [
        ("desktop", "login", "type-error", 1, "\n"),
        ("mobile", "dashboard", "react-418", 999, "\r\n"),
        ("desktop", "admin-users", "other", 999, "\r\n"),
        ("mobile", "admin-feature-flags", "type-error", 1, "\r\n"),
        ("desktop", "other", "react-418", 999, "\n"),
        ("mobile", "login", "other", 1, "\n"),
        ("desktop", "dashboard", "type-error", 999, "\r\n"),
        ("mobile", "admin-users", "react-418", 1, "\n"),
        ("desktop", "admin-feature-flags", "other", 1, "\r\n"),
        ("mobile", "other", "type-error", 999, "\r\n"),
    ],
)
def test_live_playwright_page_errors_accept_auth_roles_domain(
    project: str, page: str, kind: str, count: int, newline: str
) -> None:
    sentinel = (
        f"UE_LIVE_PAGE_ERROR_V1 project={project} check=auth-roles page={page} "
        f"type={kind} count={count}{newline}"
    )
    assert live_stand._live_playwright_page_errors(sentinel) == [
        (project, "auth-roles", page, kind, count)
    ]


@pytest.mark.parametrize("project", ["desktop", "mobile"])
@pytest.mark.parametrize("page", ["login", "map", "other"])
@pytest.mark.parametrize("kind", ["type-error", "react-418", "other"])
@pytest.mark.parametrize("count", [1, 999])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_live_playwright_page_errors_accept_map_gesture_domain(
    project: str, page: str, kind: str, count: int, newline: str
) -> None:
    sentinel = (
        f"UE_LIVE_PAGE_ERROR_V1 project={project} check=map-gesture page={page} "
        f"type={kind} count={count}{newline}"
    )
    assert live_stand._live_playwright_page_errors(sentinel) == [
        (project, "map-gesture", page, kind, count)
    ]


@pytest.mark.parametrize("page", ["login", "schedule", "other"])
@pytest.mark.parametrize("kind", ["error", "react-418", "other"])
def test_live_playwright_page_errors_accept_schedule_keyboard_domain(
    page: str, kind: str
) -> None:
    sentinel = (
        "UE_LIVE_PAGE_ERROR_V1 project=desktop check=schedule-grid-keyboard "
        f"page={page} type={kind} count=2\r\n"
    )
    assert live_stand._live_playwright_page_errors(sentinel) == [
        ("desktop", "schedule-grid-keyboard", page, kind, 2)
    ]


def test_live_playwright_page_error_details_accept_only_matching_fixed_summaries() -> (
    None
):
    map_summary = (
        "UE_LIVE_PAGE_ERROR_V1 project=desktop check=map-gesture page=map "
        "type=type-error count=2\n"
    )
    map_detail = _page_error_detail_row().replace("\n", "\r\n")
    assert live_stand._live_playwright_page_error_details(
        map_summary + map_detail + map_detail
    ) == [("desktop", "map-gesture", "map", "type-error", "map-worker", 17, 4, 2)]
    schedule_summary = (
        "UE_LIVE_PAGE_ERROR_V1 project=desktop check=schedule-grid-keyboard "
        "page=schedule type=reference-error count=1\n"
    )
    schedule_detail = _page_error_detail_row(
        project="desktop",
        check="schedule-grid-keyboard",
        page="schedule",
        type="reference-error",
        source="schedule-bundle",
        line="211",
        column="9",
        count="1",
    )
    assert live_stand._live_playwright_page_error_details(
        schedule_summary + schedule_detail
    ) == [
        (
            "desktop",
            "schedule-grid-keyboard",
            "schedule",
            "reference-error",
            "schedule-bundle",
            211,
            9,
            1,
        )
    ]


@pytest.mark.parametrize(
    ("summary", "detail"),
    [
        (
            "UE_LIVE_PAGE_ERROR_V1 project=desktop check=map-gesture page=map type=error count=1\n",
            _page_error_detail_row(source="schedule-bundle", type="error", count="1"),
        ),
        (
            "UE_LIVE_PAGE_ERROR_V1 project=mobile check=schedule-grid-keyboard page=schedule type=error count=1\n",
            _page_error_detail_row(
                project="mobile",
                check="schedule-grid-keyboard",
                page="schedule",
                source="schedule-bundle",
                line="211",
                column="9",
                type="error",
                count="1",
            ),
        ),
        (
            "UE_LIVE_PAGE_ERROR_V1 project=desktop check=schedule-grid-keyboard page=schedule type=error count=1\n",
            _page_error_detail_row(
                check="schedule-grid-keyboard",
                page="schedule",
                source="map-worker",
                type="error",
                count="1",
            ),
        ),
        (
            "UE_LIVE_PAGE_ERROR_V1 project=desktop check=map-gesture page=map type=error count=1\n",
            _page_error_detail_row(
                source="unknown", line="1", column="0", type="error", count="1"
            ),
        ),
        (
            "UE_LIVE_PAGE_ERROR_V1 project=desktop check=map-gesture page=map type=error count=1\n",
            _page_error_detail_row(
                source="unknown", line="0", column="1", type="error", count="1"
            ),
        ),
        (
            "UE_LIVE_PAGE_ERROR_V1 project=desktop check=map-gesture page=map type=error count=1\n",
            _page_error_detail_row(line="0", column="0", type="error", count="1"),
        ),
        (
            "UE_LIVE_PAGE_ERROR_V1 project=desktop check=map-gesture page=map type=error count=1\n",
            _page_error_detail_row(
                source="remote-script?query=fixture", type="error", count="1"
            ),
        ),
        (
            "UE_LIVE_PAGE_ERROR_V1 project=desktop check=map-gesture page=map type=error count=1\n",
            _page_error_detail_row(line="1000000", type="error", count="1"),
        ),
        (
            "UE_LIVE_PAGE_ERROR_V1 project=desktop check=map-gesture page=map type=error count=1\n",
            _page_error_detail_row(column="1000000", type="error", count="1"),
        ),
        (
            "UE_LIVE_PAGE_ERROR_V1 project=desktop check=map-gesture page=map type=error count=1\n",
            _page_error_detail_row(count="1000", type="error"),
        ),
        (
            "UE_LIVE_PAGE_ERROR_V1 project=desktop check=map-gesture page=map type=error count=2\n",
            _page_error_detail_row(type="error", count="1"),
        ),
    ],
)
def test_live_playwright_page_error_details_reject_invalid_pair_or_summary(
    summary: str, detail: str
) -> None:
    assert live_stand._live_playwright_page_error_details(summary + detail) == []


def test_live_playwright_page_error_details_require_summary_and_bound_records() -> None:
    detail = _page_error_detail_row()
    assert live_stand._live_playwright_page_error_details(detail) == []
    summary = (
        "UE_LIVE_PAGE_ERROR_V1 project=desktop check=map-gesture page=map "
        "type=type-error count=2\n"
    )
    records = "".join(_page_error_detail_row(line=str(line)) for line in range(1, 158))
    parsed = live_stand._live_playwright_page_error_details(summary + records + records)
    assert len(parsed) == 156
    assert parsed[0] == (
        "desktop",
        "map-gesture",
        "map",
        "type-error",
        "map-worker",
        1,
        4,
        2,
    )
    assert parsed[-1] == (
        "desktop",
        "map-gesture",
        "map",
        "type-error",
        "map-worker",
        156,
        4,
        2,
    )


def test_live_playwright_page_errors_reject_mobile_schedule_project() -> None:
    row = (
        "UE_LIVE_PAGE_ERROR_V1 project=mobile check=schedule-grid-keyboard "
        "page=schedule type=error count=1\n"
    )
    assert live_stand._live_playwright_page_errors(row) == []


@pytest.mark.parametrize(
    ("check", "page", "kind"),
    [
        ("password-reset", "admin-notifications", "error"),
        ("password-reset", "admin-users", "error"),
        ("password-reset", "admin-feature-flags", "error"),
        ("password-reset", "login", "react-418"),
        ("admin-notifications", "register", "error"),
        ("admin-notifications", "forgot-password", "error"),
        ("admin-notifications", "reset-password", "error"),
        ("admin-notifications", "admin-users", "error"),
        ("admin-notifications", "admin-feature-flags", "error"),
        ("auth-roles", "register", "error"),
        ("auth-roles", "forgot-password", "error"),
        ("auth-roles", "reset-password", "error"),
        ("auth-roles", "admin-notifications", "error"),
        ("map-gesture", "admin-users", "error"),
        ("map-gesture", "reset-password", "error"),
        ("schedule-grid-keyboard", "map", "error"),
        ("schedule-grid-keyboard", "admin-users", "error"),
    ],
)
def test_live_playwright_page_errors_reject_cross_scenario_domains(
    check: str, page: str, kind: str
) -> None:
    sentinel = (
        f"UE_LIVE_PAGE_ERROR_V1 project=desktop check={check} "
        f"page={page} type={kind} count=1\n"
    )
    assert live_stand._live_playwright_page_errors(sentinel) == []


@pytest.mark.parametrize(
    "replacement",
    [
        ("project=desktop", "project=private-project"),
        ("check=password-reset", "check=private-check"),
        ("page=reset-password", "page=private-token"),
        ("page=reset-password", "page=/reset-password"),
        ("type=error", "type=Error"),
        ("type=error", "type=private-token"),
        ("count=1", "count=0"),
        ("count=1", "count=1000"),
        ("count=1", "count=-1"),
        ("count=1", "count=01"),
        ("count=1", "count=1.0"),
        ("count=1", "count=１"),
        ("count=1", "count=" + "9" * 5000),
        ("count=1", "count=1 private-token"),
        ("count=1", "count=1 "),
        ("V1", "V2"),
        ("\n", ""),
        ("\n", "\r\r\n"),
        ("\n", "\x00\n"),
        ("\n", "\x1b[0m\n"),
        ("\n", "\u202e\n"),
        ("UE_LIVE", " UE_LIVE"),
        ("UE_LIVE", "title UE_LIVE"),
        ("UE_LIVE", "private\rUE_LIVE"),
        ("UE_LIVE", "private\vUE_LIVE"),
        ("UE_LIVE", "private\u0085UE_LIVE"),
        ("UE_LIVE", "private\u2028UE_LIVE"),
    ],
)
def test_live_playwright_page_errors_reject_malformed_records(
    replacement: tuple[str, str],
) -> None:
    sentinel = "UE_LIVE_PAGE_ERROR_V1 project=desktop check=password-reset page=reset-password type=error count=1\n"
    assert live_stand._live_playwright_page_errors(sentinel.replace(*replacement)) == []


def test_live_playwright_page_errors_deduplicate_and_bound_records() -> None:
    output = "".join(
        f"UE_LIVE_PAGE_ERROR_V1 project=desktop check=password-reset page=reset-password type=other count={count}\n"
        * 10
        for count in range(1, 1000)
    )
    assert live_stand._live_playwright_page_errors(output) == [
        ("desktop", "password-reset", "reset-password", "other", count)
        for count in range(1, 535)
    ]


@pytest.mark.parametrize("return_code", [0, 1, 23])
def test_live_playwright_emits_only_bounded_page_error_counts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    return_code: int,
) -> None:
    sentinel = "UE_LIVE_PAGE_ERROR_V1 project=desktop check=password-reset page=reset-password type=type-error count=2\n"
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"),
        return_code,
        stdout=(
            "private-title https://private.invalid/?token=private-token\n"
            + sentinel * 30
            + (
                "UE_LIVE_PAGE_ERROR_V1 project=desktop check=auth-roles "
                "page=admin-users type=react-418 count=1\n"
            )
            + "UE_LIVE_PAGE_ERROR_V1 project=mobile check=password-reset page=reset-password type=other count=999\r\n"
            + "UE_LIVE_PAGE_ERROR_V1 project=mobile check=password-reset page=reset-password type=error count="
        ).encode(),
        stderr=(
            b"1\n"
            b"UE_LIVE_PAGE_ERROR_V1 project=desktop check=password-reset page=reset-password type=error count=1\n"
            b"private-name private-message private-stack private-code private-browser-state\n"
        ),
    )
    monkeypatch.setattr(live_stand.subprocess, "run", lambda *_args, **_kw: completed)
    if return_code:
        with pytest.raises(live_stand.StandError, match=f"exit code {return_code}"):
            live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    else:
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    printed = capsys.readouterr()
    outcome = "failed" if return_code else "passed"
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E page error project=desktop check=password-reset page=reset-password type=type-error count=2",
        "live E2E page error project=desktop check=auth-roles page=admin-users type=react-418 count=1",
        "live E2E page error project=mobile check=password-reset page=reset-password type=other count=999",
        f"live E2E outcome={outcome} exit_code={return_code}",
    ]
    assert printed.err == ""
    assert completed.stdout == completed.stderr == b""


def test_live_playwright_emits_only_bounded_news_and_page_error_details(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    news = _news_viewport_row()
    summary = (
        "UE_LIVE_PAGE_ERROR_V1 project=desktop check=map-gesture page=map "
        "type=type-error count=2\n"
    )
    detail = _page_error_detail_row()
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"),
        0,
        stdout=(
            news + summary + detail + "private text https://private.invalid/path\n"
        ).encode(),
        stderr=(
            _news_viewport_row(project="mobile", language="en", width="1440")
            + "UE_LIVE_PAGE_ERROR_V1 project=desktop check=schedule-grid-keyboard "
            "page=schedule type=reference-error count=1\n"
            + _page_error_detail_row(
                project="desktop",
                check="schedule-grid-keyboard",
                page="schedule",
                type="reference-error",
                source="schedule-bundle",
                line="211",
                column="9",
                count="1",
            )
            + "private stderr diagnostic\n"
        ).encode(),
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")

    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E news viewport project=desktop language=ru width=390 "
        "viewportHeight=900 scrollY=-12 top=-4 bottom=22 left=0 right=390",
        "live E2E page error project=desktop check=map-gesture page=map "
        "type=type-error count=2",
        "live E2E page error detail project=desktop check=map-gesture page=map "
        "type=type-error source=map-worker line=17 column=4 count=2",
        "live E2E outcome=passed exit_code=0",
    ]
    assert "private" not in printed.out + printed.err
    assert printed.err == ""
    assert completed.stdout == completed.stderr == b""


def test_live_playwright_preserves_control_characters_before_diagnostic_validation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    run = subprocess.run
    child_source = (
        "import sys; "
        "sys.stdout.buffer.write("
        "b'private\\rUE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=401\\n'"
        "+ b'UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=403\\r'"
        "+ b'UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=500\\n'"
        "+ b'UE_LIVE_HTTP_STATUS_V1 project=mobile check=admin-feature-flags status=503\\r\\n'"
        "+ b'private\\rUE_LIVE_PAGE_ERROR_V1 project=desktop check=password-reset page=login type=error count=2\\n'"
        "+ b'UE_LIVE_PAGE_ERROR_V1 project=mobile check=password-reset page=reset-password type=type-error count=1\\r\\n'"
        "+ b'UE_LIVE_PROFILE_SAVE_V1 project=mobile status=422 detail=array detail_count=1 detail_msg=true alert_count=0 save_disabled=false route=profile page_error_count=0 page_error=none\\r\\n')"
    )

    def run_actual_child(
        _command: Sequence[str], **kwargs: Any
    ) -> subprocess.CompletedProcess:
        return run((sys.executable, "-c", child_source), **kwargs)

    monkeypatch.setattr(live_stand.subprocess, "run", run_actual_child)
    live_stand._run_live_playwright(
        cwd=tmp_path, environment=dict(os.environ), mode="smoke"
    )
    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E HTTP project=mobile check=admin-feature-flags status=503",
        "live E2E page error project=mobile check=password-reset page=reset-password type=type-error count=1",
        "live E2E outcome=passed exit_code=0",
    ]
    assert printed.err == ""


@pytest.mark.parametrize("return_code", [0, 1, 23])
@pytest.mark.parametrize("path_style", ["posix", "windows", "absolute"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_live_playwright_emits_only_validated_failure_locations(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    return_code: int,
    path_style: str,
    newline: str,
) -> None:
    sources = (*live_stand.LIVE_E2E_SMOKE_FILES, "tests/e2e-live/fixtures.ts")
    for filename in sources:
        source = tmp_path / filename
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("// public source\n" * 3, encoding="utf-8")
    private_title = "password=fixture-private-password token=fixture-private-token"
    frame_sources = [
        str(tmp_path / source) if path_style == "absolute" else source
        for source in sources
    ]
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"),
        return_code,
        stdout=(
            "  1) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:2:1 › "
            f"{private_title} ─────\n"
            "\n    Error: fixture-private-assertion\n\n"
            f"        at fixturePrivateFunction ({frame_sources[0]}:3:1)\n"
            f"        at {frame_sources[0]}:2:1\n"
            "  2) [mobile] › tests/e2e-live/password-reset.live.spec.ts:3:17 › "
            "https://private.invalid/reset?token=fixture-private-token ─────\n"
            "\n    Error: fixture-private-error\n\n"
            f"        at {frame_sources[1]}:1:17\n"
            f"        at privateHelper ({frame_sources[-1]}:2:17)\n"
            f"        at {frame_sources[-1]}:3:1\n"
            "6 passed\n12 failed\n2 skipped\n1 flaky\n3 interrupted\n4 did not run\n"
        ),
        stderr=(
            "  1) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:2:1 › "
            f"{private_title}\n"
            "Error: locator.fill('fixture-private-password')\n"
            f"        at {frame_sources[0]}:1:1\n"
        ),
    )
    if path_style == "windows":
        for source in sources:
            completed.stdout = completed.stdout.replace(
                source, source.replace("/", "\\")
            )
            completed.stderr = completed.stderr.replace(
                source, source.replace("/", "\\")
            )
    completed.stdout = completed.stdout.replace("\n", newline).encode()
    completed.stderr = completed.stderr.replace("\n", newline).encode()
    monkeypatch.setattr(live_stand.subprocess, "run", lambda *_args, **_kw: completed)
    if return_code:
        with pytest.raises(live_stand.StandError, match=f"exit code {return_code}"):
            live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    else:
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")

    printed = capsys.readouterr()
    outcome = "failed" if return_code else "passed"
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E counts passed=6 failed=12 skipped=2 flaky=1 interrupted=3 did_not_run=4",
        "live E2E failure project=desktop source=tests/e2e-live/auth-roles.live.spec.ts line=2 kind=declaration",
        "live E2E failure project=desktop source=tests/e2e-live/auth-roles.live.spec.ts line=3 kind=frame",
        "live E2E failure project=desktop source=tests/e2e-live/auth-roles.live.spec.ts line=2 kind=frame",
        "live E2E failure project=mobile source=tests/e2e-live/password-reset.live.spec.ts line=3 kind=declaration",
        "live E2E failure project=mobile source=tests/e2e-live/password-reset.live.spec.ts line=1 kind=frame",
        "live E2E failure project=mobile source=tests/e2e-live/fixtures.ts line=2 kind=frame",
        "live E2E failure project=mobile source=tests/e2e-live/fixtures.ts line=3 kind=frame",
        "live E2E diagnostic project=desktop source=tests/e2e-live/auth-roles.live.spec.ts line=2 category=unknown matcher=none locator=none",
        "live E2E diagnostic project=mobile source=tests/e2e-live/password-reset.live.spec.ts line=3 category=unknown matcher=none locator=none",
        "live E2E diagnostic project=desktop source=tests/e2e-live/auth-roles.live.spec.ts line=2 category=unknown matcher=none locator=none",
        f"live E2E outcome={outcome} exit_code={return_code}",
    ]
    assert printed.err == ""
    assert completed.stdout == completed.stderr == b""


def test_live_playwright_failure_source_allowlist_matches_tracked_full_suite(
    git_executable: str,
) -> None:
    tracked = _tracked_frontend_live_files(git_executable, working_directory=ROOT)
    tracked_sources = tuple(
        path.removeprefix("frontend/")
        for path in tracked
        if path.startswith("frontend/tests/e2e-live/")
        and path.endswith(".live.spec.ts")
    )
    expected_sources = {source: source for source in tracked_sources}
    expected_sources.update(
        {source.replace("/", "\\"): source for source in tracked_sources}
    )
    expected_frame_sources = {
        **expected_sources,
        "tests/e2e-live/fixtures.ts": "tests/e2e-live/fixtures.ts",
        r"tests\e2e-live\fixtures.ts": "tests/e2e-live/fixtures.ts",
    }

    assert tracked_sources
    assert len(live_stand._PLAYWRIGHT_FAILURE_DECLARATION_SOURCES) == len(
        tracked_sources
    )
    assert len(set(live_stand._PLAYWRIGHT_FAILURE_DECLARATION_SOURCES)) == len(
        tracked_sources
    )
    assert live_stand._PLAYWRIGHT_FAILURE_SOURCES == expected_sources
    assert live_stand._PLAYWRIGHT_FAILURE_FRAME_SOURCES == expected_frame_sources


def test_frontend_live_source_inventory_uses_git_root_from_mutants_copy(
    git_executable: str, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    mutants_root = repository / "mutants"
    mutants_root.mkdir(parents=True)
    tracked_sources = (
        "frontend/tests/e2e-live/auth-roles.live.spec.ts",
        "frontend/tests/e2e-live/password-reset.live.spec.ts",
    )
    for source in tracked_sources:
        path = repository / source
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// isolated tracked fixture\n", encoding="utf-8")
    _initialize_git_repository(git_executable, repository)
    subprocess.run(  # noqa: S603 - validated Git executable and fixed argv
        [git_executable, "add", "--", *tracked_sources],
        cwd=repository,
        check=True,
        capture_output=True,
    )

    assert _tracked_frontend_live_files(
        git_executable, working_directory=mutants_root
    ) == list(tracked_sources)


def test_live_playwright_emits_non_smoke_failure_locations_and_redacts_details(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    source_name = "tests/e2e-live/activity-dashboard.live.spec.ts"
    source_path = tmp_path / source_name
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "// public source\nexport const dashboard = true;\n// source frame\n",
        encoding="utf-8",
    )
    fixture_name = "tests/e2e-live/fixtures.ts"
    fixture_path = tmp_path / fixture_name
    fixture_path.write_text(
        "// public fixture\nexport function fixtureHelper() {}\n",
        encoding="utf-8",
    )
    private_details = "private title and assertion sentinel"
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(),
        1,
        stdout=(
            f"  1) [desktop] › {source_name}:2:1 › {private_details}\n"
            f"\n    Error: {private_details}\n\n"
            f"        at sourceHelper ({source_path}:3:1)\n"
            f"        at fixtureHelper ({fixture_path}:2:1)\n"
            "1 failed\n"
        ).encode(),
        stderr=b"",
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )

    with pytest.raises(live_stand.StandError, match="exit code 1"):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="full")

    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command()),
        "live E2E counts failed=1",
        "live E2E failure project=desktop source=tests/e2e-live/activity-dashboard.live.spec.ts line=2 kind=declaration",
        "live E2E failure project=desktop source=tests/e2e-live/activity-dashboard.live.spec.ts line=3 kind=frame",
        "live E2E failure project=desktop source=tests/e2e-live/fixtures.ts line=2 kind=frame",
        "live E2E diagnostic project=desktop source=tests/e2e-live/activity-dashboard.live.spec.ts line=2 category=unknown matcher=none locator=none",
        "live E2E outcome=failed exit_code=1",
    ]
    assert private_details not in printed.out + printed.err
    assert printed.err == ""
    assert completed.stdout == completed.stderr == b""


def test_live_playwright_emits_fixed_failure_categories_without_reporter_values(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    marker = f"case_marker_{uuid4().hex}"
    source_name = "tests/e2e-live/activity-dashboard.live.spec.ts"
    source_path = tmp_path / source_name
    source_path.parent.mkdir(parents=True)
    source_path.write_text("// public source\n" * 12, encoding="utf-8")
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(),
        1,
        stdout=(
            f"  1) [desktop] › {source_name}:1:1 › title-{marker}\n"
            "\n"
            "    Error: expect(locator).toBeVisible() failed\n"
            "    Expected: visible\n"
            f"    Received: expected-{marker} getByText('{marker}')\n"
            "    Call log:\n"
            f"      - waiting for getByRole('button', {{name: '{marker}'}})\n"
            f"  2) [mobile] › {source_name}:2:1 › second-title-{marker}\n"
            "\n"
            "    Error: locator.fill: Timeout 5000ms exceeded.\n"
            "    Call log:\n"
            f"      - waiting for getByLabel('{marker}')\n"
            f"  3) [desktop] › {source_name}:3:1 › third-title-{marker}\n"
            "\n"
            "    Error: expect(received).not.toBe(expected)\n"
            f"    Expected: not expected-{marker}\n"
            f"    Received: received-{marker}\n"
            f"  4) [desktop] › {source_name}:4:1 › timeout-title-{marker}\n"
            "\n"
            "    Test timeout of 20000ms exceeded.\n"
            f"  5) [mobile] › {source_name}:5:1 › fixture-setup-title-{marker}\n"
            "\n"
            f'    Test timeout of 30000ms exceeded while setting up "fixture-{marker}".\n'
            f"  6) [desktop] › {source_name}:6:1 › fixture-teardown-title-{marker}\n"
            "\n"
            f'    Tearing down "fixture-{marker}" exceeded the test timeout of 30000ms.\n'
            f"  7) [mobile] › {source_name}:7:1 › hook-title-{marker}\n"
            "\n"
            '    Test timeout of 30000ms exceeded while running "beforeEach" hook.\n'
            f"  8) [desktop] › {source_name}:8:1 › before-all-title-{marker}\n"
            "\n"
            '    "beforeAll" hook timeout of 30000ms exceeded.\n'
            f"  9) [mobile] › {source_name}:9:1 › worker-teardown-title-{marker}\n"
            "\n"
            f'    Worker teardown timeout of 30000ms exceeded while tearing down "fixture-{marker}".\n'
            f"  10) [desktop] › {source_name}:10:1 › modifier-title-{marker}\n"
            "\n"
            '    "fixme" modifier timeout of 30000ms exceeded.\n'
            f"  11) [mobile] › {source_name}:11:1 › fixture-slot-title-{marker}\n"
            "\n"
            f'    Fixture "fixture-{marker}" timeout of 30000ms exceeded during setup.\n'
            f"  12) [desktop] › {source_name}:12:1 › runtime-title-{marker}\n"
            "\n"
            f"    TypeError: runtime-{marker}\n"
            "12 failed\n"
        ).encode(),
        # A reporter error without a header in this stream must not inherit
        # the stdout failure's project or source.
        stderr=(
            b"    Error: expect(locator).toHaveText() failed\n"
            + f"    Received: {marker}\n".encode()
        ),
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )

    with pytest.raises(live_stand.StandError, match="exit code 1"):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="full")

    printed = capsys.readouterr()
    assert "live E2E counts failed=12" in printed.out.splitlines()
    assert [line for line in printed.out.splitlines() if "diagnostic" in line] == [
        "live E2E diagnostic project=desktop source=tests/e2e-live/activity-dashboard.live.spec.ts line=1 category=assertion matcher=toBeVisible locator=role",
        "live E2E diagnostic project=mobile source=tests/e2e-live/activity-dashboard.live.spec.ts line=2 category=timeout matcher=none locator=label",
        "live E2E diagnostic project=desktop source=tests/e2e-live/activity-dashboard.live.spec.ts line=3 category=assertion matcher=not.toBe locator=none",
        "live E2E diagnostic project=desktop source=tests/e2e-live/activity-dashboard.live.spec.ts line=4 category=timeout matcher=none locator=none",
        "live E2E diagnostic project=mobile source=tests/e2e-live/activity-dashboard.live.spec.ts line=5 category=timeout matcher=none locator=none",
        "live E2E diagnostic project=desktop source=tests/e2e-live/activity-dashboard.live.spec.ts line=6 category=timeout matcher=none locator=none",
        "live E2E diagnostic project=mobile source=tests/e2e-live/activity-dashboard.live.spec.ts line=7 category=timeout matcher=none locator=none",
        "live E2E diagnostic project=desktop source=tests/e2e-live/activity-dashboard.live.spec.ts line=8 category=timeout matcher=none locator=none",
        "live E2E diagnostic project=mobile source=tests/e2e-live/activity-dashboard.live.spec.ts line=9 category=timeout matcher=none locator=none",
        "live E2E diagnostic project=desktop source=tests/e2e-live/activity-dashboard.live.spec.ts line=10 category=timeout matcher=none locator=none",
        "live E2E diagnostic project=mobile source=tests/e2e-live/activity-dashboard.live.spec.ts line=11 category=timeout matcher=none locator=none",
        "live E2E diagnostic project=desktop source=tests/e2e-live/activity-dashboard.live.spec.ts line=12 category=runtime matcher=none locator=none",
    ]
    assert marker not in printed.out + printed.err
    assert printed.err == ""
    assert completed.stdout == completed.stderr == b""


def test_live_playwright_failure_diagnostics_reset_after_controls_and_oversize_lines(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    marker = f"case_marker_{uuid4().hex}"
    source_name = "tests/e2e-live/activity-dashboard.live.spec.ts"
    source_path = tmp_path / source_name
    source_path.parent.mkdir(parents=True)
    source_path.write_text("// public source\n// public source\n", encoding="utf-8")
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(),
        1,
        stdout=(
            f"  1) [desktop] › {source_name}:1:1 › title-{marker}\n"
            "\x1b[31m Error: expect(locator).toBeVisible() failed\n"
            f"    Error: expect(locator).toBeVisible() failed {marker}\n"
            f"  2) [mobile] › {source_name}:2:1 › second-title-{marker}\n"
            + ("x" * 4097)
            + "\n"
            f"    Error: locator.click: Timeout 5000ms exceeded {marker}\n"
            f"  3) [unknown-project] › tests/e2e-live/unknown.live.spec.ts:1:1 › invalid-{marker}\n"
            f"    Error: expect(locator).toBeVisible() failed {marker}\n"
            "3 failed\n"
        ).encode(),
        stderr=b"",
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )

    with pytest.raises(live_stand.StandError, match="exit code 1"):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="full")

    printed = capsys.readouterr()
    assert [line for line in printed.out.splitlines() if "diagnostic" in line] == [
        "live E2E diagnostic project=desktop source=tests/e2e-live/activity-dashboard.live.spec.ts line=1 category=unknown matcher=none locator=none",
        "live E2E diagnostic project=mobile source=tests/e2e-live/activity-dashboard.live.spec.ts line=2 category=unknown matcher=none locator=none",
    ]
    assert marker not in printed.out + printed.err
    assert printed.err == ""
    assert completed.stdout == completed.stderr == b""


def test_live_playwright_classifies_pinned_wait_for_response_timeout(
    tmp_path: Path,
) -> None:
    source_name = "tests/e2e-live/totp-recovery.live.spec.ts"
    source_path = tmp_path / source_name
    source_path.parent.mkdir(parents=True)
    source_path.write_text("// public source\n", encoding="utf-8")
    output = (
        f"  1) [desktop] › {source_name}:1:1 › waits for auth response\n\n"
        '    Error: page.waitForResponse: Timeout 30000ms exceeded while waiting for event "response"\n'
    )

    assert live_stand._live_playwright_failure_diagnostics(output, cwd=tmp_path) == [
        ("desktop", source_name, 1, "timeout", "none", "none")
    ]


@pytest.mark.parametrize(
    ("timeout_line", "expected"),
    [
        (
            '    Error: page.waitForResponse: Timeout 30000ms exceeded while waiting for event "request"\n',
            "unknown",
        ),
        (
            '    Error: page.waitForRequest: Timeout 30000ms exceeded while waiting for event "response"\n',
            "unknown",
        ),
        (
            '    Error: page.waitForResponse: Timeout 30000ms exceeded while waiting for event "response" private\n',
            "unknown",
        ),
        (
            '    Error: page.waitForResponse: Timeout 1000000ms exceeded while waiting for event "response"\n',
            "unknown",
        ),
        (
            '\x1b[31m    Error: page.waitForResponse: Timeout 30000ms exceeded while waiting for event "response"\x1b[0m\n',
            "unknown",
        ),
        (
            '    Error: page.waitForResponse: Timeout 30000ms exceeded while waiting for event "response"\x00\n',
            None,
        ),
    ],
)
def test_live_playwright_wait_for_response_timeout_classifier_fails_closed(
    tmp_path: Path,
    timeout_line: str,
    expected: str | None,
) -> None:
    source_name = "tests/e2e-live/totp-recovery.live.spec.ts"
    source_path = tmp_path / source_name
    source_path.parent.mkdir(parents=True)
    source_path.write_text("// public source\n", encoding="utf-8")
    output = (
        f"  1) [desktop] › {source_name}:1:1 › waits for auth response\n\n"
        + timeout_line
        + "1 failed\n"
    )

    diagnostics = live_stand._live_playwright_failure_diagnostics(output, cwd=tmp_path)
    if expected is None:
        assert diagnostics == []
    else:
        assert diagnostics == [("desktop", source_name, 1, expected, "none", "none")]


@pytest.mark.parametrize(
    "frame",
    [
        "        at tests/e2e-live/unknown.live.spec.ts:2:1",
        "        at /private/tests/e2e-live/auth-roles.live.spec.ts:2:1",
        r"        at C:\private\tests\e2e-live\auth-roles.live.spec.ts:2:1",
        "        at ../tests/e2e-live/auth-roles.live.spec.ts:2:1",
        "        at {cwd}/../tests/e2e-live/auth-roles.live.spec.ts:2:1",
        "        at {cwd}/tests/e2e-live/../e2e-live/auth-roles.live.spec.ts:2:1",
        "        at file://{cwd}/tests/e2e-live/auth-roles.live.spec.ts:2:1",
        "        at https://private.invalid/tests/e2e-live/auth-roles.live.spec.ts:2:1",
        r"        at tests/e2e-live\auth-roles.live.spec.ts:2:1",
        "        at auth-roles.live.spec.ts:2:1",
        "        at tests/e2e-live/auth-roles.live.spec.ts:0:1",
        "        at tests/e2e-live/auth-roles.live.spec.ts:4:1",
        "        at tests/e2e-live/auth-roles.live.spec.ts:02:1",
        "        at tests/e2e-live/auth-roles.live.spec.ts:2:0",
        "        at tests/e2e-live/auth-roles.live.spec.ts:2:18",
        "        at tests/e2e-live/auth-roles.live.spec.ts:2:01",
        "        at tests/e2e-live/auth-roles.live.spec.ts:2:1secret",
        "        at tests/e2e-live/auth-roles.live.spec.ts:2:1?private-token",
        "        at (tests/e2e-live/auth-roles.live.spec.ts:2:1)",
        "        at function (tests/e2e-live/auth-roles.live.spec.ts:2:1",
        "        at tests/e2e-live/auth-roles.live.spec.ts:2:1)",
        "        at function ((tests/e2e-live/auth-roles.live.spec.ts:2:1))",
        "        at function (tests/e2e-live/auth-roles.live.spec.ts:2:1) private",
        "        at " + "x" * 257 + " (tests/e2e-live/auth-roles.live.spec.ts:2:1)",
        "        at tests/e2e-live/auth-roles.live.spec.ts:2:1\x1b[31m",
        "        at tests/e2e-live/auth-roles.live.spec.ts:2:1\rprivate",
        "        at tests/e2e-live/auth-roles.live.spec.ts:2:1\x00private",
        "        at tests/e2e-live/auth-roles.live.spec.ts:2:1\u202eprivate",
        "        at tests/e2e-live/auth-roles.live.spec.ts:2:1\v"
        "        at tests/e2e-live/auth-roles.live.spec.ts:3:1",
        "        at " + "x" * 4096 + "/tests/e2e-live/auth-roles.live.spec.ts:2:1",
        "        at tests/e2e-live/auth-roles.live.spec.ts:" + "9" * 5000 + ":1",
        "        at tests/e2e-live/auth-roles.live.spec.ts:2:" + "9" * 5000,
        "       at tests/e2e-live/auth-roles.live.spec.ts:2:1",
    ],
    ids=[
        "unknown-source",
        "foreign-absolute",
        "foreign-windows-absolute",
        "relative-parent",
        "absolute-parent",
        "absolute-normalization",
        "file-url",
        "https-url",
        "mixed-separators",
        "basename",
        "zero-line",
        "line-past-end",
        "leading-zero-line",
        "zero-column",
        "column-past-end",
        "leading-zero-column",
        "malformed-column",
        "query",
        "missing-function",
        "unclosed-wrapper",
        "unopened-wrapper",
        "nested-wrapper",
        "trailing-text",
        "oversized-function",
        "ansi",
        "carriage-return",
        "nul",
        "bidi",
        "control-forged-frame",
        "oversized-path",
        "oversized-line",
        "oversized-column",
        "wrong-indentation",
    ],
)
@pytest.mark.parametrize(
    "frame_source",
    ["tests/e2e-live/auth-roles.live.spec.ts", "tests/e2e-live/fixtures.ts"],
)
def test_live_playwright_rejects_untrusted_failure_frames(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    frame: str,
    frame_source: str,
) -> None:
    source_name = live_stand.LIVE_E2E_SMOKE_FILES[0]
    source = tmp_path / source_name
    source.parent.mkdir(parents=True)
    source.write_text("// public source\n" * 3, encoding="utf-8")
    (tmp_path / frame_source).write_text("// public source\n" * 3, encoding="utf-8")
    output = f"  1) [desktop] › {source_name}:1:1 › private-title\n\n"
    output += frame.replace("{cwd}", str(tmp_path)).replace(
        "auth-roles.live.spec.ts", Path(frame_source).name
    )
    assert live_stand._live_playwright_failure_locations(output, cwd=tmp_path) == [
        ("desktop", source_name, 1, "declaration")
    ]
    printed = capsys.readouterr()
    assert printed.out == printed.err == ""


@pytest.mark.parametrize(
    "boundary",
    [
        "  2) [unknown] › tests/e2e-live/auth-roles.live.spec.ts:1:1 › private",
        "  2) [mobile] › tests/e2e-live/unknown.live.spec.ts:1:1 › private",
        "  2) [mobile] › tests/e2e-live/fixtures.ts:1:1 › private",
        "  2) [mobile] › tests/e2e-live/auth-roles.live.spec.ts:4:1 › private",
        "  2) [mobile] › tests/e2e-live/auth-roles.live.spec.ts:1:18 › private",
        "  2) [mobile] › tests/e2e-live/auth-roles.live.spec.ts:1:1",
        "  2) [mobile] › tests/e2e-live/auth-roles.live.spec.ts:1:1 › private\x1b[31m",
        "  2) [mobile] › tests/e2e-live/auth-roles.live.spec.ts:1:1 › " + "x" * 4096,
        "  2 failed",
        "Error: unscoped private error",
    ],
    ids=[
        "unknown-project",
        "unknown-source",
        "fixture-declaration",
        "invalid-line",
        "invalid-column",
        "malformed-header",
        "control-header",
        "oversized-header",
        "summary",
        "unscoped-error",
    ],
)
@pytest.mark.parametrize(
    "frame_source",
    ["tests/e2e-live/auth-roles.live.spec.ts", "tests/e2e-live/fixtures.ts"],
)
def test_live_playwright_frames_do_not_reuse_an_earlier_failure_project(
    tmp_path: Path, boundary: str, frame_source: str
) -> None:
    source_name = live_stand.LIVE_E2E_SMOKE_FILES[0]
    source = tmp_path / source_name
    source.parent.mkdir(parents=True)
    source.write_text("// public source\n" * 3, encoding="utf-8")
    frame_path = tmp_path / frame_source
    frame_path.write_text("// public source\n" * 3, encoding="utf-8")
    output = (
        f"  1) [desktop] › {source_name}:1:1 › private-title\n"
        f"{boundary}\n        at {frame_path}:2:1\n"
    )
    assert live_stand._live_playwright_failure_locations(output, cwd=tmp_path) == [
        ("desktop", source_name, 1, "declaration")
    ]
    assert (
        live_stand._live_playwright_failure_locations(
            f"        at {frame_path}:2:1", cwd=tmp_path
        )
        == []
    )


@pytest.mark.parametrize(
    "frame_source",
    ["tests/e2e-live/auth-roles.live.spec.ts", "tests/e2e-live/fixtures.ts"],
)
def test_live_playwright_failure_frames_require_a_header_in_the_same_stream(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    frame_source: str,
) -> None:
    source_name = live_stand.LIVE_E2E_SMOKE_FILES[0]
    source = tmp_path / source_name
    source.parent.mkdir(parents=True)
    source.write_text("// public source\n" * 3, encoding="utf-8")
    frame_path = tmp_path / frame_source
    frame_path.write_text("// public source\n" * 3, encoding="utf-8")
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(),
        23,
        stdout=f"  1) [desktop] › {source_name}:1:1 › private-title\n".encode(),
        stderr=f"        at {frame_path}:2:1\n1 failed\n".encode(),
    )
    monkeypatch.setattr(live_stand.subprocess, "run", lambda *_args, **_kw: completed)
    with pytest.raises(live_stand.StandError, match="exit code 23"):
        live_stand._run_live_playwright(cwd=tmp_path, environment={})
    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command()),
        "live E2E counts failed=1",
        f"live E2E failure project=desktop source={source_name} line=1 kind=declaration",
        f"live E2E diagnostic project=desktop source={source_name} line=1 category=unknown matcher=none locator=none",
        "live E2E outcome=failed exit_code=23",
    ]
    assert printed.err == ""
    assert completed.stdout == completed.stderr == b""


@pytest.mark.parametrize("source_state", ["missing", "invalid-utf8", "directory"])
@pytest.mark.parametrize(
    "frame_source",
    ["tests/e2e-live/password-reset.live.spec.ts", "tests/e2e-live/fixtures.ts"],
)
def test_live_playwright_failure_frames_fail_closed_without_source_bounds(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    source_state: str,
    frame_source: str,
) -> None:
    declaration = tmp_path / live_stand.LIVE_E2E_SMOKE_FILES[0]
    frame = tmp_path / frame_source
    declaration.parent.mkdir(parents=True)
    declaration.write_text("// public source\n", encoding="utf-8")
    if source_state == "invalid-utf8":
        frame.write_bytes(b"\xffprivate-source-sentinel")
    elif source_state == "directory":
        frame.mkdir()
    source_name = live_stand.LIVE_E2E_SMOKE_FILES[0]
    output = (
        f"  1) [mobile] › {source_name}:1:1 › private-title\n        at {frame}:1:1\n"
    )
    assert live_stand._live_playwright_failure_locations(output, cwd=tmp_path) == [
        ("mobile", source_name, 1, "declaration")
    ]
    printed = capsys.readouterr()
    assert printed.out == printed.err == ""


def test_live_playwright_frames_support_parentheses_in_the_exact_working_directory(
    tmp_path: Path,
) -> None:
    cwd = tmp_path / "public checkout (copy)"
    source_name = live_stand.LIVE_E2E_SMOKE_FILES[0]
    source = cwd / source_name
    source.parent.mkdir(parents=True)
    source.write_text("// public source\n" * 3, encoding="utf-8")
    output = (
        f"  1) [mobile] › {source_name}:1:1 › private-title\n"
        f"        at privateFunction ({source}:2:1)\n"
        f"        at {source}:3:1\n"
    )
    assert live_stand._live_playwright_failure_locations(output, cwd=cwd) == [
        ("mobile", source_name, 1, "declaration"),
        ("mobile", source_name, 2, "frame"),
        ("mobile", source_name, 3, "frame"),
    ]


@pytest.mark.parametrize(
    "header",
    [
        "  1) [secret-project] › tests/e2e-live/auth-roles.live.spec.ts:2:1 › title",
        "  1) [desktop] › tests/e2e-live/credential-shaped-token.live.spec.ts:2:1 › title",
        "  1) [desktop] › tests/e2e-live/fixtures.ts:2:1 › title",
        r"  1) [desktop] › tests\e2e-live\fixtures.ts:2:1 › title",
        "  1) [desktop] › ../tests/e2e-live/auth-roles.live.spec.ts:2:1 › title",
        "  1) [desktop] › /private/tests/e2e-live/auth-roles.live.spec.ts:2:1 › title",
        r"  1) [desktop] › ..\tests\e2e-live\auth-roles.live.spec.ts:2:1 › title",
        r"  1) [desktop] › C:\private\tests\e2e-live\auth-roles.live.spec.ts:2:1 › title",
        r"  1) [desktop] › tests\e2e-live\..\e2e-live\auth-roles.live.spec.ts:2:1 › title",
        r"  1) [desktop] › tests/e2e-live\auth-roles.live.spec.ts:2:1 › title",
        r"  1) [desktop] › tests\e2e-live\credential-shaped-token.live.spec.ts:2:1 › title",
        "  1) [desktop] › tests/e2e-live/../e2e-live/auth-roles.live.spec.ts:2:1 › title",
        "  1) [desktop] › auth-roles.live.spec.ts:2:1 › title",
        "  1) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:0:1 › title",
        "  1) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:4:1 › title",
        "  1) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:02:1 › title",
        "  1) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:2:0 › title",
        "  1) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:2:18 › title",
        "  1) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:2:01 › title",
        "  1) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:2:1secret › title",
        "  1) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:2:1 › title\x1b[31m",
        "  1) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:2:1 › title\rsecret",
        "  1) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:2:1 › title\x00secret",
        "  1) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:2:1 › title\u202esecret",
        "  1) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:2:1 › " + "x" * 4096,
        "  1) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:"
        + "9" * 5000
        + ":1 › title",
        "  1) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:2:"
        + "9" * 5000
        + " › title",
        "  0) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:2:1 › title",
        "  12345) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:2:1 › title",
        "  ✓ 1 [desktop] › tests/e2e-live/auth-roles.live.spec.ts:2:1 › title",
        "  1) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:2:1",
        "  1) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:2:1 › title\v"
        "  2) [mobile] › tests/e2e-live/auth-roles.live.spec.ts:2:1 › forged",
    ],
    ids=[
        "unknown-project",
        "unknown-source",
        "fixture-declaration",
        "windows-fixture-declaration",
        "parent-path",
        "absolute-path",
        "windows-parent-path",
        "windows-absolute-path",
        "windows-normalized-path",
        "mixed-path-separators",
        "windows-unknown-source",
        "normalized-path",
        "basename",
        "zero-line",
        "line-past-end",
        "leading-zero-line",
        "zero-column",
        "column-past-end",
        "leading-zero-column",
        "malformed-column",
        "ansi-control",
        "carriage-return",
        "nul-control",
        "bidi-control",
        "oversized-title",
        "oversized-line",
        "oversized-column",
        "zero-index",
        "oversized-index",
        "passing-result",
        "missing-separator",
        "control-forged-header",
    ],
)
def test_live_playwright_failure_locations_reject_untrusted_headers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], header: str
) -> None:
    source = tmp_path / live_stand.LIVE_E2E_SMOKE_FILES[0]
    source.parent.mkdir(parents=True)
    source.write_text("// public source\n" * 3, encoding="utf-8")
    (source.parent / "fixtures.ts").write_text(
        "// public source\n" * 3, encoding="utf-8"
    )
    assert live_stand._live_playwright_failure_locations(header, cwd=tmp_path) == []
    printed = capsys.readouterr()
    assert printed.out == printed.err == ""


@pytest.mark.parametrize("source_state", ["missing", "invalid-utf8", "directory"])
def test_live_playwright_failure_locations_fail_closed_without_source_bounds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], source_state: str
) -> None:
    source = tmp_path / live_stand.LIVE_E2E_SMOKE_FILES[0]
    source.parent.mkdir(parents=True)
    if source_state == "invalid-utf8":
        source.write_bytes(b"\xffprivate-source-sentinel")
    elif source_state == "directory":
        source.mkdir()
    header = (
        "  1) [desktop] › tests/e2e-live/auth-roles.live.spec.ts:1:1 › private-title"
    )
    assert live_stand._live_playwright_failure_locations(header, cwd=tmp_path) == []
    printed = capsys.readouterr()
    assert printed.out == printed.err == ""


def test_live_e2e_command_handles_windows_npm_shim_without_secret_interpolation() -> (
    None
):
    if live_stand._live_e2e_command(platform="posix") != (
        "npm",
        "run",
        "test:e2e:live",
    ):
        pytest.fail("Unix must launch npm directly")
    if live_stand._live_e2e_command(platform="nt") != (
        "cmd.exe",
        "/d",
        "/s",
        "/c",
        "npm run test:e2e:live",
    ):
        pytest.fail("Windows must use the static cmd.exe launcher for npm.cmd")


def test_live_e2e_focused_command_uses_only_canonical_reviewed_specs() -> None:
    sources = live_stand._PLAYWRIGHT_FAILURE_DECLARATION_SOURCES
    selected = (sources[-1], sources[0])
    canonical = (sources[0], sources[-1])

    assert live_stand._live_e2e_command(mode="full", platform="posix") == (
        live_stand.LIVE_E2E_COMMAND
    )
    assert live_stand._live_e2e_command(mode="smoke", platform="posix") == (
        *live_stand.LIVE_E2E_COMMAND,
        "--",
        *live_stand.LIVE_E2E_SMOKE_FILES,
    )
    assert live_stand._live_e2e_command(
        mode="full", platform="posix", specs=selected
    ) == (
        *live_stand.LIVE_E2E_COMMAND,
        "--",
        *canonical,
    )
    windows = live_stand.LIVE_E2E_WINDOWS_COMMAND
    assert live_stand._live_e2e_command(mode="full", platform="nt", specs=selected) == (
        *windows[:-1],
        f"{windows[-1]} -- {' '.join(canonical)}",
    )
    with pytest.raises(
        live_stand.StandError, match="invalid live E2E focused selection"
    ):
        live_stand._live_e2e_command(mode="smoke", specs=(sources[0],))
    with pytest.raises(
        live_stand.StandError, match="invalid live E2E focused selection"
    ):
        live_stand._live_e2e_command(mode="full", specs=(sources[0], sources[0]))
    with pytest.raises(
        live_stand.StandError, match="invalid live E2E focused selection"
    ):
        live_stand._live_e2e_command(
            mode="full", specs=("tests/e2e-live/../unlisted-spec",)
        )


@pytest.mark.parametrize(
    ("arguments", "rejected_value"),
    [
        (
            [
                "e2e",
                "--mode",
                "smoke",
                "--spec",
                "tests/e2e-live/auth-roles.live.spec.ts",
            ],
            "tests/e2e-live/auth-roles.live.spec.ts",
        ),
        (
            [
                "e2e",
                "--spec",
                "tests/e2e-live/auth-roles.live.spec.ts",
                "--spec",
                "tests/e2e-live/auth-roles.live.spec.ts",
            ],
            "tests/e2e-live/auth-roles.live.spec.ts",
        ),
        (
            ["e2e", "--spec", "tests/e2e-live/../unlisted-spec"],
            "unlisted-spec",
        ),
        (
            ["e2e", "--spec", "C:\\unlisted\\auth-roles.live.spec.ts"],
            "C:\\unlisted\\auth-roles.live.spec.ts",
        ),
        (
            ["e2e", "--spec", "tests\\e2e-live\\auth-roles.live.spec.ts"],
            "tests\\e2e-live\\auth-roles.live.spec.ts",
        ),
        (
            ["e2e", "--spec", "tests/e2e-live/*.live.spec.ts"],
            "tests/e2e-live/*.live.spec.ts",
        ),
        (
            ["e2e", "--spec", "tests/e2e-live/auth-roles.live.spec.ts\x1b"],
            "auth-roles.live.spec.ts\x1b",
        ),
        (
            ["e2e", "--spec", "tests/e2e-live/áuth-roles.live.spec.ts"],
            "áuth-roles.live.spec.ts",
        ),
    ],
)
def test_e2e_cli_rejects_unsafe_focus_before_state_or_seed_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
    rejected_value: str,
) -> None:
    side_effects: list[str] = []
    monkeypatch.setattr(
        live_stand,
        "_configure_state_mode",
        lambda _args: side_effects.append("state"),
    )
    monkeypatch.setattr(
        live_stand,
        "e2e",
        lambda *_args, **_kwargs: side_effects.append("e2e"),
    )

    assert live_stand.main(arguments) == 2

    captured = capsys.readouterr()
    assert captured.err == "live_stand: invalid live E2E focused selection\n"
    assert rejected_value not in captured.out + captured.err
    assert side_effects == []


def test_e2e_direct_call_rejects_focus_before_lock_or_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    side_effects: list[str] = []
    monkeypatch.setattr(
        live_stand,
        "stand_lifecycle_lock",
        lambda: side_effects.append("lock"),
    )
    monkeypatch.setattr(
        live_stand,
        "load_or_create_stand_admin_password",
        lambda *_args: side_effects.append("password"),
    )

    with pytest.raises(
        live_stand.StandError, match="invalid live E2E focused selection"
    ):
        live_stand.e2e("smoke", specs=("tests/e2e-live/auth-roles.live.spec.ts",))

    assert side_effects == []


def test_e2e_cli_propagates_valid_focus_in_canonical_order_before_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    side_effects: list[str] = []
    observed: list[tuple[str, tuple[str, ...]]] = []
    selected = (
        live_stand._PLAYWRIGHT_FAILURE_DECLARATION_SOURCES[-1],
        live_stand._PLAYWRIGHT_FAILURE_DECLARATION_SOURCES[0],
    )
    expected = (
        live_stand._PLAYWRIGHT_FAILURE_DECLARATION_SOURCES[0],
        live_stand._PLAYWRIGHT_FAILURE_DECLARATION_SOURCES[-1],
    )
    monkeypatch.setattr(
        live_stand,
        "_configure_state_mode",
        lambda _args: side_effects.append("state"),
    )
    monkeypatch.setattr(
        live_stand,
        "e2e",
        lambda mode, specs=(): observed.append((mode, tuple(specs))),
    )

    assert live_stand.main(["e2e", "--spec", selected[0], "--spec", selected[1]]) == 0

    assert side_effects == ["state"]
    assert observed == [("full", expected)]


def test_e2e_direct_call_propagates_valid_focus_before_password_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from contextlib import nullcontext

    observed: list[tuple[str, str, tuple[str, ...]]] = []
    selected = (
        live_stand._PLAYWRIGHT_FAILURE_DECLARATION_SOURCES[-1],
        live_stand._PLAYWRIGHT_FAILURE_DECLARATION_SOURCES[0],
    )
    expected = (
        live_stand._PLAYWRIGHT_FAILURE_DECLARATION_SOURCES[0],
        live_stand._PLAYWRIGHT_FAILURE_DECLARATION_SOURCES[-1],
    )
    password_marker = uuid4().hex
    monkeypatch.setattr(live_stand, "stand_lifecycle_lock", nullcontext)
    monkeypatch.setattr(live_stand, "load_stand_owner", lambda _path: object())
    monkeypatch.setattr(
        live_stand,
        "load_or_create_stand_admin_password",
        lambda _path, _owner: password_marker,
    )
    monkeypatch.setattr(
        live_stand,
        "_e2e_locked",
        lambda password, *, mode, specs=(): observed.append(
            (password, mode, tuple(specs))
        ),
    )

    live_stand.e2e("full", specs=selected)

    assert observed == [(password_marker, "full", expected)]


def test_live_playwright_focused_scope_is_fixed_and_diagnostic_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    selected = (
        live_stand._PLAYWRIGHT_FAILURE_DECLARATION_SOURCES[-1],
        live_stand._PLAYWRIGHT_FAILURE_DECLARATION_SOURCES[0],
    )
    expected = (
        live_stand._PLAYWRIGHT_FAILURE_DECLARATION_SOURCES[0],
        live_stand._PLAYWRIGHT_FAILURE_DECLARATION_SOURCES[-1],
    )
    expected_command = live_stand._live_e2e_command(mode="full", specs=expected)
    completed = subprocess.CompletedProcess((), 0, stdout=b"", stderr=b"")
    observed: list[tuple[str, ...]] = []

    def fake_run(command, **_kwargs):
        observed.append(tuple(command))
        completed.args = command
        return completed

    monkeypatch.setattr(live_stand.subprocess, "run", fake_run)

    live_stand._run_live_playwright(
        cwd=tmp_path, environment={}, mode="full", specs=selected
    )

    assert observed == [expected_command]
    assert capsys.readouterr().out.splitlines() == [
        "live E2E scope=focused diagnostic_only=true",
        "+ " + " ".join(expected_command),
        "live E2E outcome=passed exit_code=0",
    ]
    assert completed.stdout == completed.stderr == b""


@pytest.mark.parametrize(
    ("mode", "selected_files"),
    [
        ("full", ()),
        (
            "smoke",
            (
                "tests/e2e-live/auth-roles.live.spec.ts",
                "tests/e2e-live/password-reset.live.spec.ts",
                "tests/e2e-live/search-dialog-keyboard.live.spec.ts",
                "tests/e2e-live/settings-radio-focus.live.spec.ts",
                live_stand.LIVE_CADDY_PROBE_SPEC,
            ),
        ),
    ],
)
def test_live_e2e_mode_maps_to_fixed_playwright_selection(
    mode: str, selected_files: tuple[str, ...]
) -> None:
    expected_suffix = ("--", *selected_files) if selected_files else ()
    assert live_stand._live_e2e_command(mode=mode, platform="posix") == (
        *live_stand.LIVE_E2E_COMMAND,
        *expected_suffix,
    )
    windows_base = live_stand.LIVE_E2E_WINDOWS_COMMAND
    if selected_files:
        expected_windows = (
            *windows_base[:-1],
            f"{windows_base[-1]} -- {' '.join(selected_files)}",
        )
    else:
        expected_windows = windows_base
    assert live_stand._live_e2e_command(mode=mode, platform="nt") == expected_windows


@pytest.mark.parametrize(
    ("mode", "specs", "expire_after"),
    [
        ("smoke", None, None),
        ("full", (live_stand.LIVE_CADDY_PROBE_SPEC,), None),
        ("smoke", None, "compose"),
        ("full", (live_stand.LIVE_CADDY_PROBE_SPEC,), "daemon"),
        ("full", (live_stand.LIVE_CADDY_PROBE_SPEC,), "container"),
        ("full", ("tests/e2e-live/auth-roles.live.spec.ts",), None),
    ],
    ids=(
        "smoke",
        "full-probe",
        "compose-expired",
        "daemon-expired",
        "container-expired",
        "no-probe",
    ),
)
def test_live_e2e_probe_admission_is_bounded_and_keeps_nonprobe_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: str,
    specs: tuple[str, ...] | None,
    expire_after: str | None,
) -> None:
    now = [100.0]
    real_time = live_stand.time
    monkeypatch.setattr(
        live_stand,
        "time",
        SimpleNamespace(monotonic=lambda: now[0], time_ns=real_time.time_ns),
    )
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    owner = live_stand.StandOwner(
        repository=str(tmp_path.resolve()),
        worktree=str(worktree.resolve()),
        project_name="ue-live-0123456789abcdef",
        published_ports=tuple(_port_map().items()),
        schema_version=live_stand.OWNER_SCHEMA_VERSION,
        stack=live_stand.LIVE_STACK_CORE,
        service_roots=live_stand.LIVE_CORE_SERVICE_ROOTS,
        selected_services=live_stand.LIVE_CORE_EXPECTED_SERVICES,
    )
    docker_context = object()
    container_pin = ("a" * 64, "b" * 64)
    nonce = "1" * 32
    expected_correlation_ids = {"desktop": "2" * 32, "mobile": "3" * 32}
    events: list[tuple[str, float | None, object | None]] = []
    playwright_calls: list[tuple[str, dict[str, str]]] = []
    verification_calls: list[dict[str, object]] = []

    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)
    monkeypatch.setattr(live_stand, "_require_worktree", lambda: None)
    monkeypatch.setattr(live_stand, "load_stand_owner", lambda _path: owner)
    monkeypatch.setattr(live_stand, "_seed_locked", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        live_stand,
        "_live_e2e_environment",
        lambda *, output_directory, npm_config_directory: {
            "LIVE_E2E_OUTPUT_DIR": output_directory,
            "PLAYWRIGHT_TEST_OUTPUT_DIR": output_directory,
        },
    )
    monkeypatch.setattr(
        live_stand, "_ensure_live_e2e_dependencies", lambda *_args: None
    )
    monkeypatch.setattr(
        live_stand, "_stand_base_url", lambda _ports: "http://localhost:24000"
    )
    monkeypatch.setattr(
        live_stand,
        "_new_live_caddy_probe_values",
        lambda: (nonce, dict(expected_correlation_ids)),
    )
    monkeypatch.setattr(
        live_stand, "_new_live_docker_read_context", lambda: docker_context
    )
    probe_selected = mode == "smoke" or (
        specs is not None and live_stand.LIVE_CADDY_PROBE_SPEC in specs
    )
    expected_deadline = 125.0 if probe_selected else None
    expected_context = docker_context if probe_selected else None
    expected_specs = (
        live_stand.LIVE_E2E_SMOKE_FILES if mode == "smoke" else tuple(specs or ())
    )

    def record_admission(
        name: str,
        checked_owner: live_stand.StandOwner,
        deadline: float | None,
        actual_context: object | None,
    ) -> None:
        assert checked_owner == owner
        assert deadline == expected_deadline
        assert actual_context is expected_context
        events.append((name, deadline, actual_context))
        if expire_after == name:
            now[0] = 126.0

    original_remaining = live_stand._live_probe_remaining

    def observe_deadline(deadline: float | None) -> float | None:
        events.append(("deadline", deadline, None))
        return original_remaining(deadline)

    def run_playwright(
        *,
        cwd: Path,
        environment: dict[str, str],
        mode: str,
        specs: Sequence[str] | None = None,
    ) -> None:
        assert cwd == worktree / "frontend"
        if mode == "smoke":
            assert specs is None
        else:
            assert tuple(specs or ()) == expected_specs
        events.append(("playwright", None, None))
        playwright_calls.append((mode, dict(environment)))

    def verify_resources(
        checked_worktree: Path,
        checked_owner: live_stand.StandOwner,
        *,
        deadline: float | None = None,
        docker_context: object | None = None,
    ) -> None:
        assert checked_worktree == worktree
        record_admission("compose", checked_owner, deadline, docker_context)

    def require_owned_docker_daemon(
        checked_owner: live_stand.StandOwner,
        *,
        deadline: float | None = None,
        docker_context: object | None = None,
    ) -> None:
        record_admission("daemon", checked_owner, deadline, docker_context)

    def verify_core_caddy_container(
        checked_owner: live_stand.StandOwner,
        *,
        deadline: float | None = None,
        docker_context: object | None = None,
    ) -> tuple[str, str]:
        record_admission("container", checked_owner, deadline, docker_context)
        return container_pin

    def verify_log(
        checked_owner: live_stand.StandOwner,
        output_path: Path,
        *,
        started_at_ms: int,
        finished_at_ms: int,
        password_nonce: str,
        correlation_ids: Mapping[str, str],
        container_pin: tuple[str, str],
        docker_context: object | None = None,
    ) -> None:
        assert checked_owner == owner
        assert output_path.is_dir()
        assert finished_at_ms >= started_at_ms
        assert password_nonce == nonce
        assert dict(correlation_ids) == expected_correlation_ids
        assert container_pin == expected_container_pin
        assert docker_context is expected_docker_context
        events.append(("log-proof", None, docker_context))
        verification_calls.append(
            {
                "output_path": output_path,
                "started_at_ms": started_at_ms,
                "finished_at_ms": finished_at_ms,
                "password_nonce": password_nonce,
                "correlation_ids": dict(correlation_ids),
                "container_pin": container_pin,
                "docker_context": docker_context,
            }
        )

    expected_docker_context = docker_context
    expected_container_pin = container_pin

    monkeypatch.setattr(live_stand, "_live_probe_remaining", observe_deadline)
    monkeypatch.setattr(
        live_stand, "_verify_stand_owner_compose_resources", verify_resources
    )
    monkeypatch.setattr(
        live_stand, "_require_owned_docker_daemon", require_owned_docker_daemon
    )
    monkeypatch.setattr(
        live_stand,
        "_verified_live_core_caddy_container",
        verify_core_caddy_container,
    )
    monkeypatch.setattr(live_stand, "_run_live_playwright", run_playwright)
    monkeypatch.setattr(live_stand, "_verify_live_caddy_probe_log", verify_log)

    if expire_after is None:
        live_stand._e2e_locked("synthetic admin password", mode=mode, specs=specs)
    else:
        with pytest.raises(live_stand.StandError):
            live_stand._e2e_locked("synthetic admin password", mode=mode, specs=specs)
        expected_expired_names = {
            "compose": ["deadline", "compose", "deadline"],
            "daemon": ["deadline", "compose", "deadline", "daemon", "deadline"],
            "container": [
                "deadline",
                "compose",
                "deadline",
                "daemon",
                "deadline",
                "container",
                "deadline",
            ],
        }
        assert [event[0] for event in events] == expected_expired_names[expire_after]
        assert all(event[1] == 125.0 for event in events)
        assert playwright_calls == []
        assert verification_calls == []
        return

    if specs is not None and live_stand.LIVE_CADDY_PROBE_SPEC not in specs:
        assert events == [
            ("compose", None, None),
            ("daemon", None, None),
            ("playwright", None, None),
        ]
        assert playwright_calls[0][0] == "full"
        assert verification_calls == []
        return

    assert events == [
        ("deadline", 125.0, None),
        ("compose", 125.0, docker_context),
        ("deadline", 125.0, None),
        ("daemon", 125.0, docker_context),
        ("deadline", 125.0, None),
        ("container", 125.0, docker_context),
        ("deadline", 125.0, None),
        ("playwright", None, None),
        ("log-proof", None, docker_context),
    ]
    if mode == "smoke":
        selected_files = live_stand.LIVE_E2E_SMOKE_FILES
        assert selected_files == (
            "tests/e2e-live/auth-roles.live.spec.ts",
            "tests/e2e-live/password-reset.live.spec.ts",
            "tests/e2e-live/search-dialog-keyboard.live.spec.ts",
            "tests/e2e-live/settings-radio-focus.live.spec.ts",
            live_stand.LIVE_CADDY_PROBE_SPEC,
        )
        assert live_stand._live_e2e_command(mode="smoke", platform="posix") == (
            *live_stand.LIVE_E2E_COMMAND,
            "--",
            *selected_files,
        )
    assert len(playwright_calls) == 1
    mode_seen, playwright_environment = playwright_calls[0]
    assert mode_seen == mode
    assert playwright_environment["LIVE_CADDY_LOG_PROBE"] == nonce
    assert (
        json.loads(playwright_environment["LIVE_CADDY_PROBE_IDS"])
        == expected_correlation_ids
    )
    assert len(verification_calls) == 1
    verification = verification_calls[0]
    assert verification["password_nonce"] == nonce
    assert verification["correlation_ids"] == expected_correlation_ids
    assert verification["container_pin"] == container_pin
    assert verification["docker_context"] is docker_context
    assert verification["started_at_ms"] <= verification["finished_at_ms"]


def test_e2e_cli_forwards_explicit_mode_without_starting_a_stand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from contextlib import nullcontext

    observed: list[tuple[str, str]] = []
    monkeypatch.setattr(live_stand, "stand_lifecycle_lock", nullcontext)
    monkeypatch.setattr(live_stand, "load_stand_owner", lambda _path: object())
    monkeypatch.setattr(
        live_stand,
        "load_or_create_stand_admin_password",
        lambda _path, _owner: "synthetic-password-marker",
    )
    monkeypatch.setattr(
        live_stand,
        "_e2e_locked",
        lambda password, *, mode="full": observed.append((password, mode)),
    )

    assert live_stand.main(["e2e", "--mode", "smoke"]) == 0
    assert observed == [("synthetic-password-marker", "smoke")]


def test_busy_published_port_blocks_the_stand() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        busy_port = listener.getsockname()[1]

        assert live_stand.port_is_free(busy_port) is False
        with pytest.raises(live_stand.StandError, match=rf"\[{busy_port}\]"):
            live_stand.require_free_ports([busy_port])


def test_port_preflight_detects_a_bound_socket_without_listen() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as binder:
        binder.bind(("127.0.0.1", 0))
        bound_port = binder.getsockname()[1]

        assert live_stand.port_is_free(bound_port) is False


def test_port_map_covers_every_full_stack_and_mailpit_publication() -> None:
    expected = {
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
        "MINIO",
        "MAILPIT",
    }

    assert {
        name for name, _service, _container_port in live_stand.LIVE_PORT_SPECS
    } == expected
    assert len(live_stand.LIVE_PORT_SPECS) == len(expected)


def test_port_preflight_checks_every_live_port_on_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probes: list[tuple[int, str]] = []
    ports = _port_map()

    def fake_port_is_free(port: int, host: str = "127.0.0.1") -> bool:
        probes.append((port, host))
        return True

    monkeypatch.setattr(live_stand, "port_is_free", fake_port_is_free)

    live_stand.require_free_ports(ports)

    assert probes == [(port, "127.0.0.1") for port in ports.values()]


def test_core_port_allocation_probes_only_published_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probes: list[int] = []

    def fake_port_is_free(port: int, host: str = "127.0.0.1") -> bool:
        assert host == "127.0.0.1"
        probes.append(port)
        return True

    monkeypatch.setattr(live_stand, "port_is_free", fake_port_is_free)
    monkeypatch.setattr(live_stand.secrets, "randbelow", lambda _limit: len(probes))

    ports = live_stand.choose_published_ports(
        active_services=live_stand.LIVE_CORE_EXPECTED_SERVICES
    )
    active_names = live_stand._published_port_names_for_services(
        live_stand.LIVE_CORE_EXPECTED_SERVICES
    )

    assert "MINIO" in active_names
    assert tuple(ports) == tuple(
        name for name, _service, _port in live_stand.LIVE_PORT_SPECS
    )
    assert probes == list(ports[name] for name in active_names)
    assert len(set(ports.values())) == len(live_stand.LIVE_PORT_SPECS)
    assert not set(probes).intersection(
        ports[name] for name in ports if name not in active_names
    )


def test_core_port_recheck_ignores_unused_interpolation_ports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_names = live_stand._published_port_names_for_services(
        live_stand.LIVE_CORE_EXPECTED_SERVICES
    )
    ports = _port_map(50000)
    inactive_names = set(ports) - set(active_names)
    probes: list[int] = []

    def fake_port_is_free(port: int, host: str = "127.0.0.1") -> bool:
        assert host == "127.0.0.1"
        probes.append(port)
        return port not in {ports[name] for name in inactive_names}

    monkeypatch.setattr(live_stand, "port_is_free", fake_port_is_free)

    live_stand.require_free_ports(
        ports, active_services=live_stand.LIVE_CORE_EXPECTED_SERVICES
    )

    assert probes == [ports[name] for name in active_names]


def test_generated_port_map_is_distinct_and_within_unprivileged_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probes: list[int] = []

    def fake_port_is_free(port: int, host: str = "127.0.0.1") -> bool:
        assert host == "127.0.0.1"
        probes.append(port)
        return True

    monkeypatch.setattr(live_stand, "port_is_free", fake_port_is_free)
    monkeypatch.setattr(live_stand.secrets, "randbelow", lambda _limit: len(probes))

    ports = live_stand.choose_published_ports()

    assert "MINIO" in ports
    assert list(ports) == [
        name for name, _service, _target in live_stand.LIVE_PORT_SPECS
    ]
    assert len(set(ports.values())) == len(live_stand.LIVE_PORT_SPECS)
    assert all(20000 <= port <= 45000 for port in ports.values())


def test_core_compose_identity_binds_active_port_names_not_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree = tmp_path / "ue-live"
    worktree.mkdir()
    (worktree / live_stand.OVERLAY).write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    _install_compose_config_mock(monkeypatch, worktree)
    roots = live_stand.LIVE_CORE_SERVICE_ROOTS
    selected = live_stand.LIVE_CORE_EXPECTED_SERVICES

    def selected_services(
        _project: object, stack: str
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        if stack == live_stand.LIVE_STACK_CORE:
            return roots, selected
        return (), ("backend",)

    monkeypatch.setattr(live_stand, "resolve_live_service_selection", selected_services)
    ports = _port_map(40000)
    changed_active = dict(ports)
    changed_active["CADDY_HTTP"] += 1000
    changed_inactive = dict(ports)
    changed_inactive["GRAFANA"] += 1000

    core = live_stand._compose_resource_evidence(
        worktree,
        "ue-live-0123456789abcdef",
        ports,
        stack=live_stand.LIVE_STACK_CORE,
        service_roots=roots,
    )
    core_active_change = live_stand._compose_resource_evidence(
        worktree,
        "ue-live-0123456789abcdef",
        changed_active,
        stack=live_stand.LIVE_STACK_CORE,
        service_roots=roots,
    )
    core_inactive_change = live_stand._compose_resource_evidence(
        worktree,
        "ue-live-0123456789abcdef",
        changed_inactive,
        stack=live_stand.LIVE_STACK_CORE,
        service_roots=roots,
    )
    full = live_stand._compose_resource_evidence(
        worktree, "ue-live-0123456789abcdef", ports
    )
    full_port_change = live_stand._compose_resource_evidence(
        worktree, "ue-live-0123456789abcdef", changed_active
    )

    assert core.fingerprint == core_active_change.fingerprint
    assert core.fingerprint == core_inactive_change.fingerprint
    assert full.fingerprint == full_port_change.fingerprint


def test_free_port_is_reported_free() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
    assert live_stand.port_is_free(free_port) is True


def test_dirty_stand_worktree_is_not_switched(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_git(*args: str) -> str:
        calls.append(args)
        return "abc123" if args[0] == "rev-parse" else " M app/main.py"

    monkeypatch.setattr(live_stand, "WORKTREE", tmp_path)
    monkeypatch.setattr(live_stand, "_git", fake_git)

    with pytest.raises(live_stand.StandError, match="tracked changes"):
        live_stand.ensure_worktree("HEAD")
    assert not any(call[:1] == ("-C",) and "checkout" in call for call in calls)


def test_up_rejects_dirty_worktree_before_stopping_existing_stand(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, owner, keys = _prepare_owned_stand(monkeypatch, tmp_path)
    commands: list[list[str]] = []

    def dirty_status(*args: str) -> str:
        if args[0] == "-C" and "status" in args:
            return " M tracked-file.txt"
        return ""

    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "_git", dirty_status)
    monkeypatch.setattr(live_stand, "resolve_stand_ref", lambda _ref: "abc123")
    monkeypatch.setattr(live_stand, "load_stand_owner", lambda _path: owner)
    monkeypatch.setattr(live_stand, "load_vapid", lambda _path: keys)
    monkeypatch.setattr(live_stand, "stand_environment", lambda *_args: {})
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_: commands.append(list(command))
    )

    with pytest.raises(live_stand.StandError, match="tracked changes"):
        live_stand._up_locked("HEAD")

    assert commands == []


def _prepare_owned_stand(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    daemon_fingerprint: str = "a" * 64,
    compose_config_calls: list[tuple[list[str], Path, dict[str, str]]] | None = None,
) -> tuple[Path, live_stand.StandOwner, dict[str, str]]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    worktree = tmp_path / "ue-live"
    worktree.mkdir()
    (worktree / live_stand.OVERLAY).write_text("services: {}\n")
    monkeypatch.setattr(live_stand, "REPO_ROOT", repo_root)
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "_git", lambda *args: ".git")

    def docker_daemon_fingerprint(
        *,
        deadline: float | None = None,
        docker_context: live_stand._LiveDockerReadContext | None = None,
    ) -> str:
        assert deadline is None
        assert docker_context is None
        return daemon_fingerprint

    monkeypatch.setattr(
        live_stand,
        "docker_daemon_fingerprint",
        docker_daemon_fingerprint,
        raising=False,
    )
    _install_compose_config_mock(
        monkeypatch, worktree, compose_config_calls=compose_config_calls
    )
    monkeypatch.setattr(
        live_stand,
        "_assert_compose_volume_ownership",
        lambda _project, _volumes, **_kwargs: (),
    )
    owner = live_stand.create_stand_owner(worktree)
    keys = live_stand.load_or_create_vapid(worktree)
    owner = live_stand._bind_stand_owner_compose_resources(worktree, owner)
    return worktree, owner, keys


def _prepare_core_owned_stand(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Path, live_stand.StandOwner]:
    worktree, full_owner, _keys = _prepare_owned_stand(monkeypatch, tmp_path)
    original_resolver = live_stand.resolve_live_service_selection

    def resolve_selection(
        compose_project: Mapping[str, object], stack: str
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        if stack == live_stand.LIVE_STACK_CORE:
            return (
                live_stand.LIVE_CORE_SERVICE_ROOTS,
                live_stand.LIVE_CORE_EXPECTED_SERVICES,
            )
        return original_resolver(compose_project, stack)

    monkeypatch.setattr(live_stand, "resolve_live_service_selection", resolve_selection)
    incomplete_core_owner = replace(
        full_owner,
        compose_resource_fingerprint=None,
        resume_compose_resource_fingerprint=None,
        resume_compose_resource_schema_version=None,
        stack=live_stand.LIVE_STACK_CORE,
        service_roots=live_stand.LIVE_CORE_SERVICE_ROOTS,
        selected_services=(),
    )
    live_stand._write_stand_owner_update(worktree, incomplete_core_owner)
    core_owner = live_stand._bind_stand_owner_compose_resources(
        worktree, incomplete_core_owner
    )
    return worktree, core_owner


def _install_compose_config_mock(
    monkeypatch: pytest.MonkeyPatch,
    worktree: Path,
    *,
    compose_config_calls: list[tuple[list[str], Path, dict[str, str]]] | None = None,
) -> None:
    """Model the owned resolved volume without invoking Docker or reading stand files."""
    config_calls = compose_config_calls if compose_config_calls is not None else []
    original_run = subprocess.run

    def fake_run(command: Sequence[str], *args: Any, **kwargs: Any) -> Any:
        if tuple(command[:2]) != ("docker", "compose"):
            return original_run(command, *args, **kwargs)
        if tuple(command[-3:]) != ("config", "--format", "json"):
            pytest.fail("owned Compose commands must not invoke Docker in this fixture")

        project_name = command[command.index("-p") + 1]
        assert list(command) == live_stand.compose_command(
            "config", "--format", "json", project_name=project_name
        )
        assert kwargs["cwd"] == worktree
        assert kwargs["check"] is True
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        if "COMPOSE_PROJECT_NAME" in environment:
            assert environment["COMPOSE_PROJECT_NAME"] == project_name
        config_calls.append((list(command), worktree, dict(environment)))

        model = {
            "name": project_name,
            "volumes": {
                "app-data": {
                    "name": f"{project_name}_app-data",
                    "external": False,
                }
            },
            "services": {
                "backend": {
                    "volumes": [
                        {"type": "volume", "source": "app-data", "target": "/data"}
                    ],
                    "volumes_from": [],
                }
            },
        }
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(model), stderr=""
        )

    monkeypatch.setattr(live_stand.subprocess, "run", fake_run)


def _write_legacy_owner_marker(
    worktree: Path, owner: live_stand.StandOwner, version: int
) -> Path:
    payload: dict[str, Any] = {
        "version": version,
        "repository": owner.repository,
        "worktree": owner.worktree,
        "project_name": owner.project_name,
    }
    if version >= 3:
        payload["published_ports"] = {
            name: port for name, port in owner.published_ports if name != "MINIO"
        }
    if version >= live_stand.PREVIOUS_OWNER_SCHEMA_VERSION:
        assert owner.daemon_fingerprint is not None
        payload["daemon_fingerprint"] = owner.daemon_fingerprint
    marker = {
        **payload,
        "signature": live_stand._owner_signature(
            payload, live_stand._owner_signing_key(create=False)
        ),
    }
    marker_path = worktree / live_stand.STAND_FILE
    marker_path.write_text(json.dumps(marker), encoding="utf-8")
    return marker_path


def _write_pre_minio_owner_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    version: int,
    *,
    malformed_ports: bool = False,
    invalid_signature: bool = False,
) -> tuple[Path, Path]:
    in_place_mode = version == 9
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").mkdir()
    worktree = (
        tmp_path / live_stand.IN_PLACE_STATE_PARENT / "run-pre-minio"
        if in_place_mode
        else tmp_path / "ue-live"
    )
    worktree.mkdir(parents=True)
    (repository / "docker-compose.full.yml").write_text(
        "services: {}\n", encoding="utf-8"
    )
    (repository / live_stand.OVERLAY).write_text("services: {}\n", encoding="utf-8")
    (worktree / live_stand.OVERLAY).write_text("services: {}\n", encoding="utf-8")
    secrets_directory = worktree / ".secrets"
    secrets_directory.mkdir()
    if in_place_mode:
        (worktree / live_stand.IN_PLACE_OVERLAY).write_text(
            "services: {}\n", encoding="utf-8"
        )
        if os.name != "nt":
            worktree.chmod(0o700)
            secrets_directory.chmod(0o700)
    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", in_place_mode)
    monkeypatch.setattr(live_stand, "SOURCE_SHA", "a" * 40 if in_place_mode else None)

    key_path = (
        worktree / ".secrets" / "live-stand-owner.key"
        if in_place_mode
        else repository / ".git" / "live-stand-owner.key"
    )
    key = bytes(range(32))
    key_path.write_bytes(key)
    old_port_specs = tuple(
        spec for spec in live_stand.LIVE_PORT_SPECS if spec[0] != "MINIO"
    )
    ports = {
        name: 24000 + index
        for index, (name, _service, _target) in enumerate(old_port_specs)
    }
    if malformed_ports:
        ports.pop("BACKEND")
    payload: dict[str, object] = {
        "version": version,
        "repository": str(repository.resolve()),
        "worktree": str(worktree.resolve()),
        "project_name": "ue-live-0123456789abcdef",
        "published_ports": ports,
        "daemon_fingerprint": "b" * 64,
        "compose_resource_fingerprint": None,
        "resume_compose_resource_fingerprint": None,
        "resume_compose_resource_schema_version": None,
        "stack": live_stand.LIVE_STACK_FULL,
        "service_roots": [],
        "selected_services": [],
    }
    if in_place_mode:
        payload["source_sha"] = "a" * 40
    signature = live_stand._owner_signature(payload, key)
    if invalid_signature:
        signature = "0" * 64
    marker_path = worktree / live_stand.STAND_FILE
    marker_path.write_text(
        json.dumps({**payload, "signature": signature}), encoding="utf-8"
    )
    return worktree, marker_path


@pytest.mark.parametrize(
    ("in_place_mode", "version"),
    [(False, 8), (True, 9)],
    ids=["worktree-v8", "in-place-v9"],
)
@pytest.mark.parametrize("operation", ["load", "status", "stop", "teardown"])
def test_pre_minio_owner_markers_fail_before_lifecycle_commands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    in_place_mode: bool,
    version: int,
    operation: str,
) -> None:
    worktree, marker_path = _write_pre_minio_owner_marker(
        monkeypatch, tmp_path, version
    )
    assert in_place_mode == (version == 9)
    marker_before = marker_path.read_bytes()
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        live_stand.subprocess,
        "run",
        lambda command, *_args, **_kwargs: commands.append(tuple(command)),
    )
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_kwargs: commands.append(tuple(command)),
    )

    with pytest.raises(live_stand.StandError, match=r"pre-MINIO.*matching previous"):
        if operation == "load":
            live_stand.load_stand_owner(worktree)
        else:
            getattr(live_stand, operation)()

    assert marker_path.read_bytes() == marker_before
    assert commands == []


@pytest.mark.parametrize("invalid", ["signature", "port-shape"])
def test_invalid_pre_minio_owner_markers_use_generic_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    invalid: str,
) -> None:
    worktree, _marker_path = _write_pre_minio_owner_marker(
        monkeypatch,
        tmp_path,
        8,
        malformed_ports=invalid == "port-shape",
        invalid_signature=invalid == "signature",
    )

    with pytest.raises(live_stand.StandError, match="invalid ownership metadata"):
        live_stand.load_stand_owner(worktree)


def test_docker_daemon_fingerprint_hashes_engine_id_without_printing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    engine_id = "fixture-engine-id"
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append((command, kwargs))
        return SimpleNamespace(stdout=f"{engine_id}\n")

    monkeypatch.setattr(live_stand.subprocess, "run", run)

    fingerprint = live_stand.docker_daemon_fingerprint()

    assert fingerprint == hashlib.sha256(engine_id.encode("utf-8")).hexdigest()
    assert calls == [
        (
            ["docker", "info", "--format", "{{.ID}}"],
            {
                "check": True,
                "capture_output": True,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
            },
        )
    ]
    assert engine_id not in capsys.readouterr().out


def test_new_owner_marker_stores_fingerprints_without_raw_docker_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    engine_id = "fixture-engine-id"
    fingerprint = hashlib.sha256(engine_id.encode("utf-8")).hexdigest()
    worktree, owner, _ = _prepare_owned_stand(
        monkeypatch, tmp_path, daemon_fingerprint=fingerprint
    )
    marker_path = worktree / live_stand.STAND_FILE
    marker_text = marker_path.read_text(encoding="utf-8")
    marker = json.loads(marker_text)

    assert owner.daemon_fingerprint == fingerprint
    assert owner.compose_resource_fingerprint is not None
    assert len(owner.compose_resource_fingerprint) == 64
    assert all(
        char in "0123456789abcdef" for char in owner.compose_resource_fingerprint
    )
    assert marker["version"] == live_stand.OWNER_SCHEMA_VERSION
    assert marker["daemon_fingerprint"] == fingerprint
    assert marker["compose_resource_fingerprint"] == owner.compose_resource_fingerprint
    assert engine_id not in marker_text


@pytest.mark.parametrize(
    "stack", [live_stand.LIVE_STACK_FULL, live_stand.LIVE_STACK_CORE]
)
def test_invalidated_signed_owner_retains_resumable_resource_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stack: str
) -> None:
    if stack == live_stand.LIVE_STACK_CORE:
        worktree, owner = _prepare_core_owned_stand(monkeypatch, tmp_path)
    else:
        worktree, owner, _keys = _prepare_owned_stand(monkeypatch, tmp_path)

    original_fingerprint = owner.compose_resource_fingerprint
    assert original_fingerprint is not None

    invalidated = live_stand._invalidate_stand_owner_compose_resources(worktree, owner)
    loaded = live_stand.load_stand_owner(worktree)

    assert loaded == invalidated
    assert loaded.stack == owner.stack == stack
    assert loaded.compose_resource_fingerprint is None
    assert loaded.resume_compose_resource_fingerprint == original_fingerprint
    assert loaded.resume_compose_resource_schema_version == owner.schema_version
    assert loaded.selected_services == ()
    assert loaded.service_roots == (
        owner.service_roots if stack == live_stand.LIVE_STACK_CORE else ()
    )

    resumed = live_stand._resume_compose_resource_evidence(worktree, loaded)
    assert resumed.fingerprint == original_fingerprint
    assert resumed.stack == owner.stack
    assert resumed.selected_services == owner.selected_services


def test_core_signed_resume_accepts_reallocated_published_port_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, owner = _prepare_core_owned_stand(monkeypatch, tmp_path)
    original_fingerprint = owner.compose_resource_fingerprint
    assert original_fingerprint is not None
    changed_ports = dict(owner.published_ports)
    occupied_ports = set(changed_ports.values())
    changed_ports["CADDY_HTTP"] = next(
        port for port in range(1024, 65536) if port not in occupied_ports
    )

    incomplete = live_stand.update_stand_owner_ports(worktree, owner, changed_ports)
    rebound = live_stand._bind_stand_owner_compose_resources(worktree, incomplete)

    assert dict(rebound.published_ports) == changed_ports
    assert rebound.stack == live_stand.LIVE_STACK_CORE
    assert rebound.service_roots == owner.service_roots
    assert rebound.selected_services == owner.selected_services
    assert rebound.compose_resource_fingerprint == original_fingerprint


def test_core_signed_resume_rejects_compose_mount_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, owner = _prepare_core_owned_stand(monkeypatch, tmp_path)
    changed_ports = dict(owner.published_ports)
    occupied_ports = set(changed_ports.values())
    changed_ports["CADDY_HTTP"] = next(
        port for port in range(1024, 65536) if port not in occupied_ports
    )
    incomplete = live_stand.update_stand_owner_ports(worktree, owner, changed_ports)
    marker = worktree / live_stand.STAND_FILE
    marker_before = marker.read_bytes()
    original_run = live_stand.subprocess.run

    def changed_mount_run(command: Sequence[str], *args: Any, **kwargs: Any) -> Any:
        if tuple(command[:2]) == ("docker", "compose") and tuple(command[-3:]) == (
            "config",
            "--format",
            "json",
        ):
            project_name = command[command.index("-p") + 1]
            model = {
                "name": project_name,
                "volumes": {
                    "app-data": {
                        "name": f"{project_name}_app-data",
                        "external": False,
                    }
                },
                "services": {
                    "backend": {
                        "volumes": [
                            {
                                "type": "volume",
                                "source": "app-data",
                                "target": "/changed-target",
                            }
                        ],
                        "volumes_from": [],
                    }
                },
            }
            return subprocess.CompletedProcess(
                command, 0, stdout=json.dumps(model), stderr=""
            )
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(live_stand.subprocess, "run", changed_mount_run)

    with pytest.raises(
        live_stand.StandError,
        match="resolved Compose resource identity differs from signed resume evidence",
    ):
        live_stand._bind_stand_owner_compose_resources(worktree, incomplete)

    assert marker.read_bytes() == marker_before
    assert live_stand.load_stand_owner(worktree) == incomplete


def test_signed_complete_full_owner_requires_roots_to_match_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    assert owner.compose_resource_fingerprint is not None
    malformed = replace(owner, service_roots=())
    live_stand._write_stand_owner_update(worktree, malformed)

    with pytest.raises(
        live_stand.StandError,
        match="full-stack service roots and selection do not match",
    ):
        live_stand.load_stand_owner(worktree)


def test_signed_incomplete_full_owner_cannot_claim_a_partial_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").mkdir()
    worktree = tmp_path / live_stand.WORKTREE_NAME
    worktree.mkdir()
    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)
    monkeypatch.setattr(live_stand, "docker_daemon_fingerprint", lambda: "a" * 64)
    owner = live_stand.create_stand_owner(worktree, published_ports=_port_map())
    malformed = replace(owner, selected_services=("backend",))
    live_stand._write_stand_owner_update(worktree, malformed)

    with pytest.raises(
        live_stand.StandError,
        match="incomplete live ownership contains a service selection",
    ):
        live_stand.load_stand_owner(worktree)


@pytest.mark.parametrize("version", [2, 3, 4])
def test_status_fails_closed_for_legacy_markers_without_resource_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    version: int,
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    marker_path = _write_legacy_owner_marker(worktree, owner, version)
    marker_before = marker_path.read_bytes()
    commands: list[list[str]] = []
    lock_path = worktree.parent / f".{worktree.name}.lifecycle.lock"

    expected_message = (
        "cannot verify Docker daemon ownership"
        if version < live_stand.PREVIOUS_OWNER_SCHEMA_VERSION
        else "lacks Compose resource evidence"
    )
    with pytest.raises(live_stand.StandError, match=expected_message):
        live_stand.status()

    assert commands == []
    assert marker_path.read_bytes() == marker_before
    assert not lock_path.exists()


@pytest.mark.parametrize("version", [2, 3, 4])
@pytest.mark.parametrize("operation", ["stop", "teardown"])
def test_destructive_lifecycle_preserves_legacy_markers_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    version: int,
    operation: str,
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    marker_path = _write_legacy_owner_marker(worktree, owner, version)
    marker_before = marker_path.read_bytes()
    commands: list[list[str]] = []
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_: commands.append(list(command))
    )

    if version < live_stand.PREVIOUS_OWNER_SCHEMA_VERSION:
        with pytest.raises(
            live_stand.StandError, match="cannot verify Docker daemon ownership"
        ):
            getattr(live_stand, operation)()
        assert commands == []
    elif operation == "stop":
        with pytest.raises(
            live_stand.StandError, match="lacks Compose resource evidence"
        ):
            live_stand.stop()
        assert commands == []
    else:
        with pytest.raises(
            live_stand.StandError, match="lacks Compose resource evidence"
        ):
            live_stand.teardown()
        assert commands == []

    assert marker_path.read_bytes() == marker_before


def test_owner_marker_persists_and_authenticates_the_port_map(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    worktree = tmp_path / "ue-live"
    worktree.mkdir()
    monkeypatch.setattr(live_stand, "REPO_ROOT", repo_root)
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "_git", lambda *_: ".git")
    monkeypatch.setattr(
        live_stand, "docker_daemon_fingerprint", lambda: "a" * 64, raising=False
    )
    _install_compose_config_mock(monkeypatch, worktree)
    ports = _port_map()

    owner = live_stand.create_stand_owner(worktree, published_ports=ports)
    loaded = live_stand.load_stand_owner(worktree)
    marker = json.loads((worktree / live_stand.STAND_FILE).read_text())

    assert dict(owner.published_ports) == ports
    assert dict(loaded.published_ports) == ports
    assert marker["published_ports"] == ports
    assert marker["version"] == live_stand.OWNER_SCHEMA_VERSION

    marker["published_ports"]["CADDY_HTTPS"] += 100
    (worktree / live_stand.STAND_FILE).write_text(json.dumps(marker))
    with pytest.raises(live_stand.StandError, match="signature"):
        live_stand.load_stand_owner(worktree)


def test_live_endpoint_verifier_accepts_only_the_signed_emitted_urls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    marker = worktree / live_stand.STAND_FILE
    marker_before = marker.read_bytes()
    env_file = worktree / ".env"
    env_file.write_text("LIVE_STAND_TEST_SENTINEL=unchanged\n", encoding="utf-8")
    env_before = env_file.read_bytes()
    vapid_file = worktree / live_stand.VAPID_FILE
    original_read_text = Path.read_text

    def guarded_read_text(path: Path, *args: Any, **kwargs: Any) -> str:
        if path in {env_file, vapid_file}:
            pytest.fail("endpoint verification must not read .env or VAPID")
        return original_read_text(path, *args, **kwargs)

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("endpoint verification must not inspect Compose or VAPID")

    monkeypatch.setattr(live_stand, "_run", forbidden)
    monkeypatch.setattr(live_stand, "load_vapid", forbidden)
    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    ports = dict(owner.published_ports)

    live_stand.verify_live_endpoints(
        f"http://localhost:{ports['CADDY_HTTP']}",
        f"http://127.0.0.1:{ports['MAILPIT']}",
    )

    assert marker.read_bytes() == marker_before
    assert env_file.read_bytes() == env_before


@pytest.mark.parametrize("endpoint", ["base", "mailpit"])
def test_live_endpoint_verifier_rejects_another_valid_range_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, endpoint: str
) -> None:
    _, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    ports = dict(owner.published_ports)
    base_url = f"http://localhost:{ports['CADDY_HTTP']}"
    mailpit_url = f"http://127.0.0.1:{ports['MAILPIT']}"
    if endpoint == "base":
        base_url = f"http://localhost:{ports['CADDY_HTTP'] + 1}"
    else:
        mailpit_url = f"http://127.0.0.1:{ports['MAILPIT'] + 1}"

    with pytest.raises(
        live_stand.StandError, match="endpoint ownership verification failed"
    ):
        live_stand.verify_live_endpoints(base_url, mailpit_url)


@pytest.mark.parametrize(
    ("base_host", "base_scheme", "mailpit_host", "mailpit_scheme"),
    [
        ("127.0.0.1", "http", "127.0.0.1", "http"),
        ("localhost", "https", "127.0.0.1", "http"),
        ("localhost", "http", "localhost", "http"),
        ("localhost", "http", "127.0.0.1", "https"),
    ],
)
def test_live_endpoint_verifier_rejects_wrong_host_or_scheme(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    base_host: str,
    base_scheme: str,
    mailpit_host: str,
    mailpit_scheme: str,
) -> None:
    _, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    ports = dict(owner.published_ports)

    with pytest.raises(
        live_stand.StandError, match="endpoint ownership verification failed"
    ):
        live_stand.verify_live_endpoints(
            f"{base_scheme}://{base_host}:{ports['CADDY_HTTP']}",
            f"{mailpit_scheme}://{mailpit_host}:{ports['MAILPIT']}",
        )


@pytest.mark.parametrize("tampering", ["missing", "signature", "legacy"])
def test_live_endpoint_verifier_fails_closed_on_missing_or_tampered_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tampering: str
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    marker_path = worktree / live_stand.STAND_FILE
    ports = dict(owner.published_ports)
    if tampering == "missing":
        marker_path.unlink()
    elif tampering == "legacy":
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        payload = {
            "version": live_stand.LEGACY_OWNER_SCHEMA_VERSION,
            "repository": marker["repository"],
            "worktree": marker["worktree"],
            "project_name": marker["project_name"],
        }
        legacy_marker = {
            **payload,
            "signature": live_stand._owner_signature(
                payload, live_stand._owner_signing_key(create=False)
            ),
        }
        marker_path.write_text(json.dumps(legacy_marker), encoding="utf-8")
    else:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["published_ports"]["CADDY_HTTP"] += 1
        marker_path.write_text(json.dumps(marker), encoding="utf-8")

    with pytest.raises(
        live_stand.StandError, match="endpoint ownership verification failed"
    ):
        live_stand.verify_live_endpoints(
            f"http://localhost:{ports['CADDY_HTTP']}",
            f"http://127.0.0.1:{ports['MAILPIT']}",
        )


def test_verify_endpoints_cli_emits_only_generic_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    ports = dict(owner.published_ports)

    result = live_stand.main(
        [
            "verify-endpoints",
            "--base-url",
            f"http://localhost:{ports['CADDY_HTTP']}",
            "--mailpit-url",
            f"http://127.0.0.1:{ports['MAILPIT']}",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert captured.out == "live stand endpoints verified\n"
    assert captured.err == ""
    assert str(ports["CADDY_HTTP"]) not in captured.out
    assert str(ports["MAILPIT"]) not in captured.out


def test_verify_endpoints_cli_hides_marker_failure_details(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    (worktree / live_stand.STAND_FILE).unlink()
    ports = dict(owner.published_ports)

    result = live_stand.main(
        [
            "verify-endpoints",
            "--base-url",
            f"http://localhost:{ports['CADDY_HTTP']}",
            "--mailpit-url",
            f"http://127.0.0.1:{ports['MAILPIT']}",
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert captured.out == ""
    assert (
        captured.err
        == "live_stand: live stand endpoint ownership verification failed\n"
    )
    assert str(worktree) not in captured.err
    assert str(ports["CADDY_HTTP"]) not in captured.err


def test_legacy_owner_marker_resolves_the_original_port_map_read_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    marker_path = worktree / live_stand.STAND_FILE
    marker = json.loads(marker_path.read_text())
    payload = {
        "version": 2,
        "repository": marker["repository"],
        "worktree": marker["worktree"],
        "project_name": marker["project_name"],
    }
    marker = {
        **payload,
        "signature": live_stand._owner_signature(
            payload, live_stand._owner_signing_key(create=False)
        ),
    }
    marker_path.write_text(json.dumps(marker))

    loaded = live_stand.load_stand_owner(worktree)

    assert loaded.project_name == owner.project_name
    assert loaded.schema_version == 2
    assert dict(loaded.published_ports) == live_stand.LEGACY_PUBLISHED_PORTS


def test_status_does_not_generate_missing_owner_or_vapid_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree = tmp_path / "ue-live"
    worktree.mkdir()
    (worktree / live_stand.OVERLAY).write_text("services: {}\n")
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    common_git_directory = tmp_path / "common-git"
    common_git_directory.mkdir()
    monkeypatch.setattr(
        live_stand, "_git_common_directory", lambda: common_git_directory
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_: commands.append(list(command))
    )

    with pytest.raises(live_stand.StandError, match="ownership metadata"):
        live_stand.status()

    assert not (worktree / live_stand.STAND_FILE).exists()
    assert not (worktree / live_stand.VAPID_FILE).exists()
    assert not (worktree.parent / f".{worktree.name}.lifecycle.lock").exists()
    assert commands == []
    assert tuple(common_git_directory.iterdir()) == ()


def test_status_cli_missing_owner_is_read_only_and_does_not_use_docker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = tmp_path / "ue-live"
    worktree.mkdir()
    (worktree / live_stand.OVERLAY).write_text("services: {}\n")
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    common_git_directory = tmp_path / "common-git"
    common_git_directory.mkdir()
    monkeypatch.setattr(
        live_stand, "_git_common_directory", lambda: common_git_directory
    )

    def reject_docker(*_: Any, **__: Any) -> None:
        pytest.fail("status must not invoke Docker")

    monkeypatch.setattr(live_stand, "_run", reject_docker)
    monkeypatch.setattr(live_stand, "docker_daemon_fingerprint", reject_docker)

    assert live_stand.main(["status"]) == 2
    assert "ownership metadata" in capsys.readouterr().err
    assert not (worktree / live_stand.STAND_FILE).exists()
    assert not (worktree / live_stand.VAPID_FILE).exists()
    assert not (worktree / live_stand.ADMIN_PASSWORD_FILE).exists()
    assert not (worktree / ".secrets").exists()
    assert tuple(common_git_directory.iterdir()) == ()


@pytest.mark.parametrize("operation", ["status", "stop", "teardown"])
def test_compose_control_commands_never_read_or_pass_vapid_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, operation: str
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    vapid_path = worktree / live_stand.VAPID_FILE
    vapid_path.unlink()
    commands: list[list[str]] = []
    environments: list[dict[str, str] | None] = []

    def reject_vapid_read(_: Path) -> dict[str, str]:
        pytest.fail("status must not read the VAPID key file")

    def capture_compose_environment(
        command: list[str], *, cwd: Path, env: dict[str, str] | None = None
    ) -> None:
        del cwd
        commands.append(command)
        environments.append(env)

    monkeypatch.setenv("LIVE_VAPID_PUBLIC_KEY", "ambient-public")
    monkeypatch.setenv("LIVE_VAPID_PRIVATE_KEY", "ambient-private")
    monkeypatch.setattr(live_stand, "load_vapid", reject_vapid_read)
    if operation == "status":
        monkeypatch.setattr(
            live_stand,
            "_status_compose_output",
            lambda command, *, cwd, env: (
                commands.append(list(command)) or environments.append(dict(env)) or ""
            ),
        )
    else:
        monkeypatch.setattr(live_stand, "_run", capture_compose_environment)

    getattr(live_stand, operation)()

    compose_args = {
        "status": ("ps",),
        "stop": ("stop",),
        "teardown": ("down", "--volumes"),
    }[operation]
    assert commands == [
        live_stand.compose_command(*compose_args, project_name=owner.project_name)
    ]
    assert not vapid_path.exists()
    assert environments[0] is not None
    assert environments[0]["LIVE_VAPID_PUBLIC_KEY"] == (
        live_stand.COMPOSE_INSPECTION_PLACEHOLDER
    )
    assert environments[0]["LIVE_VAPID_PRIVATE_KEY"] == (
        live_stand.COMPOSE_INSPECTION_PLACEHOLDER
    )
    ports = dict(owner.published_ports)
    assert environments[0]["LIVE_BASE_URL"] == f"http://localhost:{ports['CADDY_HTTP']}"
    assert environments[0]["LIVE_MAILPIT_PORT"] == str(ports["MAILPIT"])
    for name, port in ports.items():
        if name != "MAILPIT":
            assert environments[0][f"LIVE_HOST_PORT_{name}"] == str(port)


def test_status_is_read_only_and_uses_the_owned_project(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    protected_files = {
        ".env": b"STATUS_SENTINEL=keep\n",
        ".env.docker": b"LIVE_TEST_VOLUME=owned-data\n",
        "backups/status-sentinel.dump": b"synthetic-backup-bytes",
    }
    for relative_path, content in protected_files.items():
        path = worktree / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    marker = worktree / live_stand.STAND_FILE
    vapid = worktree / live_stand.VAPID_FILE
    marker_before = marker.read_bytes()
    vapid_before = vapid.read_bytes()
    commands: list[list[str]] = []
    environments: list[dict[str, str]] = []

    def capture(command: list[str], *, cwd: Path, env: dict[str, str]) -> str:
        del cwd
        commands.append(list(command))
        environments.append(dict(env or {}))
        return "NAME STATUS\n"

    monkeypatch.setattr(live_stand, "_status_compose_output", capture)
    before_snapshot = live_stand._readonly_status_snapshot(worktree)
    lock_path = worktree.parent / f".{worktree.name}.lifecycle.lock"
    assert not lock_path.exists()

    live_stand.status()

    output = capsys.readouterr().out
    published = dict(owner.published_ports)
    assert f"LIVE_BASE_URL=http://localhost:{published['CADDY_HTTP']}" in output
    assert "LIVE_BASE_URL=https://localhost:" not in output

    assert commands == [
        live_stand.compose_command("ps", project_name=owner.project_name)
    ]
    _assert_compose_port_environment(environments[0], owner.published_ports)
    assert marker.read_bytes() == marker_before
    assert vapid.read_bytes() == vapid_before
    assert live_stand._readonly_status_snapshot(worktree) == before_snapshot
    assert not lock_path.exists()
    assert {
        relative_path: (worktree / relative_path).read_bytes()
        for relative_path in protected_files
    } == protected_files


def test_stop_preserves_owned_volumes_and_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    protected_files = {
        ".env": b"STOP_SENTINEL=keep\n",
        ".env.docker": b"LIVE_TEST_VOLUME=owned-data\n",
        "backups/stop-sentinel.dump": b"synthetic-backup-bytes",
    }
    for relative_path, content in protected_files.items():
        path = worktree / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    commands: list[list[str]] = []
    environments: list[dict[str, str]] = []

    def capture(command: list[str], *, cwd: Path, env: dict[str, str] | None) -> None:
        commands.append(list(command))
        environments.append(dict(env or {}))

    monkeypatch.setattr(live_stand, "_run", capture)

    live_stand.stop()

    assert commands == [
        live_stand.compose_command("stop", project_name=owner.project_name)
    ]
    assert worktree.exists()
    assert not any("--volumes" in command for command in commands)
    _assert_compose_port_environment(environments[0], owner.published_ports)
    assert {
        relative_path: (worktree / relative_path).read_bytes()
        for relative_path in protected_files
    } == protected_files


@pytest.mark.parametrize("operation", ["stop", "teardown"])
def test_destructive_lifecycle_refuses_a_different_docker_daemon(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, operation: str
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    owner_with_daemon = SimpleNamespace(
        project_name=owner.project_name,
        published_ports=owner.published_ports,
        daemon_fingerprint="a" * 64,
    )
    monkeypatch.setattr(live_stand, "_require_worktree", lambda **_kwargs: None)
    monkeypatch.setattr(
        live_stand, "load_stand_owner", lambda _worktree: owner_with_daemon
    )

    def different_daemon_fingerprint(
        *,
        deadline: float | None = None,
        docker_context: live_stand._LiveDockerReadContext | None = None,
    ) -> str:
        assert deadline is None
        assert docker_context is None
        return "b" * 64

    monkeypatch.setattr(
        live_stand,
        "docker_daemon_fingerprint",
        different_daemon_fingerprint,
        raising=False,
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_: commands.append(list(command))
    )

    with pytest.raises(live_stand.StandError, match="different Docker daemon"):
        getattr(live_stand, operation)()

    assert commands == []
    assert worktree.exists()


@pytest.mark.parametrize("operation", ["stop", "teardown"])
def test_destructive_lifecycle_fails_closed_when_daemon_identity_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, operation: str
) -> None:
    worktree, _owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    marker = worktree / live_stand.STAND_FILE
    marker_before = marker.read_bytes()
    commands: list[list[str]] = []

    def unavailable(
        *,
        deadline: float | None = None,
        docker_context: live_stand._LiveDockerReadContext | None = None,
    ) -> str:
        assert deadline is None
        assert docker_context is None
        raise live_stand.StandError("cannot verify Docker daemon identity")

    monkeypatch.setattr(live_stand, "docker_daemon_fingerprint", unavailable)
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_: commands.append(list(command))
    )

    with pytest.raises(live_stand.StandError, match="cannot verify Docker daemon"):
        getattr(live_stand, operation)()

    assert commands == []
    assert marker.read_bytes() == marker_before
    assert worktree.exists()


def test_teardown_removes_only_the_owned_compose_project_and_preserves_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    compose_config_calls: list[tuple[list[str], Path, dict[str, str]]] = []
    worktree, owner, _ = _prepare_owned_stand(
        monkeypatch, tmp_path, compose_config_calls=compose_config_calls
    )
    protected_files = {
        ".env": b"KEEP_ME=1\n",
        ".env.docker": b"LIVE_TEST_VOLUME=owned-data\n",
        "backups/teardown-sentinel.dump": b"synthetic-backup-bytes",
    }
    for relative_path, content in protected_files.items():
        path = worktree / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    commands: list[list[str]] = []
    environments: list[dict[str, str]] = []
    git_calls: list[tuple[str, ...]] = []

    def capture(command: list[str], *, cwd: Path, env: dict[str, str] | None) -> None:
        commands.append(list(command))
        environments.append(dict(env or {}))

    monkeypatch.setattr(live_stand, "_run", capture)
    monkeypatch.setattr(live_stand, "_git", lambda *args: git_calls.append(args) or "")

    live_stand.teardown()

    assert commands == [
        live_stand.compose_command("down", "--volumes", project_name=owner.project_name)
    ]
    assert git_calls == []
    assert worktree.exists()
    assert {
        relative_path: (worktree / relative_path).read_bytes()
        for relative_path in protected_files
    } == protected_files
    _assert_compose_port_environment(environments[0], owner.published_ports)
    assert len(compose_config_calls) == 2
    config_command = live_stand.compose_command(
        "config", "--format", "json", project_name=owner.project_name
    )
    assert [call[0] for call in compose_config_calls] == [
        config_command,
        config_command,
    ]
    assert all(call[1] == worktree for call in compose_config_calls)
    assert all(
        call[2]["COMPOSE_PROJECT_NAME"] == owner.project_name
        for call in compose_config_calls
    )


def test_teardown_refuses_owner_metadata_from_another_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, _, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    marker = worktree / live_stand.STAND_FILE
    data = json.loads(marker.read_text(encoding="utf-8"))
    data["worktree"] = str(tmp_path / "foreign-worktree")
    marker.write_text(json.dumps(data), encoding="utf-8")
    commands: list[list[str]] = []
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_: commands.append(list(command))
    )

    with pytest.raises(live_stand.StandError, match="belongs to another worktree"):
        live_stand.teardown()

    assert commands == []


def test_teardown_refuses_a_project_name_changed_after_owner_creation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    marker = worktree / live_stand.STAND_FILE
    data = json.loads(marker.read_text(encoding="utf-8"))
    data["project_name"] = "ue-live-fedcba9876543210"
    marker.write_text(json.dumps(data), encoding="utf-8")
    commands: list[list[str]] = []
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_: commands.append(list(command))
    )

    with pytest.raises(live_stand.StandError, match="signature"):
        live_stand.teardown()

    assert commands == []
    assert owner.project_name != data["project_name"]


def test_teardown_preflight_rejects_unregistered_anonymous_container_volume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_name = "ue-live-0123456789abcdef"
    managed_volume = f"{project_name}_app-data"
    container_id = "0123456789ab" + "0" * 52
    commands: list[list[str]] = []

    def fake_run(command: Sequence[str], **_: Any) -> subprocess.CompletedProcess[str]:
        normalized = list(command)
        commands.append(normalized)
        if normalized[:4] == ["docker", "volume", "ls", "--format"]:
            return subprocess.CompletedProcess(
                normalized, 0, stdout=f"{managed_volume}\n", stderr=""
            )
        if normalized[:3] == ["docker", "volume", "inspect"]:
            return subprocess.CompletedProcess(
                normalized,
                0,
                stdout=json.dumps(
                    {
                        "com.docker.compose.project": project_name,
                        "com.docker.compose.volume": "app-data",
                    }
                ),
                stderr="",
            )
        if normalized[:3] == ["docker", "ps", "--all"]:
            return subprocess.CompletedProcess(
                normalized, 0, stdout=f"{container_id}\n", stderr=""
            )
        if normalized[:5] == [
            "docker",
            "inspect",
            "--type",
            "container",
            "--format",
        ]:
            return subprocess.CompletedProcess(
                normalized,
                0,
                stdout=json.dumps(
                    {
                        "Id": container_id,
                        "ProjectLabel": project_name,
                        "ServiceLabel": "backend",
                        "OneoffLabel": "False",
                        "Mounts": [
                            {
                                "Type": "volume",
                                "Name": "anonymous-image-volume",
                            }
                        ],
                    }
                ),
                stderr="",
            )
        pytest.fail(f"unexpected fake Docker call: {normalized}")

    monkeypatch.setattr(live_stand.subprocess, "run", fake_run)

    with pytest.raises(live_stand.StandError, match=r"unregistered.*volume"):
        live_stand._assert_compose_volume_ownership(
            project_name,
            [("app-data", managed_volume)],
            allow_existing_owned=True,
            managed_services=["backend"],
            declared_volume_names=[managed_volume],
        )

    assert any(
        "ProjectLabel" in argument for command in commands for argument in command
    )


def _batched_inspect_test_id(value: int) -> str:
    return f"{value:064x}"


def _batched_inspect_test_row(
    container_id: str,
    *,
    project: str = "ue-live-0123456789abcdef",
    service: str = "backend",
    oneoff_label: str | None = "False",
    mounts: list[dict[str, object]] | None = None,
) -> str:
    return json.dumps(
        {
            "Id": container_id,
            "ProjectLabel": project,
            "ServiceLabel": service,
            "OneoffLabel": oneoff_label,
            "Mounts": [] if mounts is None else mounts,
        },
        separators=(",", ":"),
    )


def _stub_batched_inspection(
    monkeypatch: pytest.MonkeyPatch,
    *,
    inventory_output: str,
    inspect_output: Callable[[list[str]], str],
) -> list[list[str]]:
    commands: list[list[str]] = []

    def fake_run(command: Sequence[str], **_: Any) -> subprocess.CompletedProcess[str]:
        normalized = list(command)
        commands.append(normalized)
        if normalized[:4] == ["docker", "ps", "--all", "--quiet"]:
            return subprocess.CompletedProcess(
                normalized, 0, stdout=inventory_output, stderr=""
            )
        if normalized[:5] == [
            "docker",
            "inspect",
            "--type",
            "container",
            "--format",
        ]:
            return subprocess.CompletedProcess(
                normalized, 0, stdout=inspect_output(normalized), stderr=""
            )
        pytest.fail("unexpected Docker command")

    monkeypatch.setattr(live_stand.subprocess, "run", fake_run)
    return commands


def test_compose_container_ownership_uses_bounded_full_id_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_name = "ue-live-0123456789abcdef"
    managed_volume = f"{project_name}_app-data"
    container_ids = tuple(_batched_inspect_test_id(index) for index in range(1, 66))
    inspected_ids: list[str] = []

    def inspect_output(command: list[str]) -> str:
        batch_ids = command[6:]
        inspected_ids.extend(batch_ids)
        template = command[5]
        assert "Config.Env" not in template
        assert ".Source" not in template
        assert "Destination" not in template
        rows: list[str] = []
        for container_id in batch_ids:
            mounts: list[dict[str, object]] = []
            if container_id == container_ids[0]:
                mounts = [{"Type": "volume", "Name": managed_volume}]
            elif container_id in container_ids[1:3]:
                mount_type = "bind" if container_id == container_ids[1] else "tmpfs"
                mounts = [{"Type": mount_type, "Name": None}]
            rows.append(
                _batched_inspect_test_row(
                    container_id, project=project_name, mounts=mounts
                )
            )
        return "\n".join(rows) + "\n"

    commands = _stub_batched_inspection(
        monkeypatch,
        inventory_output="\n".join(container_ids) + "\n",
        inspect_output=inspect_output,
    )

    assert (
        live_stand._assert_compose_volume_ownership(
            project_name,
            (),
            declared_volume_names=(managed_volume,),
            allow_existing_owned=True,
            managed_services=("backend",),
        )
        == ()
    )

    inspect_commands = [command for command in commands if command[1] == "inspect"]
    assert [command[6:] for command in inspect_commands] == [
        list(container_ids[:64]),
        list(container_ids[64:]),
    ]
    assert inspected_ids == list(container_ids)
    assert all("--no-trunc" in command for command in commands if command[1] == "ps")


def test_compose_container_ownership_rejects_incomplete_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_name = "ue-live-0123456789abcdef"
    container_ids = tuple(_batched_inspect_test_id(index) for index in range(100, 165))
    inspect_calls = 0

    def missing_batch(command: list[str]) -> str:
        nonlocal inspect_calls
        inspect_calls += 1
        if inspect_calls == 1:
            return (
                "\n".join(
                    _batched_inspect_test_row(item, project=project_name)
                    for item in command[6:]
                )
                + "\n"
            )
        return ""

    _stub_batched_inspection(
        monkeypatch,
        inventory_output="\n".join(container_ids) + "\n",
        inspect_output=missing_batch,
    )
    with pytest.raises(
        live_stand.StandError,
        match="cannot verify existing live stand Docker container ownership",
    ):
        live_stand._assert_compose_volume_ownership(
            project_name,
            (),
            declared_volume_names=(),
            allow_existing_owned=True,
            managed_services=("backend",),
        )
    assert inspect_calls == 2


def test_compose_container_ownership_rejects_duplicate_json_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_name = "ue-live-0123456789abcdef"
    container_id = _batched_inspect_test_id(501)
    duplicate_id_row = (
        '{"Id":"'
        + container_id
        + '","Id":"'
        + container_id
        + '","ProjectLabel":"'
        + project_name
        + '","ServiceLabel":"backend","OneoffLabel":"False","Mounts":[]}\n'
    )
    _stub_batched_inspection(
        monkeypatch,
        inventory_output=container_id + "\n",
        inspect_output=lambda _command: duplicate_id_row,
    )

    with pytest.raises(
        live_stand.StandError,
        match="cannot verify existing live stand Docker container ownership",
    ):
        live_stand._assert_compose_volume_ownership(
            project_name,
            (),
            declared_volume_names=(),
            allow_existing_owned=True,
            managed_services=("backend",),
        )


@pytest.mark.parametrize(
    ("service", "volume", "error"),
    [
        ("foreign-service", "ue-live-0123456789abcdef_app-data", "not owned"),
        ("backend", "unregistered-volume", "unregistered.*volume"),
    ],
)
def test_compose_container_ownership_preserves_service_and_volume_guards(
    monkeypatch: pytest.MonkeyPatch,
    service: str,
    volume: str,
    error: str,
) -> None:
    project_name = "ue-live-0123456789abcdef"
    container_id = _batched_inspect_test_id(701)
    row = _batched_inspect_test_row(
        container_id,
        project=project_name,
        service=service,
        mounts=[{"Type": "volume", "Name": volume}],
    )
    _stub_batched_inspection(
        monkeypatch,
        inventory_output=container_id + "\n",
        inspect_output=lambda _command: row + "\n",
    )

    with pytest.raises(live_stand.StandError, match=error):
        live_stand._assert_compose_volume_ownership(
            project_name,
            (),
            declared_volume_names=(f"{project_name}_app-data",),
            allow_existing_owned=True,
            managed_services=("backend",),
        )


def test_first_compose_start_rejects_container_before_inspect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_name = "ue-live-0123456789abcdef"
    container_id = _batched_inspect_test_id(901)
    commands = _stub_batched_inspection(
        monkeypatch,
        inventory_output=container_id + "\n",
        inspect_output=lambda _command: pytest.fail(
            "first start must reject before container inspection"
        ),
    )

    with pytest.raises(
        live_stand.StandError,
        match="already exists before its first Compose startup",
    ):
        live_stand._assert_compose_volume_ownership(
            project_name,
            (),
            declared_volume_names=(),
            allow_existing_owned=False,
            managed_services=("backend",),
        )
    assert len(commands) == 1
    assert "--no-trunc" in commands[0]


def test_compose_container_ownership_rejects_abbreviated_inventory_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands = _stub_batched_inspection(
        monkeypatch,
        inventory_output="0123456789ab\n",
        inspect_output=lambda _command: pytest.fail(
            "an abbreviated ID must fail before inspect"
        ),
    )

    with pytest.raises(live_stand.StandError, match="container inventory is ambiguous"):
        live_stand._assert_compose_volume_ownership(
            "ue-live-0123456789abcdef",
            (),
            declared_volume_names=(),
            allow_existing_owned=True,
            managed_services=("backend",),
        )
    assert len(commands) == 1
    assert "--no-trunc" in commands[0]


def test_lifecycle_lock_serializes_competing_operations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree = tmp_path / "ue-live"
    worktree.mkdir()
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    first_acquired = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    second_acquired = threading.Event()

    def hold_lock() -> None:
        with live_stand.stand_lifecycle_lock():
            first_acquired.set()
            assert release_first.wait(timeout=2)

    def wait_for_lock() -> None:
        second_started.set()
        with live_stand.stand_lifecycle_lock():
            second_acquired.set()

    first = threading.Thread(target=hold_lock)
    second = threading.Thread(target=wait_for_lock)
    first.start()
    assert first_acquired.wait(timeout=2)
    second.start()
    assert second_started.wait(timeout=2)
    assert not second_acquired.wait(timeout=0.1)
    release_first.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert second_acquired.is_set()


def test_ensure_worktree_rejects_ref_without_live_overlay(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree = tmp_path / "ue-live"
    worktree_calls: list[tuple[str, ...]] = []

    def fake_git(*args: str) -> str:
        worktree_calls.append(args)
        if args[0] == "rev-parse":
            return "abc123"
        if args[0] == "cat-file":
            raise subprocess.CalledProcessError(1, ["git", *args])
        return ""

    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "_git", fake_git)

    with pytest.raises(live_stand.StandError, match="does not contain"):
        live_stand.ensure_worktree("bad-ref")

    assert not worktree.exists()
    assert not any(args[0] == "worktree" for args in worktree_calls)


def test_in_place_up_uses_owned_temp_state_without_git_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "docker-compose.full.yml").write_text(
        "services: {}\n", encoding="utf-8"
    )
    (repository / live_stand.OVERLAY).write_text("services: {}\n", encoding="utf-8")
    temporal_root = repository / "services" / "temporal"
    temporal_root.mkdir(parents=True)
    (temporal_root / "config.yaml").write_text("global: {}\n", encoding="utf-8")
    (temporal_root / "entrypoint.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    temporary_root = tmp_path / "temp"
    temporary_root.mkdir()
    state_parent = temporary_root / "ue-live-acceptance"
    state_root = state_parent / "run-36854541120"
    resolved_sha = "a" * 40
    git_calls: list[tuple[str, ...]] = []
    commands: list[tuple[list[str], Path, dict[str, str] | None]] = []

    def fake_git(*args: str) -> str:
        git_calls.append(args)
        if args == ("rev-parse", "--verify", "HEAD^{commit}"):
            return resolved_sha
        if args == ("cat-file", "-e", f"{resolved_sha}:{live_stand.OVERLAY}"):
            return ""
        if args == ("rev-parse", "HEAD"):
            return resolved_sha
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return ""
        if args[:4] == ("ls-files", "--others", "--ignored", "--exclude-standard"):
            return ""
        pytest.fail(f"unexpected git command: {args}")

    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", repository.parent / "ue-live")
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)
    monkeypatch.setattr(live_stand, "SOURCE_SHA", None)
    monkeypatch.setattr(live_stand.tempfile, "gettempdir", lambda: str(temporary_root))
    monkeypatch.setattr(live_stand, "_git", fake_git)
    monkeypatch.setattr(live_stand, "stand_lifecycle_lock", nullcontext)
    monkeypatch.setattr(
        live_stand,
        "ensure_worktree",
        lambda _ref: pytest.fail("in-place mode must not create or switch a worktree"),
    )
    monkeypatch.setattr(live_stand, "docker_daemon_fingerprint", lambda: "d" * 64)
    monkeypatch.setattr(live_stand, "choose_published_ports", lambda: _port_map(30000))
    monkeypatch.setattr(live_stand, "require_free_ports", lambda _ports: None)
    monkeypatch.setattr(
        live_stand,
        "load_or_create_vapid",
        lambda _root: {"public": "synthetic-public", "private": "synthetic-private"},
    )
    real_which = live_stand.shutil.which
    monkeypatch.setattr(
        live_stand.shutil,
        "which",
        lambda name: "pwsh" if name == "pwsh" else real_which(name),
    )
    monkeypatch.setattr(
        live_stand,
        "_bind_stand_owner_compose_resources",
        lambda root, owner, **_kwargs: live_stand.update_stand_owner_ports(
            root, owner, dict(owner.published_ports)
        ),
    )
    monkeypatch.setattr(
        live_stand,
        "_verify_stand_owner_compose_resources",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(live_stand, "_require_owned_docker_daemon", lambda _owner: None)

    def configure_trusted_proxy_peers(
        owner: live_stand.StandOwner,
        _environment: dict[str, str],
        _evidence: live_stand.ComposeResourceEvidence | None,
    ) -> int:
        assert owner.source_sha == resolved_sha
        assert live_stand.SOURCE_SHA == resolved_sha
        return 0

    monkeypatch.setattr(
        live_stand,
        "_configure_live_trusted_proxy_peers",
        configure_trusted_proxy_peers,
    )

    def capture(
        command: list[str], *, cwd: Path, env: dict[str, str] | None = None
    ) -> None:
        commands.append((command, cwd, env))

    monkeypatch.setattr(live_stand, "_run", capture)

    result = live_stand.main(
        ["up", "--in-place", "--state-dir", str(state_root), "--ref", "HEAD"]
    )

    assert result == 0
    assert all("worktree" not in args and "checkout" not in args for args in git_calls)
    owner_marker = json.loads(
        (state_root / live_stand.STAND_FILE).read_text(encoding="utf-8")
    )
    assert owner_marker["version"] == live_stand.IN_PLACE_OWNER_SCHEMA_VERSION
    assert owner_marker["repository"] == str(repository.resolve())
    assert owner_marker["worktree"] == str(state_root.resolve())
    assert owner_marker["source_sha"] == resolved_sha
    assert (state_root / ".secrets" / "live-stand-owner.key").is_file()
    assert (state_root / "docker-compose.live-state.yml").is_file()
    state_override = (state_root / live_stand.IN_PLACE_OVERLAY).read_text(
        encoding="utf-8"
    )
    assert "minio:" not in state_override
    assert (state_root / ".env.docker").as_posix() in state_override
    assert (state_root / ".env.docker.workers").as_posix() in state_override
    assert "volumes: !override" in state_override
    assert "static-data:/app/app/static" in state_override
    assert (
        f'source: "{(state_root / ".secrets" / "jwt_rs256.pem").as_posix()}"'
        in state_override
    )
    assert (
        f'source: "{(state_root / ".secrets" / "jwt_rs256.pub.pem").as_posix()}"'
        in state_override
    )
    assert (
        f'source: "{(state_root / ".secrets" / "temporal_api_key").as_posix()}"'
        in state_override
    )
    assert (
        f'source: "{(repository / "services" / "temporal" / "config.yaml").as_posix()}"'
        in state_override
    )
    assert (
        f'source: "{(repository / "services" / "temporal" / "entrypoint.sh").as_posix()}"'
        in state_override
    )
    assert "volumes: !override []" not in state_override
    assert "/app/.secrets:ro" not in state_override
    assert "live-vapid.json" not in state_override
    assert "live-admin-password.json" not in state_override
    assert "synthetic-public" not in state_override
    assert "synthetic-private" not in state_override
    bind_sources = set(
        re.findall(r'^\s+source: "([^"]+)"$', state_override, re.MULTILINE)
    )
    assert bind_sources == {
        (state_root / ".secrets" / "jwt_rs256.pem").as_posix(),
        (state_root / ".secrets" / "jwt_rs256.pub.pem").as_posix(),
        (state_root / ".secrets" / "temporal_api_key").as_posix(),
        (repository / "services" / "temporal" / "config.yaml").as_posix(),
        (repository / "services" / "temporal" / "entrypoint.sh").as_posix(),
    }
    assert not (repository / ".env").exists()
    assert not (repository / ".env.docker").exists()
    assert not (repository / ".secrets").exists()
    assert commands[0][1] == state_root
    assert "-LiveStandStateRoot" in commands[0][0]
    assert str(state_root) in commands[0][0]
    assert commands[-1][1] == state_root
    if os.name == "nt":
        current_user_sid = live_stand._windows_user_sid()
        for protected_path in (
            state_root,
            state_root / ".secrets",
            state_root / ".secrets" / "live-stand-owner.key",
            state_root / live_stand.STAND_FILE,
            state_root / live_stand.IN_PLACE_OVERLAY,
        ):
            acl = _windows_acl_summary(protected_path)
            assert acl["OwnerSid"] == current_user_sid
            rules = acl["Rules"]
            assert isinstance(rules, list)
            allow_rules = [rule for rule in rules if rule["Type"] == "Allow"]
            assert {rule["Sid"] for rule in allow_rules} == {
                current_user_sid,
                "S-1-5-18",
            }
            assert all("FullControl" in rule["Rights"] for rule in allow_rules)
        for protected_directory in (state_root, state_root / ".secrets"):
            acl = _windows_acl_summary(protected_directory)
            rules = acl["Rules"]
            assert isinstance(rules, list)
            allow_rules = [rule for rule in rules if rule["Type"] == "Allow"]
            assert all(
                "ContainerInherit" in rule["Inheritance"]
                and "ObjectInherit" in rule["Inheritance"]
                for rule in allow_rules
            )
    else:
        assert stat.S_IMODE(state_parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(state_root.stat().st_mode) == 0o700
        assert stat.S_IMODE((state_root / ".secrets").stat().st_mode) == 0o700
        assert (
            stat.S_IMODE(
                (state_root / ".secrets" / "live-stand-owner.key").stat().st_mode
            )
            == 0o600
        )
        assert (
            stat.S_IMODE((state_root / live_stand.STAND_FILE).stat().st_mode) == 0o600
        )
        assert (
            stat.S_IMODE((state_root / live_stand.IN_PLACE_OVERLAY).stat().st_mode)
            == 0o600
        )


def test_in_place_compose_override_does_not_store_secret_contents(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    temporal_root = repository / "services" / "temporal"
    temporal_root.mkdir(parents=True)
    (temporal_root / "config.yaml").write_text("global: {}\n", encoding="utf-8")
    (temporal_root / "entrypoint.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    state_root = tmp_path / "temp" / "ue-live-acceptance" / "run-sentinel-case"
    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", state_root)
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", True)
    live_stand._ensure_private_state_directory(state_root, protect_new_windows=True)
    secrets_root = state_root / ".secrets"
    live_stand._ensure_private_state_directory(secrets_root, protect_new_windows=True)
    sentinels = (
        "sentinel-private-env-content",
        "sentinel-worker-env-content",
        "sentinel-jwt-private-key-content",
        "sentinel-jwt-public-key-content",
        "sentinel-temporal-token-content",
    )
    for path, sentinel in zip(
        (
            state_root / ".env.docker",
            state_root / ".env.docker.workers",
            secrets_root / "jwt_rs256.pem",
            secrets_root / "jwt_rs256.pub.pem",
            secrets_root / "temporal_api_key",
        ),
        sentinels,
        strict=True,
    ):
        path.write_text(sentinel, encoding="utf-8")

    override = live_stand._write_in_place_compose_override(state_root)

    content = override.read_text(encoding="utf-8")
    assert all(sentinel not in content for sentinel in sentinels)
    assert state_root.as_posix() in content
    assert "jwt_rs256.pem" in content
    assert "temporal_api_key" in content


def test_in_place_status_stop_and_teardown_preserve_runroot_and_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "docker-compose.full.yml").write_text(
        "services: {}\n", encoding="utf-8"
    )
    (repository / live_stand.OVERLAY).write_text("services: {}\n", encoding="utf-8")
    temporary_root = tmp_path / "temp"
    state_root = temporary_root / live_stand.IN_PLACE_STATE_PARENT / "run-safety-case"
    state_root.mkdir(parents=True)
    if os.name != "nt":
        state_root.chmod(0o700)
    (state_root / live_stand.IN_PLACE_OVERLAY).write_text(
        "services: {}\n", encoding="utf-8"
    )
    source_sha = "a" * 40
    commands: list[tuple[list[str], Path, dict[str, str] | None]] = []
    resource_verifications: list[Path] = []
    git_calls: list[tuple[str, ...]] = []

    def fake_git(*args: str) -> str:
        git_calls.append(args)
        if args == ("rev-parse", "HEAD"):
            return source_sha
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return " M app/main.py"
        if args[:4] == ("ls-files", "--others", "--ignored", "--exclude-standard"):
            return "frontend/reports/generated.json"
        pytest.fail(f"unexpected git command: {args}")

    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", state_root)
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", True)
    monkeypatch.setattr(live_stand, "SOURCE_SHA", source_sha)
    monkeypatch.setattr(live_stand, "_git", fake_git)
    monkeypatch.setattr(live_stand, "stand_lifecycle_lock", nullcontext)
    monkeypatch.setattr(live_stand, "docker_daemon_fingerprint", lambda: "d" * 64)
    monkeypatch.setattr(live_stand, "_require_owned_docker_daemon", lambda _owner: None)
    monkeypatch.setattr(
        live_stand,
        "_verify_stand_owner_compose_resources",
        lambda root, *_args, **_kwargs: resource_verifications.append(root),
    )
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, *, cwd, env=None: commands.append((list(command), cwd, env)),
    )
    monkeypatch.setattr(
        live_stand,
        "_status_compose_output",
        lambda command, *, cwd, env: (
            commands.append((list(command), cwd, env)) or "NAME STATUS\n"
        ),
    )

    owner = live_stand.create_stand_owner(state_root, published_ports=_port_map(32000))
    complete_owner = live_stand.StandOwner(
        **{
            **owner.__dict__,
            "compose_resource_fingerprint": "e" * 64,
            "service_roots": ("backend",),
            "selected_services": ("backend",),
        }
    )
    live_stand._write_stand_owner_update(state_root, complete_owner)

    def snapshot(root: Path) -> dict[str, bytes]:
        return {
            str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

    before_state = snapshot(state_root)
    before_source = snapshot(repository)
    lock_path = state_root.parent / f".{state_root.name}.lifecycle.lock"
    assert not lock_path.exists()

    live_stand.status()
    assert snapshot(state_root) == before_state
    assert snapshot(repository) == before_source
    assert "--project-directory" in commands[-1][0]
    assert str(repository.resolve()) in commands[-1][0]
    assert str((state_root / ".env.docker").resolve()) in commands[-1][0]
    assert str((state_root / live_stand.IN_PLACE_OVERLAY).resolve()) in commands[-1][0]
    assert not lock_path.exists()

    live_stand.stop()
    assert commands[-1][0][-1] == "stop"
    assert snapshot(state_root) == before_state
    assert snapshot(repository) == before_source

    live_stand.teardown()
    assert commands[-1][0][-2:] == ["down", "--volumes"]
    assert snapshot(state_root) == before_state
    assert snapshot(repository) == before_source
    assert repository.is_dir() and state_root.is_dir()
    assert git_calls == []
    assert resource_verifications == [state_root, state_root, state_root]


def test_in_place_mode_rejects_state_path_outside_owned_temp_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    temporary_root = tmp_path / "temp"
    temporary_root.mkdir()
    outside = tmp_path / "unowned" / "run-outside"
    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand.tempfile, "gettempdir", lambda: str(temporary_root))
    monkeypatch.setattr(live_stand, "WORKTREE", repository.parent / "ue-live")
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)
    monkeypatch.setattr(live_stand, "SOURCE_SHA", None)
    monkeypatch.setattr(
        live_stand,
        "_git",
        lambda *_args: pytest.fail("invalid state path must fail before git access"),
    )

    result = live_stand.main(
        ["up", "--in-place", "--state-dir", str(outside), "--ref", "HEAD"]
    )

    assert result == 2
    assert not outside.exists()
    assert not (repository / ".env").exists()
    assert not (repository / ".secrets").exists()


def test_in_place_up_rejects_dirty_source_before_creating_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / live_stand.OVERLAY).write_text("services: {}\n", encoding="utf-8")
    temporary_root = tmp_path / "temp"
    temporary_root.mkdir()
    state_root = temporary_root / live_stand.IN_PLACE_STATE_PARENT / "run-dirty-source"
    source_sha = "a" * 40

    def fake_git(*args: str) -> str:
        if args == ("rev-parse", "--verify", "HEAD^{commit}"):
            return source_sha
        if args == ("cat-file", "-e", f"{source_sha}:{live_stand.OVERLAY}"):
            return ""
        if args == ("rev-parse", "HEAD"):
            return source_sha
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return " M scripts/live_stand.py"
        pytest.fail(f"unexpected git command: {args}")

    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", repository.parent / "ue-live")
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)
    monkeypatch.setattr(live_stand, "SOURCE_SHA", None)
    monkeypatch.setattr(live_stand.tempfile, "gettempdir", lambda: str(temporary_root))
    monkeypatch.setattr(live_stand, "_git", fake_git)
    monkeypatch.setattr(live_stand, "stand_lifecycle_lock", nullcontext)
    monkeypatch.setattr(
        live_stand,
        "choose_published_ports",
        lambda: pytest.fail("dirty source must be rejected before allocating ports"),
    )

    result = live_stand.main(
        ["up", "--in-place", "--state-dir", str(state_root), "--ref", "HEAD"]
    )

    assert result == 2
    assert not state_root.exists()


def test_in_place_up_rejects_untracked_app_source_before_creating_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    app_source = repository / "app" / "new_module.py"
    app_source.parent.mkdir(parents=True)
    app_source.write_text("SOURCE_SENTINEL = True\n", encoding="utf-8")
    (repository / live_stand.OVERLAY).write_text("services: {}\n", encoding="utf-8")
    temporary_root = tmp_path / "temp"
    temporary_root.mkdir()
    state_root = (
        temporary_root / live_stand.IN_PLACE_STATE_PARENT / "run-untracked-source"
    )
    source_sha = "a" * 40

    def fake_git(*args: str) -> str:
        if args == ("rev-parse", "--verify", "HEAD^{commit}"):
            return source_sha
        if args == ("cat-file", "-e", f"{source_sha}:{live_stand.OVERLAY}"):
            return ""
        if args == ("rev-parse", "HEAD"):
            return source_sha
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return "?? app/new_module.py"
        pytest.fail(f"unexpected git command: {args}")

    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", repository.parent / "ue-live")
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)
    monkeypatch.setattr(live_stand, "SOURCE_SHA", None)
    monkeypatch.setattr(live_stand.tempfile, "gettempdir", lambda: str(temporary_root))
    monkeypatch.setattr(live_stand, "_git", fake_git)
    monkeypatch.setattr(live_stand, "stand_lifecycle_lock", nullcontext)
    monkeypatch.setattr(
        live_stand,
        "choose_published_ports",
        lambda: pytest.fail(
            "untracked app source must be rejected before port allocation"
        ),
    )

    result = live_stand.main(
        ["up", "--in-place", "--state-dir", str(state_root), "--ref", "HEAD"]
    )

    assert result == 2
    assert app_source.read_text(encoding="utf-8") == "SOURCE_SENTINEL = True\n"
    assert not state_root.exists()


def test_in_place_up_rejects_ignored_app_source_before_creating_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    app_source = repository / "app" / "local_settings.py"
    app_source.parent.mkdir(parents=True)
    app_source.write_text("PRIVATE_SENTINEL = True\n", encoding="utf-8")
    (repository / live_stand.OVERLAY).write_text("services: {}\n", encoding="utf-8")
    temporary_root = tmp_path / "temp"
    temporary_root.mkdir()
    state_root = (
        temporary_root / live_stand.IN_PLACE_STATE_PARENT / "run-ignored-source"
    )
    source_sha = "a" * 40
    git_calls: list[tuple[str, ...]] = []

    def fake_git(*args: str) -> str:
        git_calls.append(args)
        if args == ("rev-parse", "--verify", "HEAD^{commit}"):
            return source_sha
        if args == ("cat-file", "-e", f"{source_sha}:{live_stand.OVERLAY}"):
            return ""
        if args == ("rev-parse", "HEAD"):
            return source_sha
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return ""
        if args[:4] == ("ls-files", "--others", "--ignored", "--exclude-standard"):
            return "app/local_settings.py"
        pytest.fail(f"unexpected git command: {args}")

    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", repository.parent / "ue-live")
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)
    monkeypatch.setattr(live_stand, "SOURCE_SHA", None)
    monkeypatch.setattr(live_stand.tempfile, "gettempdir", lambda: str(temporary_root))
    monkeypatch.setattr(live_stand, "_git", fake_git)
    monkeypatch.setattr(live_stand, "stand_lifecycle_lock", nullcontext)
    monkeypatch.setattr(
        live_stand,
        "choose_published_ports",
        lambda: pytest.fail(
            "ignored app source must be rejected before allocating ports"
        ),
    )

    result = live_stand.main(
        ["up", "--in-place", "--state-dir", str(state_root), "--ref", "HEAD"]
    )

    assert result == 2
    assert app_source.read_text(encoding="utf-8") == "PRIVATE_SENTINEL = True\n"
    assert not state_root.exists()
    assert ("status", "--porcelain", "--untracked-files=normal") in git_calls
    assert any(
        args[:4] == ("ls-files", "--others", "--ignored", "--exclude-standard")
        for args in git_calls
    )


def test_in_place_source_current_rejects_untracked_app_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    app_source = repository / "app" / "untracked_module.py"
    app_source.parent.mkdir(parents=True)
    app_source.write_text("SOURCE_SENTINEL = True\n", encoding="utf-8")
    source_sha = "a" * 40
    git_calls: list[tuple[str, ...]] = []

    def fake_git(*args: str) -> str:
        git_calls.append(args)
        if args == ("rev-parse", "HEAD"):
            return source_sha
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return "?? app/untracked_module.py"
        pytest.fail(f"unexpected git command: {args}")

    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "_git", fake_git)

    with pytest.raises(live_stand.StandError, match="modified or untracked"):
        live_stand._assert_in_place_source_current(
            live_stand.StandOwner(
                repository=str(repository),
                worktree=str(tmp_path / "owned-run"),
                project_name="ue-live-untracked",
                published_ports=_port_map(34000),
                schema_version=live_stand.IN_PLACE_OWNER_SCHEMA_VERSION,
                source_sha=source_sha,
            )
        )

    assert git_calls == [
        ("rev-parse", "HEAD"),
        ("status", "--porcelain", "--untracked-files=normal"),
    ]


def test_in_place_source_current_rejects_ignored_app_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    app_source = repository / "app" / "local_settings.py"
    app_source.parent.mkdir(parents=True)
    app_source.write_text("PRIVATE_SENTINEL = True\n", encoding="utf-8")
    source_sha = "a" * 40
    git_calls: list[tuple[str, ...]] = []

    def fake_git(*args: str) -> str:
        git_calls.append(args)
        if args == ("rev-parse", "HEAD"):
            return source_sha
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return ""
        if args[:4] == ("ls-files", "--others", "--ignored", "--exclude-standard"):
            return "app/local_settings.py"
        pytest.fail(f"unexpected git command: {args}")

    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "_git", fake_git)

    with pytest.raises(live_stand.StandError, match="ignored untracked files"):
        live_stand._assert_in_place_source_current(
            live_stand.StandOwner(
                repository=str(repository),
                worktree=str(tmp_path / "owned-run"),
                project_name="ue-live-ignored-source",
                published_ports=_port_map(34000),
                schema_version=live_stand.IN_PLACE_OWNER_SCHEMA_VERSION,
                source_sha=source_sha,
            )
        )

    assert git_calls[:2] == [
        ("rev-parse", "HEAD"),
        ("status", "--porcelain", "--untracked-files=normal"),
    ]
    ignored_source_query = git_calls[2]
    assert ignored_source_query[:7] == (
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "--directory",
        "--no-empty-directory",
        "--",
    )
    assert set(live_stand.IN_PLACE_BUILD_SOURCE_PATHS).issubset(ignored_source_query)
    assert any("node_modules" in item for item in ignored_source_query)
    assert "app" in ignored_source_query
    assert ":(exclude,glob)frontend/coverage/**" in ignored_source_query


def test_in_place_source_guard_exclusions_match_dockerignore_rules() -> None:
    dockerignore = live_stand.REPO_ROOT / ".dockerignore"
    rules = set(dockerignore.read_text(encoding="utf-8").splitlines())

    assert set(live_stand.IN_PLACE_DOCKERIGNORE_ARTIFACT_RULES).issubset(rules)
    for pattern in live_stand.IN_PLACE_DOCKERIGNORE_EXCLUSIONS:
        dockerignore_rule = pattern[:-2] if pattern.endswith("/**") else pattern
        assert dockerignore_rule in rules, pattern


@pytest.mark.parametrize(
    "relative_source",
    [
        "app/coverage/untracked_module.py",
        "app/test-results/untracked_module.py",
        "app/playwright-report/untracked_module.py",
        "app/.vitest/untracked_module.py",
        "app/.venv/untracked_module.py",
        "app/.pytest_cache/untracked_module.py",
    ],
)
def test_in_place_source_guard_rejects_ignored_nested_source_not_dockerignored(
    git_executable: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relative_source: str,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".gitignore").write_text(
        "coverage/\ntest-results/\nplaywright-report/\n.vitest/\n"
        ".venv/\n.pytest_cache/\n__pycache__/\n",
        encoding="utf-8",
    )
    (repository / ".dockerignore").write_text(
        "frontend/coverage/\n"
        "frontend/test-results/\n"
        "frontend/playwright-report/\n"
        "frontend/.vitest/\n"
        "frontend/reports/\n"
        "**/__pycache__/\n",
        encoding="utf-8",
    )
    _initialize_git_repository(git_executable, repository)
    ignored_source = repository / relative_source
    ignored_source.parent.mkdir(parents=True)
    ignored_source.write_text("SOURCE_SENTINEL = True\n", encoding="utf-8")
    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)

    with pytest.raises(live_stand.StandError, match="ignored untracked files"):
        live_stand._assert_no_ignored_in_place_build_sources()


def test_in_place_source_guard_allows_exact_ignored_frontend_artifact(
    git_executable: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".gitignore").write_text("frontend/reports/\n", encoding="utf-8")
    (repository / ".dockerignore").write_text("frontend/reports/\n", encoding="utf-8")
    _initialize_git_repository(git_executable, repository)
    reports = repository / "frontend" / "reports"
    reports.mkdir(parents=True)
    (reports / "generated-summary.html").write_text("local report\n", encoding="utf-8")
    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)

    live_stand._assert_no_ignored_in_place_build_sources()


def test_in_place_source_guard_allows_nested_python_bytecode_cache(
    git_executable: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    (repository / ".dockerignore").write_text("**/__pycache__/\n", encoding="utf-8")
    _initialize_git_repository(git_executable, repository)
    bytecode_cache = repository / "app" / "__pycache__"
    bytecode_cache.mkdir(parents=True)
    (bytecode_cache / "generated.pyc").write_bytes(b"synthetic bytecode")
    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)

    live_stand._assert_no_ignored_in_place_build_sources()


def test_in_place_up_refuses_owned_runroot_from_another_source_sha(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / live_stand.OVERLAY).write_text("services: {}\n", encoding="utf-8")
    state_root = tmp_path / "temp" / live_stand.IN_PLACE_STATE_PARENT / "run-old-source"
    state_root.mkdir(parents=True)
    (state_root / live_stand.IN_PLACE_OVERLAY).write_text(
        "services: {}\n", encoding="utf-8"
    )
    original_sha = "a" * 40
    current_sha = "b" * 40
    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", state_root)
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", True)
    monkeypatch.setattr(live_stand, "SOURCE_SHA", original_sha)
    monkeypatch.setattr(live_stand, "docker_daemon_fingerprint", lambda: "d" * 64)
    owner = live_stand.create_stand_owner(state_root, published_ports=_port_map(33000))
    marker_before = (state_root / live_stand.STAND_FILE).read_bytes()

    def fake_git(*args: str) -> str:
        if args in {
            ("rev-parse", "--verify", "HEAD^{commit}"),
            ("rev-parse", "HEAD"),
        }:
            return current_sha
        if args == ("cat-file", "-e", f"{current_sha}:{live_stand.OVERLAY}"):
            return ""
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return ""
        if args[:4] == ("ls-files", "--others", "--ignored", "--exclude-standard"):
            return ""
        pytest.fail(f"unexpected git command: {args}")

    monkeypatch.setattr(live_stand, "_git", fake_git)
    monkeypatch.setattr(live_stand, "resolve_stand_ref", lambda _ref: current_sha)
    monkeypatch.setattr(
        live_stand,
        "choose_published_ports",
        lambda: pytest.fail("different source owner must fail before port allocation"),
    )
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda *_args, **_kwargs: pytest.fail(
            "different source owner must not stop or start"
        ),
    )

    with pytest.raises(live_stand.StandError, match="different source SHA"):
        live_stand._up_locked("HEAD")

    assert owner.source_sha == original_sha
    assert (state_root / live_stand.STAND_FILE).read_bytes() == marker_before


def test_up_validates_ref_before_stopping_existing_stand(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, _, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    marker_before = (worktree / live_stand.STAND_FILE).read_bytes()
    commands: list[list[str]] = []

    def invalid_ref(*args: str) -> str:
        raise subprocess.CalledProcessError(1, ["git", *args])

    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "_git", invalid_ref)
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_: commands.append(list(command))
    )

    with pytest.raises(live_stand.StandError, match="invalid or does not contain"):
        live_stand.up("missing-ref")

    assert commands == []
    assert (worktree / live_stand.STAND_FILE).read_bytes() == marker_before


def test_up_refuses_to_stop_an_existing_stand_on_a_different_daemon(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, _owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    marker_path = worktree / live_stand.STAND_FILE
    marker_before = marker_path.read_bytes()
    commands: list[list[str]] = []
    monkeypatch.setattr(live_stand, "resolve_stand_ref", lambda _ref: "resolved-sha")
    monkeypatch.setattr(live_stand, "choose_published_ports", lambda: _port_map(50000))
    monkeypatch.setattr(live_stand, "require_free_ports", lambda _ports: None)
    monkeypatch.setattr(
        live_stand,
        "_git",
        lambda *args: "" if "status" in args else "resolved-sha",
    )

    def different_daemon_fingerprint(
        *,
        deadline: float | None = None,
        docker_context: live_stand._LiveDockerReadContext | None = None,
    ) -> str:
        assert deadline is None
        assert docker_context is None
        return "b" * 64

    monkeypatch.setattr(
        live_stand, "docker_daemon_fingerprint", different_daemon_fingerprint
    )

    def capture_unexpected_compose(command: list[str], **_: Any) -> None:
        commands.append(list(command))
        raise live_stand.StandError("unexpected Compose command")

    monkeypatch.setattr(live_stand, "_run", capture_unexpected_compose)
    monkeypatch.setattr(
        live_stand,
        "ensure_worktree",
        lambda _sha: pytest.fail(
            "worktree must not change when daemon identity differs"
        ),
    )

    with pytest.raises(live_stand.StandError, match="different Docker daemon"):
        live_stand._up_locked("HEAD")

    assert commands == []
    assert marker_path.read_bytes() == marker_before


def test_nats_outage_cli_exposes_owned_state_options(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        live_stand.main(["nats-outage", "--help"])

    assert exit_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "--in-place" in help_text
    assert "--state-dir" in help_text


def test_nats_outage_requires_owned_state_before_state_side_effects(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unexpected_state_configuration(_args: Any) -> None:
        pytest.fail("unavailable NATS runner must not configure owned state")

    monkeypatch.setattr(
        live_stand, "_configure_state_mode", unexpected_state_configuration
    )

    assert live_stand.main(["nats-outage"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        captured.err
        == "live_stand: owned NATS outage requires --in-place and --state-dir\n"
    )


def test_main_reports_stand_errors_with_exit_code_two(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse() -> None:
        raise live_stand.StandError("no stand")

    monkeypatch.setattr(live_stand, "status", refuse)

    assert live_stand.main(["status"]) == 2
    assert "live_stand: no stand" in capsys.readouterr().err


def test_live_overlay_replaces_every_publication_with_loopback_port_variables() -> None:
    source = (ROOT / "docker-compose.live.yml").read_text(encoding="utf-8")
    overlay: dict[str, Any] = yaml.safe_load(
        source.replace("!override", "").replace("!reset", "")
    )
    services = overlay["services"]

    ws_origins = services["ws-hub"]["environment"]["ALLOWED_ORIGINS"]
    assert ws_origins.startswith("${LIVE_BASE_URL:?")
    assert "http://localhost" in ws_origins
    assert "*" not in ws_origins

    expected = {
        name: service["ports"]
        for name, service in services.items()
        if "ports" in service
    }
    assert set(expected) == {
        "backend",
        "frontend",
        "postgres",
        "gateway",
        "ws-hub",
        "temporal",
        "imgproxy",
        "grafana",
        "prometheus",
        "alloy",
        "pyroscope",
        "caddy",
        "mailpit",
        "minio",
    }
    assert source.count("ports: !override") == len(expected)
    assert all(
        port.startswith("127.0.0.1:${")
        for service_ports in expected.values()
        for port in service_ports
    )
    assert expected["minio"] == [
        "127.0.0.1:${LIVE_HOST_PORT_MINIO:?set by scripts/live_stand.py}:9000"
    ]
    assert sum(map(len, expected.values())) == len(live_stand.LIVE_PORT_SPECS)
    assert not any(
        legacy_port in source
        for legacy_port in ("80:80", "443:443", "127.0.0.1:8000:8000")
    )
    for sender in ("backend", "outbox-worker", "notifications-worker"):
        environment = services[sender]["environment"]
        assert environment["SMTP_HOST"] == "mailpit"
        assert environment["VAPID_PRIVATE_KEY"].startswith("${LIVE_VAPID_PRIVATE_KEY:?")
    assert set(services["caddy"]) == {"ports"}


def test_live_overlay_keeps_base_storage_on_a_project_scoped_volume() -> None:
    source = (ROOT / "docker-compose.live.yml").read_text(encoding="utf-8")
    overlay: dict[str, Any] = yaml.safe_load(
        source.replace("!override", "").replace("!reset", "")
    )

    # The overlay publishes storage only to its owner-bound loopback port. The
    # base service still owns its project-scoped storage volume.
    assert set(overlay["services"]["minio"]) == {"ports"}
    assert overlay["services"]["minio"]["ports"] == [
        "127.0.0.1:${LIVE_HOST_PORT_MINIO:?set by scripts/live_stand.py}:9000"
    ]
    assert "minio-init" not in overlay["services"]
    assert "volumes" not in overlay
    assert "!reset null" not in source
    assert "university_ecosystem_seaweedfs_data" not in source
    assert "quay.io/minio" not in source


def test_up_preflights_every_port_before_stopping_or_building(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    events: list[str] = []
    compose_calls: list[list[str]] = []
    checked_port_maps: list[dict[str, int]] = []
    new_ports = _port_map(50000)

    def check_ports(ports: dict[str, int]) -> None:
        checked_port_maps.append(dict(ports))
        events.append("ports")

    def run(command: list[str], **_: Any) -> None:
        compose_calls.append(list(command))
        if command[-1] == "stop":
            events.append("compose-stop")
        elif "-PrepareOnly" in command:
            events.append("prepare")
        else:
            events.append("build")

    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(
        live_stand,
        "_git",
        lambda *args: "" if "status" in args else "resolved-sha",
    )
    monkeypatch.setattr(live_stand, "_run", run)

    def configure_trusted_proxy_peers(
        owner: live_stand.StandOwner,
        _environment: dict[str, str],
        evidence: live_stand.ComposeResourceEvidence,
    ) -> int:
        assert owner.source_sha is None
        assert live_stand.SOURCE_SHA == "resolved-sha"
        assert evidence.fingerprint == owner.compose_resource_fingerprint
        return 0

    monkeypatch.setattr(
        live_stand,
        "_configure_live_trusted_proxy_peers",
        configure_trusted_proxy_peers,
    )
    monkeypatch.setattr(live_stand, "require_free_ports", check_ports)
    monkeypatch.setattr(live_stand, "choose_published_ports", lambda: new_ports)
    monkeypatch.setattr(
        live_stand,
        "ensure_worktree",
        lambda ref: events.append(f"ensure:{ref}") or "resolved-sha",
    )
    monkeypatch.setattr(live_stand, "stand_environment", lambda *_args: {})
    monkeypatch.setattr(live_stand.shutil, "which", lambda name: "pwsh")

    live_stand.up("HEAD")

    assert events == [
        "ports",
        "compose-stop",
        "ensure:resolved-sha",
        "ports",
        "prepare",
        "build",
    ]
    assert checked_port_maps == [new_ports, new_ports]
    assert compose_calls[0] == live_stand.compose_command(
        "stop", project_name=owner.project_name
    )
    assert compose_calls[1] == [
        "pwsh",
        "-NoProfile",
        "-File",
        "start-docker.ps1",
        "-PrepareOnly",
        "-InitializeTrustedProxyBootstrap",
        "-ExtraCompose",
        live_stand.OVERLAY,
    ]
    assert compose_calls[2] == [
        "pwsh",
        "-NoProfile",
        "-File",
        "start-docker.ps1",
        "-Build",
        "-ExtraCompose",
        live_stand.OVERLAY,
        "-LiveAcceptanceStack",
        owner.stack,
        "-LiveAcceptanceServicesJson",
        json.dumps(owner.selected_services, separators=(",", ":")),
        "-AllowExistingOwnedVolumes",
    ]
    started_owner = live_stand.load_stand_owner(worktree)
    assert dict(started_owner.published_ports) == new_ports
    assert started_owner.compose_resource_fingerprint is not None
    assert started_owner.source_sha is None
    assert live_stand.SOURCE_SHA == "resolved-sha"


def test_up_port_conflict_preserves_the_running_stand_and_never_builds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, _owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    events: list[str] = []
    ports = _port_map(50000)

    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "resolve_stand_ref", lambda _ref: "sha")
    monkeypatch.setattr(live_stand, "choose_published_ports", lambda: ports)
    monkeypatch.setattr(
        live_stand,
        "require_free_ports",
        lambda _ports: (_ for _ in ()).throw(live_stand.StandError("busy ports")),
    )
    monkeypatch.setattr(
        live_stand, "_run", lambda *_args, **_kwargs: events.append("docker")
    )
    monkeypatch.setattr(
        live_stand, "ensure_worktree", lambda *_args: events.append("checkout")
    )

    with pytest.raises(live_stand.StandError, match="busy ports"):
        live_stand._up_locked("HEAD")

    assert events == []


def test_normal_trusted_proxy_source_requires_the_verified_checkout_sha(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    expected_sha = "a" * 40
    git_calls: list[tuple[str, ...]] = []

    def fake_git(*args: str) -> str:
        git_calls.append(args)
        if args == ("-C", str(worktree), "rev-parse", "HEAD"):
            return expected_sha
        if args == (
            "-C",
            str(worktree),
            "status",
            "--porcelain",
            "--untracked-files=no",
        ):
            return ""
        pytest.fail(f"unexpected git command: {args}")

    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)
    monkeypatch.setattr(live_stand, "SOURCE_SHA", None)
    monkeypatch.setattr(live_stand, "_git", fake_git)
    assert owner.source_sha is None
    with pytest.raises(
        live_stand.StandError,
        match="live trusted proxy owner or source identity changed",
    ):
        live_stand._assert_live_trusted_proxy_source_current(owner)
    assert git_calls == []

    monkeypatch.setattr(live_stand, "SOURCE_SHA", expected_sha)
    live_stand._assert_live_trusted_proxy_source_current(owner)
    assert git_calls == [
        ("-C", str(worktree), "rev-parse", "HEAD"),
        ("-C", str(worktree), "status", "--porcelain", "--untracked-files=no"),
    ]

    monkeypatch.setattr(live_stand, "SOURCE_SHA", "b" * 40)
    with pytest.raises(
        live_stand.StandError,
        match="live trusted proxy source identity changed",
    ):
        live_stand._assert_live_trusted_proxy_source_current(owner)


_AUTH_HTTP_DIAG_TEST_OPERATIONS = (
    "profile_read",
    "profile_identity_read",
    "password_settings_register",
    "totp_register",
    "password_change_invalid",
    "password_change_save",
    "totp_recovery_accept",
    "totp_recovery_replay",
    "push_topics_read",
    "push_subscribe",
    "push_topics_initial",
    "push_topics_optout",
    "push_unsubscribe",
    "push_rebind",
    "profile_update_enable",
    "profile_update_start",
    "profile_update_end",
    "profile_update_midnight_start",
    "profile_update_midnight_end",
    "profile_update_disable",
    "student_admin_read",
    "admin_topics_read",
    "admin_account_search",
    "admin_account_delete",
)


def _auth_ui_diag_record(
    *,
    project: str = "desktop",
    scenario: str = "password_current_invalid",
    status: int = 422,
    **overrides: object,
) -> dict[str, object]:
    record: dict[str, object] = {
        "schema": 1,
        "project": project,
        "scenario": scenario,
        "status": status,
        "detailClass": "expected",
        "alertCount": 1,
        "alertCountCapped": False,
        "alertVisible": True,
        "currentFieldInvalid": True if scenario == "password_current_invalid" else None,
        "loginChallenge": None if scenario == "password_current_invalid" else True,
        "pageError": False,
    }
    record.update(overrides)
    return record


def _auth_http_diag_record(
    operation: str = "profile_read",
    *,
    project: str = "desktop",
    status: int | None = None,
    expected_status: int | None = None,
    **overrides: object,
) -> dict[str, object]:
    required_status = (
        403
        if operation == "student_admin_read"
        else 400
        if operation in {"password_change_invalid", "totp_recovery_replay"}
        else 200
    )
    record: dict[str, object] = {
        "schema": 1,
        "project": project,
        "operation": operation,
        "expectedStatus": (
            required_status if expected_status is None else expected_status
        ),
        "status": (
            (500 if required_status == 200 else 200) if status is None else status
        ),
    }
    record.update(overrides)
    return record


def _auth_diag_row(prefix: str, record: dict[str, object], newline: str = "\n") -> str:
    return prefix + json.dumps(record, separators=(",", ":")) + newline


@pytest.mark.parametrize(
    ("project", "scenario", "current_invalid", "login_challenge"),
    [
        ("desktop", "password_current_invalid", True, None),
        ("mobile", "password_current_invalid", False, None),
        ("desktop", "totp_recovery_replay", None, True),
        ("mobile", "totp_recovery_replay", None, False),
    ],
)
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_live_playwright_auth_ui_parser_accepts_exact_failure_records(
    project: str,
    scenario: str,
    current_invalid: bool | None,
    login_challenge: bool | None,
    newline: str,
) -> None:
    record = _auth_ui_diag_record(
        project=project,
        scenario=scenario,
        currentFieldInvalid=current_invalid,
        loginChallenge=login_challenge,
    )
    assert live_stand._live_playwright_auth_ui_diagnostics(
        _auth_diag_row("AUTH_UI_DIAG ", record, newline)
    ) == [record]


def test_live_playwright_auth_ui_parser_accepts_capped_alerts_and_details() -> None:
    for detail_class in ("expected", "other-string", "non-string", "missing"):
        record = _auth_ui_diag_record(
            scenario="totp_recovery_replay",
            detailClass=detail_class,
            alertCount=8,
            alertCountCapped=True,
        )
        assert live_stand._live_playwright_auth_ui_diagnostics(
            _auth_diag_row("AUTH_UI_DIAG ", record)
        ) == [record]


def test_live_playwright_auth_ui_parser_rejects_malformed_or_private_rows() -> None:
    valid = _auth_ui_diag_record()
    malformed: list[dict[str, object]] = []
    for key, value in (
        ("schema", True),
        ("schema", 2),
        ("project", "private-project"),
        ("scenario", "password_current_invalid https://private.invalid"),
        ("status", True),
        ("status", 99),
        ("status", 600),
        ("detailClass", "expected private alert text"),
        ("alertCount", True),
        ("alertCount", -1),
        ("alertCount", 9),
        ("alertCountCapped", 1),
        ("alertVisible", "true"),
        ("pageError", None),
        ("extra", "private token"),
    ):
        malformed.append({**valid, key: value})
    malformed.append(_auth_ui_diag_record(alertCountCapped=True))
    malformed.append(
        _auth_ui_diag_record(
            scenario="totp_recovery_replay",
            currentFieldInvalid=False,
            loginChallenge=True,
        )
    )
    malformed.append(
        _auth_ui_diag_record(
            scenario="password_current_invalid",
            currentFieldInvalid=True,
            loginChallenge=False,
        )
    )

    for record in malformed:
        assert (
            live_stand._live_playwright_auth_ui_diagnostics(
                _auth_diag_row("AUTH_UI_DIAG ", record)
            )
            == []
        )

    row = _auth_diag_row("AUTH_UI_DIAG ", valid)
    malformed_rows = (
        row.rstrip("\n"),
        row[:-1] + " private-url\n",
        "private title " + row,
        row[:-1].replace('"schema":1', '"schema":1,"schema":1') + "\n",
        row[:-1].replace('"status":422', '"status":NaN') + "\n",
        row[:-1].replace('"status":422', '"status":422.0') + "\n",
        row.replace("\n", "\x00\n"),
        "AUTH_UI_DIAG " + "x" * 1025 + "\n",
    )
    for malformed_row in malformed_rows:
        assert live_stand._live_playwright_auth_ui_diagnostics(malformed_row) == []


def test_live_playwright_auth_ui_parser_deduplicates_and_caps_records() -> None:
    records = [
        _auth_ui_diag_record(status=100 + index, alertCount=index % 9)
        for index in range(17)
    ]
    rows = "".join(
        _auth_diag_row("AUTH_UI_DIAG ", record)
        for record in [records[0], records[1], records[0], *records[2:]]
    )
    assert live_stand._live_playwright_auth_ui_diagnostics(rows) == records[:16]


@pytest.mark.parametrize("operation", _AUTH_HTTP_DIAG_TEST_OPERATIONS)
@pytest.mark.parametrize("project", ["desktop", "mobile"])
def test_live_playwright_auth_http_parser_accepts_closed_status_mismatches(
    operation: str, project: str
) -> None:
    record = _auth_http_diag_record(operation, project=project)
    assert live_stand._live_playwright_auth_http_diagnostics(
        _auth_diag_row("AUTH_HTTP_DIAG ", record)
    ) == [record]


def test_live_playwright_auth_http_parser_rejects_unexpected_or_private_rows() -> None:
    valid = _auth_http_diag_record()
    malformed = (
        {**valid, "schema": True},
        {**valid, "project": "private"},
        {**valid, "operation": "profile_read?token=private"},
        {**valid, "expectedStatus": 403},
        {**valid, "expectedStatus": True},
        {**valid, "status": 200},
        {**valid, "status": 99},
        {**valid, "status": 600},
        {**valid, "status": 503.0},
        {**valid, "status": True},
        {**valid, "extra": "https://private.invalid/path"},
        _auth_http_diag_record("student_admin_read", expected_status=200),
        _auth_http_diag_record("student_admin_read", expected_status=403, status=403),
        _auth_http_diag_record("password_change_invalid", expected_status=200),
        _auth_http_diag_record(
            "password_change_invalid", expected_status=400, status=400
        ),
        _auth_http_diag_record("totp_recovery_replay", expected_status=200),
        _auth_http_diag_record("totp_recovery_replay", expected_status=400, status=400),
    )
    for record in malformed:
        assert (
            live_stand._live_playwright_auth_http_diagnostics(
                _auth_diag_row("AUTH_HTTP_DIAG ", record)
            )
            == []
        )

    row = _auth_diag_row("AUTH_HTTP_DIAG ", valid)
    malformed_rows = (
        row.rstrip("\n"),
        row[:-1].replace('"schema":1', '"schema":1,"schema":1') + "\n",
        row[:-1].replace('"status":500', '"status":Infinity') + "\n",
        row.replace("\n", "\x00\n"),
        "AUTH_HTTP_DIAG " + "x" * 1025 + "\n",
    )
    for malformed_row in malformed_rows:
        assert live_stand._live_playwright_auth_http_diagnostics(malformed_row) == []


def test_live_playwright_auth_http_parser_deduplicates_and_caps_records() -> None:
    records = [
        _auth_http_diag_record(operation, status=501 + index)
        for index, operation in enumerate(_AUTH_HTTP_DIAG_TEST_OPERATIONS)
    ]
    rows = "".join(
        _auth_diag_row("AUTH_HTTP_DIAG ", record)
        for record in [records[0], records[1], records[0], *records[2:]]
    )
    assert live_stand._live_playwright_auth_http_diagnostics(rows) == records[:16]


def test_live_playwright_auth_diagnostics_are_failure_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    rows = _auth_diag_row("AUTH_UI_DIAG ", _auth_ui_diag_record()) + _auth_diag_row(
        "AUTH_HTTP_DIAG ", _auth_http_diag_record()
    )
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"),
        0,
        stdout=rows.encode(),
        stderr=b"",
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")

    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E outcome=passed exit_code=0",
    ]
    assert "live E2E auth UI" not in printed.out
    assert "live E2E auth HTTP" not in printed.out
    assert printed.err == ""
    assert completed.stdout == completed.stderr == b""


def test_live_playwright_emits_only_closed_auth_diagnostics_from_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    ui_record = _auth_ui_diag_record(project="mobile", scenario="totp_recovery_replay")
    http_record = _auth_http_diag_record("push_subscribe", project="mobile", status=503)
    private = (
        "private alert text password=not-for-output https://private.invalid/user/123"
    )
    valid_ui = _auth_diag_row("AUTH_UI_DIAG ", ui_record)
    valid_http = _auth_diag_row("AUTH_HTTP_DIAG ", http_record)
    malformed_ui = _auth_diag_row("AUTH_UI_DIAG ", {**ui_record, "scenario": private})
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"),
        1,
        stdout=(valid_ui + valid_http + malformed_ui + private + "\n").encode(),
        stderr=(valid_ui + valid_http + private + "\n").encode(),
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    with pytest.raises(live_stand.StandError, match="exit code 1"):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")

    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E auth UI " + json.dumps(ui_record, separators=(",", ":")),
        "live E2E auth HTTP " + json.dumps(http_record, separators=(",", ":")),
        "live E2E outcome=failed exit_code=1",
    ]
    assert private not in printed.out + printed.err
    assert printed.err == ""
    assert completed.stdout == completed.stderr == b""


_STORY_SETUP_STAGES = (
    "browser-launch",
    "fixture-policy",
    "owner-cdp",
    "command-line",
    "debug-port",
    "cdp-attach",
    "default-context",
    "cookies",
    "main-target",
    "project-options",
    "bootstrap-listener",
    "login",
    "dashboard",
    "bootstrap",
    "story-trigger",
    "warm-up",
    "baseline",
    "cycle0",
    "measured-cycle",
    "acceptance",
    "cleanup",
)


def _story_setup_diag_record(
    *, project: str = "desktop", stage: str = "login", exception_kind: str = "error"
) -> dict[str, object]:
    return {
        "schema": 1,
        "project": project,
        "stage": stage,
        "exceptionKind": exception_kind,
    }


def _story_setup_diag_row(record: dict[str, object], newline: str = "\n") -> str:
    return "STORY_SETUP_DIAG " + json.dumps(record, separators=(",", ":")) + newline


@pytest.mark.parametrize("project", ["desktop", "mobile"])
@pytest.mark.parametrize("stage", _STORY_SETUP_STAGES)
def test_live_playwright_story_setup_parser_accepts_closed_stages(
    project: str, stage: str
) -> None:
    record = _story_setup_diag_record(project=project, stage=stage)
    assert live_stand._live_playwright_story_setup_diagnostics(
        _story_setup_diag_row(record)
    ) == [record]


@pytest.mark.parametrize(
    "exception_kind",
    ["error", "non-error", "cleanup", "error-with-cleanup", "non-error-with-cleanup"],
)
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_live_playwright_story_setup_parser_accepts_closed_exception_kinds(
    exception_kind: str, newline: str
) -> None:
    record = _story_setup_diag_record(exception_kind=exception_kind)
    assert live_stand._live_playwright_story_setup_diagnostics(
        _story_setup_diag_row(record, newline)
    ) == [record]


def test_live_playwright_story_setup_parser_rejects_private_or_malformed_rows() -> None:
    valid = _story_setup_diag_record()
    invalid = (
        {**valid, "schema": True},
        {**valid, "schema": 2},
        {**valid, "project": "private-project"},
        {**valid, "stage": "login https://private.invalid"},
        {**valid, "exceptionKind": "RuntimeError: private token"},
        {**valid, "extra": "private URL"},
    )
    assert all(
        live_stand._live_playwright_story_setup_diagnostics(
            _story_setup_diag_row(record)
        )
        == []
        for record in invalid
    )
    row = _story_setup_diag_row(valid)
    malformed = (
        row.rstrip("\n"),
        row[:-1].replace('"schema":1', '"schema":1,"schema":1') + "\n",
        row[:-1].replace('"schema":1', '"schema":NaN') + "\n",
        row.replace("\n", "\x00\n"),
        "STORY_SETUP_DIAG " + "x" * 513 + "\n",
    )
    assert all(
        live_stand._live_playwright_story_setup_diagnostics(value) == []
        for value in malformed
    )


def test_live_playwright_story_setup_parser_deduplicates_and_caps_records() -> None:
    records = [
        _story_setup_diag_record(stage=stage)
        for stage in ("login", "dashboard", "bootstrap", "cycle0", "acceptance")
    ]
    rows = "".join(
        _story_setup_diag_row(record)
        for record in (records[0], records[1], records[0], *records[2:])
    )
    assert live_stand._live_playwright_story_setup_diagnostics(rows) == records[:4]


def test_live_playwright_emits_story_setup_diagnostics_from_failure_stdout_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    record = _story_setup_diag_record(project="mobile", stage="cycle0")
    private = "private exception https://private.invalid token=not-for-output"
    valid = _story_setup_diag_row(record)
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"),
        1,
        stdout=(valid + private + "\n").encode(),
        stderr=valid.encode(),
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    with pytest.raises(live_stand.StandError, match="exit code 1"):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E story setup " + json.dumps(record, separators=(",", ":")),
        "live E2E outcome=failed exit_code=1",
    ]
    assert private not in printed.out + printed.err
    assert printed.err == ""
    assert completed.stdout == completed.stderr == b""


def test_live_playwright_suppresses_story_setup_diagnostics_on_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    row = _story_setup_diag_row(_story_setup_diag_record())
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"), 0, stdout=row.encode(), stderr=b""
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E outcome=passed exit_code=0",
    ]


_AUTH_REGISTRATION_PHASES = (
    "before-submit",
    "submit-click",
    "response-wait",
    "response-received",
    "navigation",
)


def _auth_registration_diag_record(
    *,
    project: str = "desktop",
    scenario: str = "password-settings",
    phase: str = "response-received",
    form_valid: bool = True,
    submit_enabled: bool = True,
    request_observed: bool = True,
    status: int | None = 422,
) -> dict[str, object]:
    return {
        "schema": 1,
        "project": project,
        "scenario": scenario,
        "phase": phase,
        "formValid": form_valid,
        "submitEnabled": submit_enabled,
        "requestObserved": request_observed,
        "status": status,
    }


def _auth_registration_diag_row(record: dict[str, object], newline: str = "\n") -> str:
    return (
        "AUTH_REGISTRATION_DIAG " + json.dumps(record, separators=(",", ":")) + newline
    )


def test_live_playwright_auth_registration_parser_accepts_closed_records() -> None:
    records = (
        _auth_registration_diag_record(
            project="desktop",
            phase="before-submit",
            form_valid=False,
            submit_enabled=False,
            request_observed=False,
            status=None,
        ),
        _auth_registration_diag_record(
            project="mobile",
            scenario="totp",
            phase="response-wait",
            request_observed=True,
            status=None,
        ),
        _auth_registration_diag_record(
            project="desktop",
            scenario="email-otp",
            phase="submit-click",
            request_observed=True,
            status=200,
        ),
        _auth_registration_diag_record(project="desktop", phase="response-received"),
        _auth_registration_diag_record(
            project="mobile", scenario="totp", phase="navigation", status=200
        ),
    )
    for record in records:
        assert live_stand._live_playwright_auth_registration_diagnostics(
            _auth_diag_row("AUTH_REGISTRATION_DIAG ", record)
        ) == [record]


@pytest.mark.parametrize(
    "phase_record",
    [
        _auth_registration_diag_record(phase="before-submit", request_observed=True),
        _auth_registration_diag_record(
            phase="before-submit", request_observed=False, status=200
        ),
        _auth_registration_diag_record(phase="response-wait", status=200),
        _auth_registration_diag_record(
            scenario="email-otp",
            phase="submit-click",
            request_observed=False,
            status=200,
        ),
        _auth_registration_diag_record(
            phase="response-received", request_observed=False
        ),
        _auth_registration_diag_record(phase="response-received", status=None),
        _auth_registration_diag_record(
            phase="navigation", request_observed=False, status=200
        ),
        _auth_registration_diag_record(phase="navigation", status=None),
    ],
)
def test_live_playwright_auth_registration_parser_rejects_inconsistent_phases(
    phase_record: dict[str, object],
) -> None:
    assert (
        live_stand._live_playwright_auth_registration_diagnostics(
            _auth_diag_row("AUTH_REGISTRATION_DIAG ", phase_record)
        )
        == []
    )


def test_live_playwright_auth_registration_parser_rejects_malformed_or_private_rows() -> (
    None
):
    valid = _auth_registration_diag_record()
    invalid = (
        {**valid, "schema": True},
        {**valid, "schema": 2},
        {**valid, "project": "private-project"},
        {**valid, "scenario": "private-scenario"},
        {**valid, "phase": "response https://private.invalid"},
        {**valid, "formValid": 1},
        {**valid, "submitEnabled": "yes"},
        {**valid, "requestObserved": 0},
        {**valid, "status": True},
        {**valid, "status": 99},
        {**valid, "status": 600},
        {**valid, "status": 200.0},
        {**valid, "extra": "private token"},
    )
    assert all(
        live_stand._live_playwright_auth_registration_diagnostics(
            _auth_diag_row("AUTH_REGISTRATION_DIAG ", record)
        )
        == []
        for record in invalid
    )
    missing_scenario = dict(valid)
    del missing_scenario["scenario"]
    assert (
        live_stand._live_playwright_auth_registration_diagnostics(
            _auth_diag_row("AUTH_REGISTRATION_DIAG ", missing_scenario)
        )
        == []
    )
    row = _auth_diag_row("AUTH_REGISTRATION_DIAG ", valid)
    malformed = (
        row.rstrip("\n"),
        row[:-1].replace('"schema":1', '"schema":1,"schema":1') + "\n",
        row[:-1].replace('"status":422', '"status":NaN') + "\n",
        row.replace("\n", "\x00\n"),
        "AUTH_REGISTRATION_DIAG " + "x" * 513 + "\n",
    )
    assert all(
        live_stand._live_playwright_auth_registration_diagnostics(value) == []
        for value in malformed
    )


def test_live_playwright_auth_registration_parser_deduplicates_and_caps_records() -> (
    None
):
    records = [
        _auth_registration_diag_record(phase="response-received", status=400 + index)
        for index in range(5)
    ]
    rows = "".join(
        _auth_diag_row("AUTH_REGISTRATION_DIAG ", record)
        for record in (records[0], records[1], records[0], *records[2:])
    )
    assert (
        live_stand._live_playwright_auth_registration_diagnostics(rows) == records[:4]
    )


def test_live_playwright_emits_registration_diagnostics_only_from_failure_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    record = _auth_registration_diag_record(
        project="mobile", scenario="totp", phase="navigation", status=200
    )
    private = "private response body https://private.invalid token=hidden"
    valid = _auth_registration_diag_row(record)
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"),
        1,
        stdout=(valid + private + "\n").encode(),
        stderr=valid.encode(),
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    with pytest.raises(live_stand.StandError, match="exit code 1"):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E auth registration " + json.dumps(record, separators=(",", ":")),
        "live E2E outcome=failed exit_code=1",
    ]
    assert private not in printed.out + printed.err
    assert printed.err == ""


def test_live_playwright_suppresses_registration_diagnostics_on_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    row = _auth_registration_diag_row(_auth_registration_diag_record())
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"), 0, stdout=row.encode(), stderr=b""
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E outcome=passed exit_code=0",
    ]


def _pwa_bundle_route_diag_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "schema": 1,
        "project": "desktop",
        "routeEntries": 1,
        "originMatches": 1,
        "bundlePathMatches": 1,
        "serviceWorkerRequestSeen": False,
    }
    record.update(overrides)
    return record


def _pwa_bundle_route_diag_row(record: dict[str, object], newline: str = "\n") -> str:
    return (
        "PWA_BUNDLE_ROUTE_DIAG " + json.dumps(record, separators=(",", ":")) + newline
    )


def test_live_playwright_pwa_route_parser_accepts_closed_records() -> None:
    ordinary = _pwa_bundle_route_diag_record()
    saturated = _pwa_bundle_route_diag_record(
        project="mobile",
        routeEntries=64,
        originMatches=64,
        bundlePathMatches=64,
        serviceWorkerRequestSeen=True,
    )
    assert live_stand._live_playwright_pwa_bundle_route_diagnostics(
        _pwa_bundle_route_diag_row(ordinary) + _pwa_bundle_route_diag_row(saturated)
    ) == [ordinary, saturated]


def test_live_playwright_pwa_bundle_route_parser_rejects_bad_or_private_rows() -> None:
    valid = _pwa_bundle_route_diag_record()
    invalid_records = (
        {**valid, "schema": True},
        {**valid, "project": "private-project"},
        {**valid, "routeEntries": True},
        {**valid, "routeEntries": 65},
        {**valid, "originMatches": 2},
        {**valid, "bundlePathMatches": 2},
        {**valid, "serviceWorkerRequestSeen": 1},
        {**valid, "serviceWorkerRequestSeen": True, "routeEntries": 0},
        {**valid, "requestUrl": "https://private.invalid/path"},
    )
    rows = "".join(_pwa_bundle_route_diag_row(record) for record in invalid_records)
    rows += 'PWA_BUNDLE_ROUTE_DIAG {"schema":1,"schema":1}\n'
    rows += 'PWA_BUNDLE_ROUTE_DIAG {"schema":NaN}\n'
    rows += "PWA_BUNDLE_ROUTE_DIAG " + "x" * 513 + "\n"
    rows += _pwa_bundle_route_diag_row(valid, newline="")
    assert live_stand._live_playwright_pwa_bundle_route_diagnostics(rows) == []


def test_live_playwright_pwa_bundle_route_parser_deduplicates_and_caps() -> None:
    records = [
        _pwa_bundle_route_diag_record(
            project="desktop" if index % 2 == 0 else "mobile",
            routeEntries=index,
            originMatches=index,
            bundlePathMatches=index,
        )
        for index in range(1, 6)
    ]
    rows = "".join(
        _pwa_bundle_route_diag_row(record)
        for record in (records[0], records[1], records[0], *records[2:])
    )
    assert live_stand._live_playwright_pwa_bundle_route_diagnostics(rows) == records[:4]


def test_live_playwright_emits_only_validated_pwa_route_diagnostics_from_failure_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    record = _pwa_bundle_route_diag_record(
        project="mobile", routeEntries=4, originMatches=2, bundlePathMatches=0
    )
    private = "https://private.invalid/assets/app.js token=hidden response body"
    valid = _pwa_bundle_route_diag_row(record)
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"),
        1,
        stdout=(valid + private + "\n").encode(),
        stderr=valid.encode(),
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    with pytest.raises(live_stand.StandError, match="exit code 1"):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E PWA bundle route " + json.dumps(record, separators=(",", ":")),
        "live E2E outcome=failed exit_code=1",
    ]
    assert private not in printed.out + printed.err
    assert printed.err == ""


def test_live_playwright_suppresses_pwa_bundle_route_diagnostics_on_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    row = _pwa_bundle_route_diag_row(_pwa_bundle_route_diag_record())
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"), 0, stdout=row.encode(), stderr=b""
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E outcome=passed exit_code=0",
    ]


def _story_memory_cycle_trace_record(**overrides: object) -> dict[str, object]:
    sample = {"documents": 2, "nodes": 788, "jsEventListeners": 458}
    record: dict[str, object] = {
        "schema": 1,
        "project": "desktop",
        "diagnosticStatus": "available",
        "samples": {
            "baseline": sample,
            "dialogOpen": {**sample, "nodes": 811},
            "hiddenResumed": {**sample, "nodes": 811},
            "afterCloseSettled": {**sample, "nodes": 729},
        },
    }
    record.update(overrides)
    return record


def _story_memory_cycle_trace_row(
    record: dict[str, object], newline: str = "\n"
) -> str:
    return (
        "STORY_MEMORY_CYCLE_TRACE_DIAG "
        + json.dumps(record, separators=(",", ":"))
        + newline
    )


def test_live_playwright_story_memory_cycle_trace_parser_accepts_closed_statuses() -> (
    None
):
    available = _story_memory_cycle_trace_record()
    partial = _story_memory_cycle_trace_record(
        project="mobile",
        diagnosticStatus="partial",
        samples={
            "baseline": {"documents": 1, "nodes": 2, "jsEventListeners": 3},
            "dialogOpen": None,
            "hiddenResumed": None,
            "afterCloseSettled": {"documents": 1, "nodes": 2, "jsEventListeners": 3},
        },
    )
    unavailable = _story_memory_cycle_trace_record(
        diagnosticStatus="unavailable",
        samples={
            key: None
            for key in ("baseline", "dialogOpen", "hiddenResumed", "afterCloseSettled")
        },
    )
    rows = "".join(
        _story_memory_cycle_trace_row(record)
        for record in (available, partial, unavailable)
    )
    assert live_stand._live_playwright_story_memory_cycle_trace_diagnostics(rows) == [
        available,
        partial,
        unavailable,
    ]


def test_live_playwright_story_memory_cycle_trace_rejects_private_or_inconsistent_rows() -> (
    None
):
    valid = _story_memory_cycle_trace_record()
    samples = valid["samples"]
    assert isinstance(samples, dict)
    invalid = (
        {**valid, "schema": True},
        {**valid, "project": "https://private.invalid/user"},
        {**valid, "diagnosticStatus": "available token=hidden"},
        {**valid, "extra": "private response body"},
        {**valid, "samples": {**samples, "requestUrl": "https://private.invalid"}},
        {
            **valid,
            "samples": {
                **samples,
                "baseline": {"documents": True, "nodes": 2, "jsEventListeners": 3},
            },
        },
        {
            **valid,
            "samples": {
                **samples,
                "baseline": {
                    "documents": 2**53,
                    "nodes": 2,
                    "jsEventListeners": 3,
                },
            },
        },
        {
            **valid,
            "diagnosticStatus": "partial",
            "samples": {key: None for key in samples},
        },
        {
            **valid,
            "diagnosticStatus": "unavailable",
            "samples": {**samples, "afterCloseSettled": None},
        },
    )
    rows = "".join(_story_memory_cycle_trace_row(record) for record in invalid)
    rows += 'STORY_MEMORY_CYCLE_TRACE_DIAG {"schema":1,"schema":1}\n'
    rows += 'STORY_MEMORY_CYCLE_TRACE_DIAG {"schema":NaN}\n'
    rows += _story_memory_cycle_trace_row(valid, newline="")
    rows += "STORY_MEMORY_CYCLE_TRACE_DIAG " + "x" * 2049 + "\n"
    assert live_stand._live_playwright_story_memory_cycle_trace_diagnostics(rows) == []


def _pwa_update_lifecycle_diag_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "schema": 1,
        "project": "mobile",
        "diagnosticStatus": "available",
        "controllerChangeCount": 0,
        "controllerPresent": True,
        "controllerState": "activated",
        "installingState": "none",
        "waitingState": "none",
        "activeState": "activated",
        "controllerIsActive": True,
        "workerTransformApplied": True,
        "bundleUpdateResponseSeen": True,
        "routeEntries": 1,
        "originMatches": 1,
        "bundlePathMatches": 1,
        "serviceWorkerRequestSeen": True,
    }
    record.update(overrides)
    return record


def _pwa_update_lifecycle_diag_row(
    record: dict[str, object], newline: str = "\n"
) -> str:
    return (
        "PWA_UPDATE_LIFECYCLE_DIAG "
        + json.dumps(record, separators=(",", ":"))
        + newline
    )


def test_live_playwright_pwa_update_lifecycle_parser_accepts_available_and_unavailable() -> (
    None
):
    available = _pwa_update_lifecycle_diag_record()
    unavailable = _pwa_update_lifecycle_diag_record(
        project="desktop",
        diagnosticStatus="unavailable",
        controllerChangeCount=None,
        controllerPresent=None,
        controllerState="none",
        installingState="none",
        waitingState="none",
        activeState="none",
        controllerIsActive=None,
        routeEntries=None,
        originMatches=None,
        bundlePathMatches=None,
        serviceWorkerRequestSeen=False,
    )
    assert live_stand._live_playwright_pwa_update_lifecycle_diagnostics(
        _pwa_update_lifecycle_diag_row(available)
        + _pwa_update_lifecycle_diag_row(unavailable)
    ) == [available, unavailable]


def test_live_playwright_pwa_update_lifecycle_accepts_parsed_but_rejects_unknown_state() -> (
    None
):
    parsed = _pwa_update_lifecycle_diag_record(installingState="parsed")
    unknown = {**parsed, "waitingState": "received"}

    assert live_stand._live_playwright_pwa_update_lifecycle_diagnostics(
        _pwa_update_lifecycle_diag_row(parsed)
    ) == [parsed]
    assert (
        live_stand._live_playwright_pwa_update_lifecycle_diagnostics(
            _pwa_update_lifecycle_diag_row(unknown)
        )
        == []
    )


def test_live_playwright_pwa_update_lifecycle_rejects_private_or_inconsistent_rows() -> (
    None
):
    valid = _pwa_update_lifecycle_diag_record()
    invalid = (
        {**valid, "schema": True},
        {**valid, "project": "mobile https://private.invalid"},
        {**valid, "project": []},
        {**valid, "project": {}},
        {**valid, "diagnosticStatus": "partial"},
        {**valid, "extra": "token=hidden"},
        {**valid, "controllerChangeCount": True},
        {**valid, "routeEntries": 65},
        {**valid, "controllerState": "private response body"},
        {**valid, "originMatches": 2},
        {**valid, "bundlePathMatches": 2},
        {**valid, "serviceWorkerRequestSeen": True, "routeEntries": 0},
        {**valid, "serviceWorkerRequestSeen": True, "routeEntries": None},
        {
            **valid,
            "diagnosticStatus": "unavailable",
            "activeState": "activated",
        },
        {**valid, "controllerPresent": 1},
        {**valid, "workerTransformApplied": "yes"},
    )
    rows = "".join(_pwa_update_lifecycle_diag_row(record) for record in invalid)
    rows += 'PWA_UPDATE_LIFECYCLE_DIAG {"schema":1,"schema":1}\n'
    rows += 'PWA_UPDATE_LIFECYCLE_DIAG {"schema":NaN}\n'
    rows += _pwa_update_lifecycle_diag_row(valid, newline="")
    rows += "PWA_UPDATE_LIFECYCLE_DIAG " + "x" * 1025 + "\n"
    assert live_stand._live_playwright_pwa_update_lifecycle_diagnostics(rows) == []


def _registration_admission_diag_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "schema": 1,
        "project": "desktop",
        "stage": "ledger-read",
        "errorClass": "Error",
        "nodeCode": None,
        "cost": 1,
        "timeoutMs": 30000,
        "remainingMs": 29000,
        "requestCount": 0,
        "activeRequestCount": 0,
        "deadlineAvailable": True,
        "ownerPresent": True,
        "ledgerPresent": False,
        "requestObserved": False,
        "responseObserved": False,
        "actionFailed": False,
        "status": None,
    }
    record.update(overrides)
    return record


def _registration_admission_diag_row(
    record: dict[str, object], newline: str = "\n"
) -> str:
    return (
        "REGISTRATION_ADMISSION_DIAG "
        + json.dumps(record, separators=(",", ":"))
        + newline
    )


def test_live_playwright_registration_admission_parser_accepts_bounded_records() -> (
    None
):
    deadline_failure = _registration_admission_diag_record(
        project="mobile",
        stage="deadline",
        errorClass="TypeError",
        cost=None,
        timeoutMs=None,
        remainingMs=None,
        deadlineAvailable=False,
    )
    response_failure = _registration_admission_diag_record(
        stage="request-drain",
        nodeCode="ETIMEDOUT",
        requestCount=1,
        activeRequestCount=1,
        requestObserved=True,
        responseObserved=True,
        status=429,
        actionFailed=True,
    )
    assert live_stand._live_playwright_registration_admission_diagnostics(
        _registration_admission_diag_row(deadline_failure)
        + _registration_admission_diag_row(response_failure)
    ) == [deadline_failure, response_failure]


def test_live_playwright_registration_admission_parser_rejects_private_or_inconsistent_rows() -> (
    None
):
    valid = _registration_admission_diag_record()
    invalid = (
        {**valid, "schema": True},
        {**valid, "project": "https://private.invalid/user"},
        {**valid, "project": []},
        {**valid, "project": {}},
        {**valid, "stage": "submit https://private.invalid"},
        {**valid, "errorClass": "TypeError token=hidden"},
        {**valid, "nodeCode": "C:\\private\\path"},
        {**valid, "extra": "private response body"},
        {**valid, "cost": True},
        {**valid, "cost": 0},
        {**valid, "cost": 6},
        {**valid, "timeoutMs": 360001},
        {**valid, "timeoutMs": 0},
        {**valid, "remainingMs": -1},
        {**valid, "remainingMs": 0},
        {**valid, "deadlineAvailable": False, "remainingMs": 100},
        {**valid, "requestCount": True},
        {**valid, "requestCount": 257},
        {**valid, "activeRequestCount": 1},
        {**valid, "requestObserved": True},
        {**valid, "responseObserved": True},
        {**valid, "deadlineAvailable": 1},
        {**valid, "status": True},
        {**valid, "status": 600},
        {**valid, "status": 200, "responseObserved": False},
    )
    rows = "".join(_registration_admission_diag_row(record) for record in invalid)
    rows += 'REGISTRATION_ADMISSION_DIAG {"schema":1,"schema":1}\n'
    rows += 'REGISTRATION_ADMISSION_DIAG {"schema":NaN}\n'
    rows += _registration_admission_diag_row(valid, newline="")
    rows += "REGISTRATION_ADMISSION_DIAG " + "x" * 1025 + "\n"
    assert live_stand._live_playwright_registration_admission_diagnostics(rows) == []


@pytest.mark.parametrize(
    ("prefix", "record", "summary"),
    [
        (
            "STORY_MEMORY_CYCLE_TRACE_DIAG ",
            _story_memory_cycle_trace_record(),
            "live E2E story memory cycle trace ",
        ),
        (
            "PWA_UPDATE_LIFECYCLE_DIAG ",
            _pwa_update_lifecycle_diag_record(),
            "live E2E PWA update lifecycle ",
        ),
        (
            "REGISTRATION_ADMISSION_DIAG ",
            _registration_admission_diag_record(),
            "live E2E registration admission ",
        ),
    ],
)
def test_live_playwright_emits_only_validated_new_diagnostics_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    prefix: str,
    record: dict[str, object],
    summary: str,
) -> None:
    row = prefix + json.dumps(record, separators=(",", ":")) + "\n"
    private = "https://private.invalid/path?token=hidden response body"
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"),
        1,
        stdout=(row + private + "\n").encode(),
        stderr=row.encode(),
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    with pytest.raises(live_stand.StandError, match="exit code 1"):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        summary + json.dumps(record, separators=(",", ":")),
        "live E2E outcome=failed exit_code=1",
    ]
    assert private not in printed.out + printed.err
    assert printed.err == ""


@pytest.mark.parametrize(
    "prefix,record",
    [
        ("STORY_MEMORY_CYCLE_TRACE_DIAG ", _story_memory_cycle_trace_record()),
        ("PWA_UPDATE_LIFECYCLE_DIAG ", _pwa_update_lifecycle_diag_record()),
        ("REGISTRATION_ADMISSION_DIAG ", _registration_admission_diag_record()),
    ],
)
def test_live_playwright_suppresses_new_diagnostics_on_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    prefix: str,
    record: dict[str, object],
) -> None:
    row = prefix + json.dumps(record, separators=(",", ":")) + "\n"
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"), 0, stdout=row.encode(), stderr=b""
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E outcome=passed exit_code=0",
    ]


@pytest.mark.parametrize(
    "fields",
    [
        "project=desktop stage=submit requests=0 responses=0 status=none route=login",
        "project=mobile stage=navigation requests=1 responses=1 status=200 route=dashboard",
        "project=desktop stage=navigation requests=many responses=many status=599 route=other",
        "project=mobile stage=submit requests=1 responses=0 status=none route=unavailable",
        "project=desktop stage=navigation requests=1 responses=1 status=100 route=register",
    ],
)
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_live_playwright_emits_closed_login_failure_observations(
    fields: str,
    newline: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    row = f"UE_LIVE_LOGIN_FAILURE_V1 {fields}{newline}"
    completed = subprocess.CompletedProcess(
        [],
        1,
        stdout=(row + "private-body https://private.invalid/?token=x\n").encode(),
        stderr=b"private-stack private-credential\n",
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    with pytest.raises(live_stand.StandError):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        f"live E2E login failure {fields}",
        "live E2E outcome=failed exit_code=1",
    ]
    assert printed.err == ""
    assert completed.stdout == completed.stderr == b""


@pytest.mark.parametrize(
    "replacement",
    [
        ("project=desktop", "project=private"),
        ("stage=navigation", "stage=response"),
        ("requests=1", "requests=2"),
        ("responses=1", "responses=01"),
        ("status=200", "status=99"),
        ("status=200", "status=600"),
        ("status=200", "status=200.0"),
        ("status=200", "status=0200"),
        ("route=login", "route=/login?token=x"),
        ("route=login", "route=login#private"),
        ("route=login", "route=login extra=private"),
        ("\n", ""),
        ("\n", "\r"),
        ("\n", "\x1b[31m\n"),
        ("\n", "\u202e\n"),
    ],
)
def test_live_playwright_discards_malformed_login_failure_rows(
    replacement: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    row = (
        "UE_LIVE_LOGIN_FAILURE_V1 project=desktop stage=navigation "
        "requests=1 responses=1 status=200 route=login\n"
    ).replace(*replacement)
    completed = subprocess.CompletedProcess([], 1, stdout=row.encode(), stderr=b"")
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    with pytest.raises(live_stand.StandError):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command(mode="smoke")),
        "live E2E outcome=failed exit_code=1",
    ]
    assert printed.err == ""


def test_live_playwright_bounds_and_deduplicates_login_failure_rows(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    fields = [
        "project=desktop stage=navigation requests=1 responses=1 "
        f"status={status} route=login"
        for status in range(100, 120)
    ]
    stdout = "".join(f"UE_LIVE_LOGIN_FAILURE_V1 {row}\n" * 2 for row in fields).encode()
    completed = subprocess.CompletedProcess([], 1, stdout=stdout, stderr=b"")
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    with pytest.raises(live_stand.StandError):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    printed = capsys.readouterr()
    summaries = [
        line
        for line in printed.out.splitlines()
        if line.startswith("live E2E login failure ")
    ]
    assert summaries == [f"live E2E login failure {row}" for row in fields[:16]]
    assert printed.err == ""


@pytest.mark.parametrize("return_code", [0, 1])
def test_live_playwright_never_accepts_login_failure_rows_from_stderr(
    return_code: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    row = (
        b"UE_LIVE_LOGIN_FAILURE_V1 project=desktop stage=navigation "
        b"requests=1 responses=1 status=200 route=login\n"
    )
    completed = subprocess.CompletedProcess([], return_code, stdout=b"", stderr=row)
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    expectation = pytest.raises(live_stand.StandError) if return_code else nullcontext()
    with expectation:
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    printed = capsys.readouterr()
    assert "live E2E login failure " not in printed.out
    assert printed.err == ""


def test_live_playwright_suppresses_login_failure_rows_after_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    row = (
        b"UE_LIVE_LOGIN_FAILURE_V1 project=desktop stage=navigation "
        b"requests=1 responses=1 status=200 route=login\n"
    )
    completed = subprocess.CompletedProcess([], 0, stdout=row, stderr=b"")
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    printed = capsys.readouterr()
    assert "live E2E login failure " not in printed.out
    assert printed.err == ""


_PROJECTION_PROJECT = "ue-live-0123456789abcdef"


def _projection_model(*, core: bool = False) -> dict[str, Any]:
    names = live_stand.LIVE_CORE_EXPECTED_SERVICES if core else ("backend",)
    services: dict[str, Any] = {name: {} for name in names}
    services["backend"]["volumes"] = [
        {"type": "volume", "source": "app-data", "target": "/data"}
    ]
    if core:
        services["caddy"]["depends_on"] = [name for name in names if name != "caddy"]
    return {
        "name": _PROJECTION_PROJECT,
        "volumes": {
            "app-data": {
                "name": f"{_PROJECTION_PROJECT}_app-data",
                "external": False,
            },
            "unused": {"name": "shared-unused", "external": True},
        },
        "networks": {"unused-net": {"name": "shared-net", "external": True}},
        "services": services,
    }


def _projection_expected(
    *,
    core: bool = False,
    legacy: bool = False,
    target: str = "/data",
) -> Any:
    """Independent expected projection for the fixed synthetic models."""
    project_name = _PROJECTION_PROJECT
    selected = live_stand.LIVE_CORE_EXPECTED_SERVICES if core else ("backend",)
    roots = live_stand.LIVE_CORE_SERVICE_ROOTS if core else ("backend",)
    stack = live_stand.LIVE_STACK_CORE if core else live_stand.LIVE_STACK_FULL
    volume_name = f"{project_name}_app-data"
    network_name = f"{project_name}_default"
    retain_unused = not core or legacy

    volumes = {"app-data": {"external": False, "resolved_name": volume_name}}
    networks = {"default": {"external": False, "resolved_name": network_name}}
    if retain_unused:
        volumes["unused"] = {
            "external": True,
            "resolved_name": "shared-unused",
        }
        networks["unused-net"] = {
            "external": True,
            "resolved_name": "shared-net",
        }

    mounts: dict[str, Any] = {
        name: {
            "volumes": [],
            "volumes_from": [],
            "networks": ["default"],
            "network_mode": None,
        }
        for name in selected
    }
    mounts["backend"]["volumes"] = [
        {"type": "volume", "source": "app-data", "target": target}
    ]
    projection: dict[str, Any] = {
        "project_name": project_name,
        "volumes": volumes,
        "networks": networks,
        "service_mounts": mounts,
    }
    if not legacy:
        projection.update(
            {
                "stack": stack,
                "service_roots": list(roots),
                "selected_services": list(selected),
            }
        )
        if core:
            projection["published_port_names"] = [
                "BACKEND",
                "CADDY_HTTP",
                "CADDY_HTTPS",
                "FRONTEND",
                "GATEWAY",
                "IMGPROXY",
                "MAILPIT",
                "MINIO",
                "POSTGRES",
                "WS_HUB",
            ]

    canonical = json.dumps(
        projection,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    declared_volumes = (
        tuple(sorted((volume_name, "shared-unused")))
        if retain_unused
        else (volume_name,)
    )
    bindings = [("default", network_name, False)]
    if retain_unused:
        bindings.append(("unused-net", "shared-net", True))
    return live_stand.ComposeResourceEvidence(
        fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        managed_volumes=(("app-data", volume_name),),
        declared_volume_names=declared_volumes,
        managed_networks=(("default", network_name),),
        managed_services=tuple(sorted(selected)),
        stack=stack,
        service_roots=roots,
        selected_services=selected,
        network_bindings=tuple(sorted(bindings)),
        service_networks=tuple((name, ("default",)) for name in sorted(selected)),
        service_mounts=tuple(
            (
                service,
                tuple(
                    (
                        mount["type"],
                        (
                            volumes[mount["source"]]["resolved_name"]
                            if mount["type"] == "volume"
                            else mount["source"]
                        ),
                        mount["target"],
                    )
                    for mount in details["volumes"]
                ),
            )
            for service, details in sorted(mounts.items())
        ),
    )


def _install_projection_process(
    monkeypatch: pytest.MonkeyPatch,
    worktree: Path,
    ports: dict[str, int],
    stdout: Any,
    *,
    error: Exception | None = None,
) -> list[tuple[str, ...]]:
    """Allow exactly one expected mocked call, with no subprocess fallback."""
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)
    environment = {"COMPOSE_PROJECT_NAME": _PROJECTION_PROJECT}
    expected_command = [
        "docker",
        "compose",
        "-p",
        _PROJECTION_PROJECT,
        "--env-file",
        ".env.docker",
        "-f",
        "docker-compose.full.yml",
        "-f",
        live_stand.OVERLAY,
        "config",
        "--format",
        "json",
    ]
    calls: list[tuple[str, ...]] = []

    def control_environment(
        project_name: str,
        published_ports: Mapping[str, int],
        *,
        base_environment: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        assert project_name == _PROJECTION_PROJECT
        assert dict(published_ports) == ports
        assert base_environment is None
        return environment

    def fake_run(
        command: Sequence[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        assert list(command) == expected_command
        assert kwargs == {
            "cwd": worktree,
            "env": environment,
            "check": True,
            "capture_output": True,
            "text": True,
        }
        assert calls == [], "unexpected additional process invocation"
        calls.append(tuple(command))
        if error is not None:
            raise error
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(live_stand, "compose_control_environment", control_environment)
    monkeypatch.setattr(live_stand.subprocess, "run", fake_run)
    return calls


def _assert_projection_pair(
    monkeypatch: pytest.MonkeyPatch,
    worktree: Path,
    model: object,
    *,
    core: bool = False,
    legacy: bool = False,
    ports: dict[str, int] | None = None,
    roots: Sequence[str] | None = None,
    expected_error: str | None = None,
) -> Any:
    published_ports = _port_map() if ports is None else ports
    original = json.dumps(model, sort_keys=True)
    direct_model = json.loads(original)
    calls = _install_projection_process(
        monkeypatch, worktree, published_ports, json.dumps(model)
    )
    stack = live_stand.LIVE_STACK_CORE if core else live_stand.LIVE_STACK_FULL
    service_roots = (
        live_stand.LIVE_CORE_SERVICE_ROOTS if core and roots is None else roots
    )
    options = {
        "stack": stack,
        "service_roots": service_roots,
        "legacy_projection": legacy,
    }
    if expected_error is None:
        wrapped = live_stand._compose_resource_evidence(
            worktree, _PROJECTION_PROJECT, published_ports, **options
        )
        assert len(calls) == 1
        direct = live_stand._compose_resource_evidence_from_project(
            direct_model, _PROJECTION_PROJECT, published_ports, **options
        )
        assert wrapped == direct
    else:
        with pytest.raises(live_stand.StandError) as wrapped_error:
            live_stand._compose_resource_evidence(
                worktree, _PROJECTION_PROJECT, published_ports, **options
            )
        assert len(calls) == 1
        with pytest.raises(live_stand.StandError) as direct_error:
            live_stand._compose_resource_evidence_from_project(
                direct_model, _PROJECTION_PROJECT, published_ports, **options
            )
        assert str(wrapped_error.value) == expected_error
        assert str(direct_error.value) == expected_error
        wrapped = None

    assert len(calls) == 1
    assert json.dumps(model, sort_keys=True) == original
    assert json.dumps(direct_model, sort_keys=True) == original
    return wrapped


def test_compose_resource_projection_full_matches_existing_wrapper(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    observed = _assert_projection_pair(monkeypatch, tmp_path, _projection_model())
    assert observed == _projection_expected()


def test_compose_resource_projection_core_preserves_closure_and_filtering(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model = _projection_model(core=True)
    expected = _projection_expected(core=True)
    original = _assert_projection_pair(monkeypatch, tmp_path, model, core=True)
    assert original == expected

    changed_ports = _port_map()
    changed_ports["CADDY_HTTP"] += 1000
    changed_ports["GRAFANA"] += 1000
    port_changed = _assert_projection_pair(
        monkeypatch,
        tmp_path,
        model,
        core=True,
        ports=changed_ports,
    )
    assert port_changed == expected

    unused_changed = json.loads(json.dumps(model))
    unused_changed["volumes"]["unused"]["name"] = "other-shared-unused"
    unused_changed["networks"]["unused-net"]["name"] = "other-shared-net"
    unused_observed = _assert_projection_pair(
        monkeypatch, tmp_path, unused_changed, core=True
    )
    assert unused_observed == expected

    mount_changed = json.loads(json.dumps(model))
    mount_changed["services"]["backend"]["volumes"][0]["target"] = "/data/é"
    changed = _assert_projection_pair(monkeypatch, tmp_path, mount_changed, core=True)
    assert changed == _projection_expected(core=True, target="/data/é")
    assert changed.fingerprint != original.fingerprint


@pytest.mark.parametrize("core", [False, True], ids=["full", "core"])
def test_compose_resource_projection_legacy_preserves_schema(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, core: bool
) -> None:
    model = _projection_model(core=core)
    observed = _assert_projection_pair(
        monkeypatch, tmp_path, model, core=core, legacy=True
    )
    assert observed == _projection_expected(core=core, legacy=True)
    assert "shared-unused" in observed.declared_volume_names
    assert ("unused-net", "shared-net", True) in observed.network_bindings

    modern = _assert_projection_pair(monkeypatch, tmp_path, model, core=core)
    assert observed.fingerprint != modern.fingerprint
    if core:
        assert "shared-unused" not in modern.declared_volume_names
        assert ("unused-net", "shared-net", True) not in modern.network_bindings


@pytest.mark.parametrize(
    ("case", "message"),
    [
        (
            "root-list",
            "resolved Compose project does not match live stand ownership",
        ),
        (
            "wrong-name",
            "resolved Compose project does not match live stand ownership",
        ),
        ("volumes-list", "resolved Compose resource inventory is invalid"),
        ("external-type", "resolved Compose volume ownership is ambiguous"),
        (
            "unscoped-volume",
            "refusing unscoped Compose volume outside the live stand project",
        ),
        (
            "volumes-from",
            "Compose volumes_from is unsupported for owned teardown",
        ),
        (
            "anonymous-volume",
            "anonymous Compose volumes are unsupported for owned teardown",
        ),
        (
            "undeclared-volume",
            "resolved Compose mount refers to an undeclared volume",
        ),
    ],
)
def test_compose_resource_projection_preserves_malformed_model_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case: str,
    message: str,
) -> None:
    model: Any = _projection_model()
    if case == "root-list":
        model = []
    elif case == "wrong-name":
        model["name"] = "wrong-project"
    elif case == "volumes-list":
        model["volumes"] = []
    elif case == "external-type":
        model["volumes"]["app-data"]["external"] = 1
    elif case == "unscoped-volume":
        model["volumes"]["app-data"]["name"] = "unscoped-data"
    elif case == "volumes-from":
        model["services"]["backend"]["volumes_from"] = ["other"]
    elif case == "anonymous-volume":
        model["services"]["backend"]["volumes"][0].pop("source")
    else:
        assert case == "undeclared-volume"
        model["services"]["backend"]["volumes"][0]["source"] = "undeclared"

    _assert_projection_pair(monkeypatch, tmp_path, model, expected_error=message)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        (
            "missing-root",
            "reviewed live Core service roots are missing from Compose",
        ),
        (
            "missing-dependency",
            "resolved Compose dependency references an unknown service",
        ),
        (
            "extra-service",
            "resolved live Core dependency closure differs from reviewed services",
        ),
        (
            "wrong-roots",
            "resolved Compose service roots differ from live owner selection",
        ),
    ],
)
def test_compose_resource_projection_preserves_core_selection_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case: str,
    message: str,
) -> None:
    model = _projection_model(core=True)
    roots: Sequence[str] | None = None
    if case == "missing-root":
        model["services"].pop("mailpit")
    elif case == "missing-dependency":
        model["services"]["caddy"]["depends_on"].append("absent-service")
    elif case == "extra-service":
        model["services"]["extra-service"] = {}
        model["services"]["caddy"]["depends_on"].append("extra-service")
    else:
        assert case == "wrong-roots"
        roots = ("backend",)

    _assert_projection_pair(
        monkeypatch,
        tmp_path,
        model,
        core=True,
        roots=roots,
        expected_error=message,
    )


@pytest.mark.parametrize(
    "case",
    ["invalid-project", "os-error", "process-error", "invalid-json", "none-output"],
)
def test_compose_resource_wrapper_preserves_preprojection_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, case: str
) -> None:
    ports = _port_map()
    stdout: Any = json.dumps(_projection_model())
    error: Exception | None = None
    project_name = _PROJECTION_PROJECT
    if case == "invalid-project":
        project_name = "invalid-project"
        message = f"refusing unexpected Compose project name {project_name!r}"
    elif case == "os-error":
        error = OSError("synthetic process failure")
        message = "cannot verify resolved Compose resource ownership"
    elif case == "process-error":
        error = subprocess.CalledProcessError(1, ["docker", "compose"])
        message = "cannot verify resolved Compose resource ownership"
    elif case == "invalid-json":
        stdout = "{"
        message = "cannot parse resolved Compose resource ownership"
    else:
        assert case == "none-output"
        stdout = None
        message = "cannot parse resolved Compose resource ownership"

    calls = _install_projection_process(
        monkeypatch, tmp_path, ports, stdout, error=error
    )

    def unexpected_projection(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("projection must not run after a wrapper admission failure")

    monkeypatch.setattr(
        live_stand,
        "_compose_resource_evidence_from_project",
        unexpected_projection,
    )
    with pytest.raises(live_stand.StandError) as caught:
        live_stand._compose_resource_evidence(tmp_path, project_name, ports)
    assert str(caught.value) == message
    assert len(calls) == (0 if case == "invalid-project" else 1)
    if case != "invalid-project":
        assert caught.value.__suppress_context__ is True


def _aud174_access_log_row(
    uri: str,
    *,
    method: str = "GET",
    logger: str = "http.log.access.log0",
    status: int = 200,
    timestamp: str = "2026-10-20T12:00:00.000Z",
    level: str = "info",
    message: str = "handled request",
) -> bytes:
    payload = {
        "level": level,
        "ts": 1_798_000_000.0,
        "logger": logger,
        "msg": message,
        "request": {"method": method, "uri": uri},
        "status": status,
    }
    return (
        timestamp.encode("ascii") + b" " + json.dumps(payload).encode("utf-8") + b"\n"
    )


def _aud174_docker_read_context(
    tmp_path: Path,
) -> live_stand._LiveDockerReadContext:
    executable = str(Path(sys.executable).resolve(strict=True))
    return live_stand._LiveDockerReadContext(
        executable=executable,
        executable_identity=live_stand._live_docker_executable_identity(executable),
        cwd=str(tmp_path.resolve(strict=True)),
        environment=tuple(sorted(os.environ.items())),
    )


def test_live_caddy_probe_accepts_distinct_project_correlations_and_successful_gets() -> (
    None
):
    nonce = "0123456789abcdef" * 2
    correlations = {
        "desktop": "1" * 32,
        "mobile": "2" * 32,
    }
    assert correlations["desktop"] != correlations["mobile"]
    for project, correlation_id in correlations.items():
        redacted_uri = f"/login?probe={correlation_id}&password=REDACTED"
        output = _aud174_access_log_row(redacted_uri, status=200)

        live_stand._assert_live_caddy_probe_redaction(
            output,
            password_nonce=nonce,
            correlation_id=correlation_id,
            project=project,
        )


@pytest.mark.parametrize(
    ("rows", "status", "method", "logger", "wrong_uri"),
    [
        pytest.param(0, 200, "GET", "http.log.access.log0", False, id="missing-row"),
        pytest.param(2, 200, "GET", "http.log.access.log0", False, id="duplicate-row"),
        pytest.param(
            1, 404, "GET", "http.log.access.log0", False, id="unsuccessful-response"
        ),
        pytest.param(1, 200, "POST", "http.log.access.log0", False, id="wrong-method"),
        pytest.param(1, 200, "GET", "other", False, id="wrong-logger"),
        pytest.param(
            1,
            200,
            "GET",
            "http.log.access",
            False,
            id="unnamed-access-logger-not-configured",
        ),
        pytest.param(
            1, 200, "GET", "http.log.access.log0", True, id="wrong-correlation"
        ),
    ],
)
def test_live_caddy_probe_rejects_incomplete_or_nonmatching_rows(
    rows: int, status: int, method: str, logger: str, wrong_uri: bool
) -> None:
    nonce = "0123456789abcdef" * 2
    correlation_id = "1" * 32
    observed_correlation = "3" * 32 if wrong_uri else correlation_id
    redacted_uri = f"/login?probe={observed_correlation}&password=REDACTED"
    output = (
        _aud174_access_log_row(
            redacted_uri, method=method, logger=logger, status=status
        )
        * rows
    )

    with pytest.raises(live_stand.StandError) as error:
        live_stand._assert_live_caddy_probe_redaction(
            output,
            password_nonce=nonce,
            correlation_id=correlation_id,
            project="desktop",
        )

    assert str(error.value) == "Caddy access-log redaction proof failed"
    assert nonce not in str(error.value)
    assert correlation_id not in str(error.value)


def test_live_caddy_probe_rejects_unredacted_value_without_echoing_it() -> None:
    nonce = "0123456789abcdef" * 2
    correlation_id = "1" * 32
    raw_uri = f"/login?probe={correlation_id}&password={nonce}-desktop"
    output = _aud174_access_log_row(raw_uri)

    with pytest.raises(live_stand.StandError) as error:
        live_stand._assert_live_caddy_probe_redaction(
            output,
            password_nonce=nonce,
            correlation_id=correlation_id,
            project="desktop",
        )

    assert str(error.value) == "Caddy access-log redaction proof failed"
    assert nonce not in str(error.value)
    assert raw_uri not in str(error.value)


def test_live_caddy_probe_rejects_duplicate_correlations_across_streams() -> None:
    nonce = "0123456789abcdef" * 2
    correlation_id = "1" * 32
    redacted_uri = f"/login?probe={correlation_id}&password=REDACTED"
    row = _aud174_access_log_row(redacted_uri)

    with pytest.raises(
        live_stand.StandError,
        match="Caddy access-log redaction proof failed",
    ):
        live_stand._assert_live_caddy_probe_redaction(
            row,
            stderr=row,
            password_nonce=nonce,
            correlation_id=correlation_id,
            project="desktop",
        )


def test_live_caddy_probe_rejects_password_nonce_in_stderr() -> None:
    nonce = "0123456789abcdef" * 2
    correlation_id = "1" * 32
    raw_uri = f"/login?probe={correlation_id}&password={nonce}"

    with pytest.raises(
        live_stand.StandError,
        match="Caddy access-log redaction proof failed",
    ):
        live_stand._assert_live_caddy_probe_redaction(
            b"",
            stderr=_aud174_access_log_row(raw_uri),
            password_nonce=nonce,
            correlation_id=correlation_id,
            project="desktop",
        )


def test_live_caddy_probe_rejects_combined_stdout_and_stderr_over_capture_limit() -> (
    None
):
    nonce = "0123456789abcdef" * 2
    correlation_id = "1" * 32
    redacted_uri = f"/login?probe={correlation_id}&password=REDACTED"

    with pytest.raises(
        live_stand.StandError,
        match="Caddy access-log redaction proof failed",
    ):
        live_stand._assert_live_caddy_probe_redaction(
            _aud174_access_log_row(redacted_uri),
            stderr=b" " * live_stand._LIVE_CADDY_PROBE_MAX_BYTES,
            password_nonce=nonce,
            correlation_id=correlation_id,
            project="desktop",
        )


def test_live_caddy_probe_rejects_invalid_tokens_and_oversized_log_capture() -> None:
    nonce = "0123456789abcdef" * 2
    correlation_id = "1" * 32
    redacted_uri = f"/login?probe={correlation_id}&password=REDACTED"
    output = _aud174_access_log_row(redacted_uri)

    for invalid_nonce, invalid_correlation in (
        ("not-a-random-marker", correlation_id),
        (nonce, "not-a-correlation"),
        (nonce, nonce),
    ):
        with pytest.raises(
            live_stand.StandError, match="Caddy access-log redaction proof failed"
        ):
            live_stand._assert_live_caddy_probe_redaction(
                output,
                password_nonce=invalid_nonce,
                correlation_id=invalid_correlation,
                project="desktop",
            )
    with pytest.raises(
        live_stand.StandError, match="Caddy access-log redaction proof failed"
    ):
        live_stand._assert_live_caddy_probe_redaction(
            output + b" " * (live_stand._LIVE_CADDY_PROBE_MAX_BYTES + 1),
            password_nonce=nonce,
            correlation_id=correlation_id,
            project="desktop",
        )


@pytest.mark.parametrize(
    ("markers", "start_ms", "finish_ms"),
    [
        pytest.param(
            {
                "desktop": ("desktop", 1_000),
                "mobile": ("mobile", 2_000),
            },
            500,
            2_500,
            id="exact-project-markers",
        ),
        pytest.param(
            {"desktop": ("desktop", 1_000)},
            500,
            2_500,
            id="missing-project",
        ),
        pytest.param(
            {
                "desktop": ("desktop", 1_000),
                "mobile": ("mobile", 2_000),
                "unexpected": ("unexpected", 2_000),
            },
            500,
            2_500,
            id="unexpected-project",
        ),
        pytest.param(
            {
                "desktop": ("desktop", 1_000),
                "mobile": ("mobile", 2_000),
            },
            1_500,
            2_500,
            id="stale-marker",
        ),
        pytest.param(
            {
                "desktop": ("desktop", 1_000),
                "mobile": ("mobile", 2_001),
            },
            500,
            2_000,
            id="marker-after-run",
        ),
    ],
)
def test_live_caddy_probe_requires_complete_in_run_project_observations(
    tmp_path: Path,
    markers: dict[str, tuple[str, int]],
    start_ms: int,
    finish_ms: int,
) -> None:
    for file_project, (recorded_project, completed_at_ms) in markers.items():
        marker = {
            "schema": "aud174-caddy-probe-v1",
            "project": recorded_project,
            "completed_at_ms": completed_at_ms,
        }
        (tmp_path / f"aud174-caddy-probe-{file_project}.json").write_text(
            json.dumps(marker), encoding="utf-8"
        )

    if (
        len(markers) == 2
        and set(markers) == {"desktop", "mobile"}
        and all(
            file_project == recorded_project
            and start_ms <= completed_at_ms <= finish_ms
            for file_project, (recorded_project, completed_at_ms) in markers.items()
        )
    ):
        observations = live_stand._read_live_caddy_probe_observations(
            tmp_path, started_at_ms=start_ms, finished_at_ms=finish_ms
        )
        assert observations == {"desktop": 1_000, "mobile": 2_000}
        assert list(tmp_path.glob("aud174-caddy-probe-*.json")) == []
    else:
        with pytest.raises(
            live_stand.StandError,
            match="Caddy access-log redaction proof failed",
        ):
            live_stand._read_live_caddy_probe_observations(
                tmp_path, started_at_ms=start_ms, finished_at_ms=finish_ms
            )


def test_live_caddy_probe_marker_reads_are_bounded_and_descriptor_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for project, completed_at_ms in (("desktop", 1_000), ("mobile", 2_000)):
        (tmp_path / f"aud174-caddy-probe-{project}.json").write_text(
            json.dumps(
                {
                    "schema": "aud174-caddy-probe-v1",
                    "project": project,
                    "completed_at_ms": completed_at_ms,
                }
            ),
            encoding="utf-8",
        )

    original_read = os.read
    read_sizes: list[int] = []
    bytes_by_inode: dict[int, int] = {}

    def bounded_read(descriptor: int, size: int) -> bytes:
        read_sizes.append(size)
        data = original_read(descriptor, size)
        inode = os.fstat(descriptor).st_ino
        bytes_by_inode[inode] = bytes_by_inode.get(inode, 0) + len(data)
        return data

    monkeypatch.setattr(live_stand.os, "read", bounded_read)
    observations = live_stand._read_live_caddy_probe_observations(
        tmp_path,
        started_at_ms=500,
        finished_at_ms=2_500,
        deadline=live_stand.time.monotonic() + 5,
    )

    assert observations == {"desktop": 1_000, "mobile": 2_000}
    assert read_sizes
    assert max(read_sizes) <= 64
    assert len(bytes_by_inode) == 2
    assert all(
        count <= live_stand._LIVE_CADDY_PROBE_MARKER_MAX_BYTES + 1
        for count in bytes_by_inode.values()
    )


def test_live_caddy_probe_marker_deadline_expires_before_read_and_cleans_up(
    tmp_path: Path,
) -> None:
    for project in live_stand.LIVE_CADDY_PROBE_PROJECTS:
        (tmp_path / f"aud174-caddy-probe-{project}.json").write_text(
            json.dumps(
                {
                    "schema": "aud174-caddy-probe-v1",
                    "project": project,
                    "completed_at_ms": 1_000,
                }
            ),
            encoding="utf-8",
        )

    with pytest.raises(
        live_stand.StandError,
        match="Caddy access-log redaction proof failed",
    ):
        live_stand._read_live_caddy_probe_observations(
            tmp_path,
            started_at_ms=500,
            finished_at_ms=1_500,
            deadline=live_stand.time.monotonic() - 1,
        )

    assert list(tmp_path.glob("aud174-caddy-probe-*.json")) == []


def test_live_caddy_probe_marker_deadline_expires_during_read_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for project in live_stand.LIVE_CADDY_PROBE_PROJECTS:
        (tmp_path / f"aud174-caddy-probe-{project}.json").write_text(
            json.dumps(
                {
                    "schema": "aud174-caddy-probe-v1",
                    "project": project,
                    "completed_at_ms": 1_000,
                }
            ),
            encoding="utf-8",
        )

    now = [100.0]
    original_read = os.read

    def expire_after_read(descriptor: int, size: int) -> bytes:
        data = original_read(descriptor, size)
        now[0] = 101.0
        return data

    monkeypatch.setattr(live_stand.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(live_stand.os, "read", expire_after_read)
    with pytest.raises(
        live_stand.StandError,
        match="Caddy access-log redaction proof failed",
    ):
        live_stand._read_live_caddy_probe_observations(
            tmp_path,
            started_at_ms=500,
            finished_at_ms=1_500,
            deadline=100.5,
        )

    assert list(tmp_path.glob("aud174-caddy-probe-*.json")) == []


def _aud174_two_project_rows(
    completed_at_ms: Mapping[str, int], correlation_ids: Mapping[str, str]
) -> bytes:
    return b"".join(
        _aud174_access_log_row(
            f"/login?probe={correlation_ids[project]}&password=REDACTED",
            timestamp=live_stand._caddy_probe_timestamp_argument(
                completed_at_ms[project]
            ),
        )
        for project in live_stand.LIVE_CADDY_PROBE_PROJECTS
    )


def _aud174_read_project_logs(
    owner: object,
    *,
    container_pin: tuple[str, str],
    completed_at_ms: Mapping[str, int],
    password_nonce: str,
    correlation_ids: Mapping[str, str],
    deadline: float,
    docker_context: live_stand._LiveDockerReadContext,
) -> None:
    live_stand._read_live_caddy_probe_logs(
        owner,
        container_pin=container_pin,
        completed_at_ms=completed_at_ms,
        password_nonce=password_nonce,
        correlation_ids=correlation_ids,
        deadline=deadline,
        docker_context=docker_context,
    )


def test_live_caddy_probe_reads_one_union_window_from_reverified_pinned_container(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner = object()
    container_pin = ("a" * 64, "b" * 64)
    password_nonce = "0" * 32
    correlations = {"desktop": "1" * 32, "mobile": "2" * 32}
    completed_at = {"desktop": 1_798_000_000_000, "mobile": 1_798_000_002_000}
    completed = subprocess.CompletedProcess(
        ["docker", "logs"],
        0,
        stdout=_aud174_two_project_rows(completed_at, correlations),
        stderr=b"",
    )
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    pin_checks: list[tuple[str, str]] = []
    parser_calls: list[tuple[bytes, bytes, str, int | None, int | None]] = []
    original_parser = live_stand._assert_live_caddy_probe_redaction

    def record_parser(
        output: bytes,
        *,
        stderr: bytes,
        password_nonce: str,
        correlation_id: str,
        project: str,
        since_ms: int | None = None,
        until_ms: int | None = None,
    ) -> None:
        parser_calls.append((output, stderr, project, since_ms, until_ms))
        original_parser(
            output,
            stderr=stderr,
            password_nonce=password_nonce,
            correlation_id=correlation_id,
            project=project,
            since_ms=since_ms,
            until_ms=until_ms,
        )

    def fake_read(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append((args, kwargs))
        return completed

    context = _aud174_docker_read_context(tmp_path)
    monkeypatch.setattr(live_stand, "_run_live_bounded_read", fake_read)
    monkeypatch.setattr(live_stand, "_assert_live_caddy_probe_redaction", record_parser)
    monkeypatch.setattr(
        live_stand,
        "_assert_live_caddy_container_pin",
        lambda _owner, pin, **_kwargs: pin_checks.append(pin),
    )

    _aud174_read_project_logs(
        owner,
        container_pin=container_pin,
        completed_at_ms=completed_at,
        password_nonce=password_nonce,
        correlation_ids=correlations,
        deadline=live_stand.time.monotonic() + 30,
        docker_context=context,
    )

    assert len(calls) == 1
    command = calls[0][0][0]
    assert command == [
        "docker",
        "logs",
        "--timestamps",
        "--since",
        live_stand._caddy_probe_timestamp_argument(
            completed_at["desktop"] - live_stand._LIVE_CADDY_PROBE_WINDOW_MS
        ),
        "--until",
        live_stand._caddy_probe_timestamp_argument(
            completed_at["mobile"] + live_stand._LIVE_CADDY_PROBE_WINDOW_MS
        ),
        container_pin[0],
    ]
    options = calls[0][1]
    assert options["context"] is context
    assert options["deadline"] > live_stand.time.monotonic()
    assert options["maximum_bytes"] == live_stand._LIVE_CADDY_PROBE_MAX_BYTES
    assert options["command_timeout_seconds"] <= (
        live_stand._LIVE_CADDY_PROBE_LOG_TIMEOUT_SECONDS
    )
    assert "--tail" not in command
    assert password_nonce not in " ".join(command)
    assert pin_checks == [container_pin, container_pin]
    assert [call[2:] for call in parser_calls] == [
        (
            project,
            max(1, timestamp - live_stand._LIVE_CADDY_PROBE_WINDOW_MS),
            timestamp + live_stand._LIVE_CADDY_PROBE_WINDOW_MS,
        )
        for project, timestamp in completed_at.items()
    ]
    assert parser_calls[0][0] is parser_calls[1][0]
    assert parser_calls[0][1] is parser_calls[1][1]
    assert completed.stdout == completed.stderr == b""


def test_live_caddy_probe_accepts_timestamped_project_rows_on_stderr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner = object()
    container_pin = ("a" * 64, "b" * 64)
    password_nonce = "0" * 32
    correlations = {"desktop": "1" * 32, "mobile": "2" * 32}
    completed_at = {"desktop": 1_798_000_000_000, "mobile": 1_798_000_002_000}
    completed = subprocess.CompletedProcess(
        ["docker", "logs"],
        0,
        stdout=b"",
        stderr=_aud174_two_project_rows(completed_at, correlations),
    )
    context = _aud174_docker_read_context(tmp_path)
    monkeypatch.setattr(
        live_stand,
        "_run_live_bounded_read",
        lambda *_args, **_kwargs: completed,
    )
    monkeypatch.setattr(
        live_stand,
        "_assert_live_caddy_container_pin",
        lambda *_args, **_kwargs: None,
    )

    _aud174_read_project_logs(
        owner,
        container_pin=container_pin,
        completed_at_ms=completed_at,
        password_nonce=password_nonce,
        correlation_ids=correlations,
        deadline=live_stand.time.monotonic() + 30,
        docker_context=context,
    )


@pytest.mark.parametrize(
    ("returncode", "stderr"),
    [
        pytest.param(
            0, b"Docker daemon error while reading logs\n", id="malformed-diagnostic"
        ),
        pytest.param(
            0,
            _aud174_access_log_row(
                "/unrelated", level="error", message="Caddy log read failed"
            ),
            id="structured-error-diagnostic",
        ),
        pytest.param(
            0,
            _aud174_access_log_row("/unrelated").replace(
                b'"status": 200', b'"status": 500, "status": 200'
            ),
            id="duplicate-json-field",
        ),
    ],
)
def test_live_caddy_probe_rejects_error_diagnostics_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    returncode: int,
    stderr: bytes,
) -> None:
    owner = object()
    container_pin = ("a" * 64, "b" * 64)
    password_nonce = "0" * 32
    correlations = {"desktop": "1" * 32, "mobile": "2" * 32}
    completed_at = {"desktop": 1_798_000_000_000, "mobile": 1_798_000_002_000}
    completed = subprocess.CompletedProcess(
        ["docker", "logs"],
        returncode,
        stdout=_aud174_two_project_rows(completed_at, correlations),
        stderr=stderr,
    )
    monkeypatch.setattr(
        live_stand,
        "_run_live_bounded_read",
        lambda *_args, **_kwargs: completed,
    )
    pin_checks: list[tuple[str, str]] = []

    def record_pin(
        _owner: object,
        pin: tuple[str, str],
        **_kwargs: object,
    ) -> None:
        pin_checks.append(pin)

    monkeypatch.setattr(live_stand, "_assert_live_caddy_container_pin", record_pin)

    with pytest.raises(
        live_stand.StandError,
        match="Caddy access-log redaction proof failed",
    ) as error:
        _aud174_read_project_logs(
            owner,
            container_pin=container_pin,
            completed_at_ms=completed_at,
            password_nonce=password_nonce,
            correlation_ids=correlations,
            deadline=live_stand.time.monotonic() + 30,
            docker_context=_aud174_docker_read_context(tmp_path),
        )

    assert "Docker daemon error" not in str(error.value)
    assert "Caddy log read failed" not in str(error.value)
    assert pin_checks == [container_pin, container_pin]
    assert completed.stdout == completed.stderr == b""


def test_live_caddy_probe_rejects_nonzero_docker_logs_with_valid_project_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner = object()
    container_pin = ("a" * 64, "b" * 64)
    password_nonce = "0" * 32
    correlations = {"desktop": "1" * 32, "mobile": "2" * 32}
    completed_at = {"desktop": 1_798_000_000_000, "mobile": 1_798_000_002_000}
    completed = subprocess.CompletedProcess(
        ["docker", "logs"],
        1,
        stdout=b"",
        stderr=_aud174_two_project_rows(completed_at, correlations),
    )
    monkeypatch.setattr(
        live_stand,
        "_run_live_bounded_read",
        lambda *_args, **_kwargs: completed,
    )
    monkeypatch.setattr(
        live_stand,
        "_assert_live_caddy_container_pin",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(
        live_stand.StandError,
        match="Caddy access-log redaction proof failed",
    ):
        _aud174_read_project_logs(
            owner,
            container_pin=container_pin,
            completed_at_ms=completed_at,
            password_nonce=password_nonce,
            correlation_ids=correlations,
            deadline=live_stand.time.monotonic() + 30,
            docker_context=_aud174_docker_read_context(tmp_path),
        )


def test_live_caddy_probe_rejects_project_row_outside_its_window_inside_union(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner = object()
    container_pin = ("a" * 64, "b" * 64)
    password_nonce = "0" * 32
    correlations = {"desktop": "1" * 32, "mobile": "2" * 32}
    completed_at = {"desktop": 1_798_000_000_000, "mobile": 1_798_000_020_000}
    between_windows = live_stand._caddy_probe_timestamp_argument(
        completed_at["desktop"] + 10_000
    )
    desktop_payload = _aud174_access_log_row(
        f"/login?probe={correlations['desktop']}&password=REDACTED"
    ).split(b" ", 1)[1]
    mobile_row = _aud174_access_log_row(
        f"/login?probe={correlations['mobile']}&password=REDACTED",
        timestamp=live_stand._caddy_probe_timestamp_argument(completed_at["mobile"]),
    )
    output = between_windows.encode("ascii") + b" " + desktop_payload + mobile_row
    context = _aud174_docker_read_context(tmp_path)
    monkeypatch.setattr(
        live_stand,
        "_run_live_bounded_read",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["docker", "logs"], 0, stdout=output, stderr=b""
        ),
    )
    monkeypatch.setattr(
        live_stand,
        "_assert_live_caddy_container_pin",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(
        live_stand.StandError,
        match="Caddy access-log redaction proof failed",
    ):
        _aud174_read_project_logs(
            owner,
            container_pin=container_pin,
            completed_at_ms=completed_at,
            password_nonce=password_nonce,
            correlation_ids=correlations,
            deadline=live_stand.time.monotonic() + 30,
            docker_context=context,
        )


def test_live_caddy_probe_does_not_query_logs_after_container_pin_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner = object()
    container_pin = ("a" * 64, "b" * 64)
    calls: list[object] = []
    pin_calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        live_stand,
        "_run_live_bounded_read",
        lambda *args, **kwargs: calls.append(args),
    )

    def fail_on_pin_change(
        _owner: object,
        pin: tuple[str, str],
        **_kwargs: object,
    ) -> None:
        pin_calls.append(pin)
        raise live_stand.StandError("private owner detail")

    monkeypatch.setattr(
        live_stand, "_assert_live_caddy_container_pin", fail_on_pin_change
    )
    with pytest.raises(live_stand.StandError) as error:
        _aud174_read_project_logs(
            owner,
            container_pin=container_pin,
            completed_at_ms={"desktop": 1_798_000_000_000, "mobile": 1_798_000_000_100},
            password_nonce="f" * 32,
            correlation_ids={"desktop": "1" * 32, "mobile": "2" * 32},
            deadline=live_stand.time.monotonic() + 30,
            docker_context=_aud174_docker_read_context(tmp_path),
        )
    assert str(error.value) == "Caddy access-log redaction proof failed"
    assert calls == []
    assert pin_calls == [container_pin, container_pin]


def test_live_caddy_probe_hides_docker_timeout_diagnostics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    container_pin = ("a" * 64, "b" * 64)
    pin_checks: list[tuple[str, str]] = []

    def record_pin(
        _owner: object,
        pin: tuple[str, str],
        **_kwargs: object,
    ) -> None:
        pin_checks.append(pin)

    monkeypatch.setattr(live_stand, "_assert_live_caddy_container_pin", record_pin)

    def timeout(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(["docker", "logs"], 10, output=b"private URI")

    monkeypatch.setattr(live_stand, "_run_live_bounded_read", timeout)
    with pytest.raises(live_stand.StandError) as error:
        _aud174_read_project_logs(
            object(),
            container_pin=container_pin,
            completed_at_ms={"desktop": 1_798_000_000_000, "mobile": 1_798_000_000_100},
            password_nonce="f" * 32,
            correlation_ids={"desktop": "1" * 32, "mobile": "2" * 32},
            deadline=live_stand.time.monotonic() + 30,
            docker_context=_aud174_docker_read_context(tmp_path),
        )
    assert str(error.value) == "Caddy access-log redaction proof failed"
    assert "private URI" not in str(error.value)
    assert pin_checks == [container_pin, container_pin]


def test_live_caddy_probe_deadline_covers_final_container_recheck(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    now = [100.0]
    context = _aud174_docker_read_context(tmp_path)
    observed_deadlines: list[float] = []
    pin_deadlines: list[float | None] = []
    log_deadlines: list[float] = []
    pin_calls = 0
    completed_reads: list[subprocess.CompletedProcess[bytes]] = []
    correlations = {"desktop": "1" * 32, "mobile": "2" * 32}
    completed_at = {"desktop": 15, "mobile": 16}
    rows = _aud174_two_project_rows(completed_at, correlations)

    def read_markers(
        _directory: Path,
        *,
        started_at_ms: int,
        finished_at_ms: int,
        deadline: float | None = None,
    ) -> dict[str, int]:
        assert started_at_ms == 10
        assert finished_at_ms == 20
        assert deadline is not None
        observed_deadlines.append(deadline)
        return completed_at

    def check_pin(
        _owner: object,
        _pin: tuple[str, str],
        *,
        deadline: float | None = None,
        docker_context: live_stand._LiveDockerReadContext | None = None,
    ) -> None:
        nonlocal pin_calls
        pin_calls += 1
        pin_deadlines.append(deadline)
        assert docker_context is context
        if pin_calls == 2:
            now[0] = 125.001

    def read_logs(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        assert kwargs.get("context") is context
        log_deadlines.append(kwargs["deadline"])
        completed = subprocess.CompletedProcess(
            ["docker", "logs"], 0, stdout=rows, stderr=b""
        )
        completed_reads.append(completed)
        return completed

    monkeypatch.setattr(live_stand.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(live_stand, "_read_live_caddy_probe_observations", read_markers)
    monkeypatch.setattr(live_stand, "_assert_live_caddy_container_pin", check_pin)
    monkeypatch.setattr(live_stand, "_run_live_bounded_read", read_logs)

    with pytest.raises(
        live_stand.StandError,
        match="Caddy access-log redaction proof failed",
    ):
        live_stand._verify_live_caddy_probe_log(
            object(),
            tmp_path,
            started_at_ms=10,
            finished_at_ms=20,
            password_nonce="f" * 32,
            correlation_ids=correlations,
            container_pin=("a" * 64, "b" * 64),
            docker_context=context,
        )

    assert observed_deadlines == [125.0]
    # The 10-second capture budget is narrower than the 25-second total proof.
    assert log_deadlines == [110.0]
    assert pin_deadlines == [125.0, 125.0]
    assert len(completed_reads) == 1
    assert completed_reads[0].stdout == completed_reads[0].stderr == b""
    assert capsys.readouterr().out == ""


def _aud174_diagnostic_verifier_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    password_nonce: str,
    correlations: Mapping[str, str],
    pin_check: Callable[..., None] | None = None,
    log_reader: Callable[..., subprocess.CompletedProcess[bytes]] | None = None,
    marker_reader: Callable[..., Mapping[str, int]] | None = None,
    docker_context: live_stand._LiveDockerReadContext | None = None,
) -> tuple[
    object,
    Path,
    tuple[str, str],
    dict[str, int],
    live_stand._LiveDockerReadContext,
]:
    owner = object()
    output_directory = tmp_path / "playwright-output"
    output_directory.mkdir()
    container_pin = ("a" * 64, "b" * 64)
    completed_at = {"desktop": 1_798_000_000_000, "mobile": 1_798_000_000_100}
    context = docker_context or _aud174_docker_read_context(tmp_path)

    def valid_rows() -> bytes:
        return _aud174_two_project_rows(completed_at, correlations)

    monkeypatch.setattr(
        live_stand,
        "_read_live_caddy_probe_observations",
        marker_reader or (lambda *_args, **_kwargs: completed_at),
    )
    monkeypatch.setattr(
        live_stand,
        "_assert_live_caddy_container_pin",
        pin_check or (lambda *_args, **_kwargs: None),
    )
    monkeypatch.setattr(
        live_stand,
        "_run_live_bounded_read",
        log_reader
        or (
            lambda *_args, **_kwargs: subprocess.CompletedProcess(
                ["docker", "logs"], 0, stdout=valid_rows(), stderr=b""
            )
        ),
    )
    return owner, output_directory, container_pin, completed_at, context


@pytest.mark.parametrize(
    ("failure", "expected_stage"),
    [
        pytest.param("input", "input_validation", id="input-validation"),
        pytest.param("context", "context_resolution", id="context-resolution"),
        pytest.param("deadline", "deadline", id="deadline"),
        pytest.param("markers", "marker_observation", id="marker-observation"),
        pytest.param("pre-pin", "pre_pin", id="pre-pin"),
        pytest.param("log-read", "log_read", id="log-read"),
        pytest.param("log-size", "log_size", id="log-size"),
        pytest.param("nonce", "nonce_exposure", id="nonce-exposure"),
        pytest.param("stderr", "stderr_validation", id="stderr-validation"),
        pytest.param("correlation", "correlation_row", id="correlation-row"),
        pytest.param("project-row", "project_row", id="project-row"),
        pytest.param("post-pin", "post_pin", id="post-pin"),
        pytest.param("internal", "internal", id="internal"),
    ],
)
def test_live_caddy_probe_emits_only_fixed_stage_code_on_failure(
    failure: str,
    expected_stage: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    password_nonce = uuid4().hex
    correlations = {
        project: uuid4().hex for project in live_stand.LIVE_CADDY_PROBE_PROJECTS
    }
    secret_text = f"private-exception-{uuid4().hex}"
    owner = object()
    output_directory = tmp_path / "playwright-output"
    output_directory.mkdir()
    container_pin = ("a" * 64, "b" * 64)
    completed_at = {"desktop": 1_798_000_000_000, "mobile": 1_798_000_000_100}
    context: live_stand._LiveDockerReadContext | None = _aud174_docker_read_context(
        tmp_path
    )
    pin_calls = 0

    def read_markers(*_args: object, **_kwargs: object) -> Mapping[str, int]:
        if failure == "internal":
            raise KeyError(secret_text)
        return completed_at

    def read_logs(
        *_args: object, **_kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        if failure == "log-read":
            raise subprocess.TimeoutExpired(["docker", "logs"], 10, output=secret_text)
        rows = _aud174_two_project_rows(completed_at, correlations)
        if failure == "log-size":
            rows = b"x" * (live_stand._LIVE_CADDY_PROBE_MAX_BYTES + 1)
        if failure == "nonce":
            rows += password_nonce.encode("ascii") + b"\n"
        stderr = b""
        if failure == "stderr":
            stderr = b"unstructured " + secret_text.encode("ascii") + b"\n"
        if failure == "correlation":
            rows = _aud174_access_log_row(
                f"/login?probe={correlations['desktop']}&password=REDACTED",
                timestamp=live_stand._caddy_probe_timestamp_argument(
                    completed_at["desktop"]
                ),
            )
        if failure == "project-row":
            rows = b"".join(
                _aud174_access_log_row(
                    f"/login?probe={correlations[project]}&password=REDACTED",
                    status=500 if project == "desktop" else 200,
                    timestamp=live_stand._caddy_probe_timestamp_argument(
                        completed_at[project]
                    ),
                )
                for project in live_stand.LIVE_CADDY_PROBE_PROJECTS
            )
        return subprocess.CompletedProcess(
            ["docker", "logs"], 0, stdout=rows, stderr=stderr
        )

    def check_pin(*_args: object, **_kwargs: object) -> None:
        nonlocal pin_calls
        pin_calls += 1
        if failure == "pre-pin" and pin_calls == 1:
            raise live_stand.StandError(secret_text)
        if failure == "post-pin" and pin_calls == 2:
            raise live_stand.StandError(secret_text)

    monkeypatch.setattr(live_stand, "_read_live_caddy_probe_observations", read_markers)
    monkeypatch.setattr(live_stand, "_assert_live_caddy_container_pin", check_pin)
    monkeypatch.setattr(live_stand, "_run_live_bounded_read", read_logs)
    if failure == "context":

        def fail_context() -> live_stand._LiveDockerReadContext:
            raise live_stand.StandError(secret_text)

        monkeypatch.setattr(
            live_stand,
            "_new_live_docker_read_context",
            fail_context,
        )
        context = None
    elif failure == "deadline":
        monkeypatch.setattr(
            live_stand,
            "_live_probe_remaining",
            lambda _deadline: (_ for _ in ()).throw(live_stand.StandError(secret_text)),
        )
    elif failure == "markers":
        monkeypatch.setattr(
            live_stand,
            "_read_live_caddy_probe_observations",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                live_stand.StandError(secret_text)
            ),
        )

    with pytest.raises(live_stand.StandError) as caught:
        live_stand._verify_live_caddy_probe_log(
            owner,
            output_directory,
            started_at_ms=1_797_999_999_000,
            finished_at_ms=1_798_000_001_000,
            password_nonce=(
                "bad-" + password_nonce if failure == "input" else password_nonce
            ),
            correlation_ids=correlations,
            container_pin=container_pin,
            docker_context=context,
        )

    assert str(caught.value) == "Caddy access-log redaction proof failed"
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"live_caddy_probe_failure_stage={expected_stage}\n"
    assert secret_text not in captured.err
    assert password_nonce not in captured.err
    assert all(value not in captured.err for value in correlations.values())


def test_live_caddy_probe_success_emits_no_failure_stage(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    password_nonce = uuid4().hex
    correlations = {
        project: uuid4().hex for project in live_stand.LIVE_CADDY_PROBE_PROJECTS
    }
    owner, directory, pin, _completed_at, context = _aud174_diagnostic_verifier_inputs(
        monkeypatch,
        tmp_path,
        password_nonce=password_nonce,
        correlations=correlations,
    )

    live_stand._verify_live_caddy_probe_log(
        owner,
        directory,
        started_at_ms=1_797_999_999_000,
        finished_at_ms=1_798_000_001_000,
        password_nonce=password_nonce,
        correlation_ids=correlations,
        container_pin=pin,
        docker_context=context,
    )

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == "live Caddy access-log redaction=verified projects=2\n"
    assert "failure_stage" not in captured.out


def test_live_bounded_reader_caps_flood_and_reaps_its_direct_child(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    context = _aud174_docker_read_context(tmp_path)
    real_start = live_stand.fast_preflight._start_process
    started: list[subprocess.Popen[bytes]] = []

    def capture_start(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        process = real_start(*args, **kwargs)
        started.append(process)
        return process

    monkeypatch.setattr(live_stand.fast_preflight, "_start_process", capture_start)
    started_at = live_stand.time.monotonic()
    with pytest.raises(
        live_stand.StandError,
        match="Caddy access-log redaction proof failed",
    ):
        live_stand._run_live_bounded_read(
            (
                context.executable,
                "-c",
                "import os; block=b'x'*65536; [os.write(i % 2 + 1, block) for i in range(64)]",
            ),
            context=context,
            deadline=started_at + 5,
            maximum_bytes=1024,
            command_timeout_seconds=4,
        )

    assert live_stand.time.monotonic() - started_at < 3
    assert len(started) == 1
    assert started[0].returncode is not None


def test_live_bounded_reader_times_out_and_reaps_its_direct_child(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    context = _aud174_docker_read_context(tmp_path)
    real_start = live_stand.fast_preflight._start_process
    started: list[subprocess.Popen[bytes]] = []

    def capture_start(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        process = real_start(*args, **kwargs)
        started.append(process)
        return process

    monkeypatch.setattr(live_stand.fast_preflight, "_start_process", capture_start)
    started_at = live_stand.time.monotonic()
    with pytest.raises(
        live_stand.StandError,
        match="Caddy access-log redaction proof failed",
    ):
        live_stand._run_live_bounded_read(
            (context.executable, "-c", "import time; time.sleep(30)"),
            context=context,
            deadline=started_at + 3,
            maximum_bytes=1024,
            command_timeout_seconds=1,
        )

    assert live_stand.time.monotonic() - started_at < 2
    assert len(started) == 1
    assert started[0].returncode is not None


def test_live_bounded_reader_reaps_child_after_its_pipes_close(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    context = _aud174_docker_read_context(tmp_path)
    real_start = live_stand.fast_preflight._start_process
    started: list[subprocess.Popen[bytes]] = []

    def capture_start(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        process = real_start(*args, **kwargs)
        started.append(process)
        return process

    monkeypatch.setattr(live_stand.fast_preflight, "_start_process", capture_start)
    started_at = live_stand.time.monotonic()
    with pytest.raises(
        live_stand.StandError,
        match="Caddy access-log redaction proof failed",
    ):
        live_stand._run_live_bounded_read(
            (
                context.executable,
                "-c",
                # The parent bounds this child to one second and then reaps it.
                "import os, time; os.close(1); os.close(2); time.sleep(30)",
            ),
            context=context,
            deadline=started_at + 3,
            maximum_bytes=1024,
            command_timeout_seconds=1,
        )

    assert live_stand.time.monotonic() - started_at < 2
    assert len(started) == 1
    assert started[0].returncode is not None


def test_live_caddy_probe_rejects_malformed_or_nonregular_observations(
    tmp_path: Path,
) -> None:
    desktop = tmp_path / "aud174-caddy-probe-desktop.json"
    mobile = tmp_path / "aud174-caddy-probe-mobile.json"
    desktop.write_text("{", encoding="utf-8")
    mobile.write_text(
        json.dumps(
            {
                "schema": "aud174-caddy-probe-v1",
                "project": "mobile",
                "completed_at_ms": 2_000,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        live_stand.StandError, match="Caddy access-log redaction proof failed"
    ):
        live_stand._read_live_caddy_probe_observations(
            tmp_path, started_at_ms=500, finished_at_ms=2_500
        )
    desktop.unlink(missing_ok=True)
    desktop.mkdir()
    with pytest.raises(
        live_stand.StandError, match="Caddy access-log redaction proof failed"
    ):
        live_stand._read_live_caddy_probe_observations(
            tmp_path, started_at_ms=500, finished_at_ms=2_500
        )


def _aud174_full_probe_setup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[
    live_stand.StandOwner,
    live_stand.ComposeResourceEvidence,
    live_stand._LiveDockerReadContext,
    dict[str, Any],
]:
    project_name = _PROJECTION_PROJECT
    model = _projection_model()
    bind_source = str(tmp_path / "Caddyfile")
    model["services"].update(
        {
            "caddy": {
                "volumes": [
                    {
                        "type": "bind",
                        "source": bind_source,
                        "target": "/etc/caddy/Caddyfile",
                    },
                    {
                        "type": "volume",
                        "source": "app-data",
                        "target": "/data",
                    },
                ]
            },
            "frontend": {},
        }
    )
    evidence = live_stand._compose_resource_evidence_from_project(
        model,
        project_name,
        _port_map(),
    )
    assert evidence.stack == live_stand.LIVE_STACK_FULL
    assert set(evidence.managed_services) == {"backend", "caddy", "frontend"}
    daemon_fingerprint = hashlib.sha256(b"synthetic-daemon").hexdigest()
    owner = live_stand.StandOwner(
        repository=str(tmp_path),
        worktree=str(tmp_path),
        project_name=project_name,
        published_ports=tuple(_port_map().items()),
        schema_version=live_stand.OWNER_SCHEMA_VERSION,
        daemon_fingerprint=daemon_fingerprint,
        compose_resource_fingerprint=evidence.fingerprint,
        stack=live_stand.LIVE_STACK_FULL,
        service_roots=evidence.service_roots,
        selected_services=evidence.selected_services,
    )
    context = _aud174_docker_read_context(tmp_path)
    caddy_id = _batched_inspect_test_id(8101)
    backend_id = _batched_inspect_test_id(8102)
    stopped_frontend_id = _batched_inspect_test_id(8103)
    bind_mount = {
        "Type": "bind",
        "Name": "",
        "Source": bind_source,
        "Destination": "/etc/caddy/Caddyfile",
        "Driver": "",
        "Mode": "ro",
        "RW": False,
        "Propagation": "rprivate",
    }
    volume_name = f"{project_name}_app-data"
    volume_mount = {
        "Type": "volume",
        "Name": volume_name,
        "Source": volume_name,
        "Destination": "/data",
        "Driver": "local",
        "Mode": "z",
        "RW": True,
        "Propagation": "",
    }
    raw_caddy = {
        "Id": caddy_id,
        "Name": f"/{project_name}-caddy-1",
        "Image": "sha256:" + "a" * 64,
        "Config": {
            "Image": "caddy:2",
            "Labels": {
                "com.docker.compose.project": project_name,
                "com.docker.compose.service": "caddy",
                "com.docker.compose.oneoff": "False",
            },
        },
        "Mounts": [bind_mount, volume_mount],
        "State": {"Running": True, "Status": "running"},
    }
    rows = {
        caddy_id: {
            "Id": caddy_id,
            "ProjectLabel": project_name,
            "ServiceLabel": "caddy",
            "OneoffLabel": "False",
            "Mounts": [
                {"Type": "bind", "Name": None},
                {"Type": "volume", "Name": volume_name},
            ],
        },
        backend_id: {
            "Id": backend_id,
            "ProjectLabel": project_name,
            "ServiceLabel": "backend",
            "OneoffLabel": "False",
            "Mounts": [{"Type": "volume", "Name": volume_name}],
        },
        stopped_frontend_id: {
            "Id": stopped_frontend_id,
            "ProjectLabel": project_name,
            "ServiceLabel": "frontend",
            "OneoffLabel": "False",
            "Mounts": [],
        },
    }
    state: dict[str, Any] = {
        "owner": owner,
        "evidence": evidence,
        "context": context,
        "ids": [caddy_id, backend_id, stopped_frontend_id],
        "caddy_id": caddy_id,
        "raw_caddy": raw_caddy,
        "rows": rows,
        "events": [],
        "owner_loads": 0,
        "resource_verifications": 0,
        "daemon_fingerprint": daemon_fingerprint,
        "daemon_fingerprints": None,
        "daemon_calls": 0,
        "expire_after": None,
        "clock": [100.0],
        "deadline": 125.0,
        "ps_outputs": None,
        "batch_output_override": None,
        "evidence_after_first": None,
        "owner_after_first": None,
    }

    def load_owner(_worktree: Path) -> live_stand.StandOwner:
        state["owner_loads"] += 1
        state["events"].append(("owner", state["owner_loads"]))
        if state["owner_loads"] > 1 and state["owner_after_first"] is not None:
            return state["owner_after_first"]
        return state["owner"]

    def daemon_fingerprint(
        *,
        deadline: float | None = None,
        docker_context: live_stand._LiveDockerReadContext | None = None,
    ) -> str:
        state["events"].append(("daemon", deadline, docker_context))
        state["daemon_calls"] += 1
        fingerprints = state["daemon_fingerprints"]
        if fingerprints is not None:
            return fingerprints[min(state["daemon_calls"] - 1, len(fingerprints) - 1)]
        return state["daemon_fingerprint"]

    def verify_resources(
        worktree: Path,
        observed_owner: live_stand.StandOwner,
        *,
        deadline: float | None = None,
        docker_context: live_stand._LiveDockerReadContext | None = None,
        **_kwargs: Any,
    ) -> live_stand.ComposeResourceEvidence:
        assert worktree == live_stand.WORKTREE
        assert observed_owner == state["owner"]
        state["resource_verifications"] += 1
        state["events"].append(("resources", deadline, docker_context))
        if (
            state["resource_verifications"] > 1
            and state["evidence_after_first"] is not None
        ):
            return state["evidence_after_first"]
        return state["evidence"]

    def docker_output(
        arguments: Sequence[str],
        _error_message: str,
        *,
        deadline: float | None = None,
        docker_context: live_stand._LiveDockerReadContext | None = None,
    ) -> str:
        normalized = tuple(arguments)
        state["events"].append(("docker", normalized, deadline, docker_context))
        assert deadline == state["deadline"]
        assert docker_context is context
        if normalized[:1] == ("ps",):
            assert normalized == (
                "ps",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                f"label=com.docker.compose.project={project_name}",
            )
            outputs = state["ps_outputs"]
            if outputs is None:
                output_ids = state["ids"]
            else:
                output_ids = outputs[min(state.get("ps_calls", 0), len(outputs) - 1)]
            state["ps_calls"] = state.get("ps_calls", 0) + 1
            result = "".join(f"{container_id}\n" for container_id in output_ids)
            if state["expire_after"] == "ps" or (
                state["expire_after"] == "second-ps" and state["ps_calls"] == 2
            ):
                state["clock"][0] = state["deadline"]
            return result
        if normalized[:4] == ("inspect", "--type", "container", "--format"):
            template = normalized[4]
            assert template == live_stand._DOCKER_INSPECT_FORMAT
            batch_ids = list(normalized[5:])
            assert batch_ids
            assert set(batch_ids) <= set(state["ids"])
            override = state["batch_output_override"]
            if override is not None:
                result = override(batch_ids)
            else:
                result = (
                    "\n".join(
                        json.dumps(state["rows"][container_id], separators=(",", ":"))
                        for container_id in batch_ids
                    )
                    + "\n"
                )
            if state["expire_after"] == "batch":
                state["clock"][0] = state["deadline"]
            return result
        if normalized == ("inspect", "--type", "container", caddy_id):
            if state["expire_after"] == "caddy-inspect":
                state["clock"][0] = state["deadline"]
            return json.dumps(state["raw_caddy"], separators=(",", ":"))
        pytest.fail(f"unexpected Full Caddy Docker inspection: {normalized}")

    monkeypatch.setattr(live_stand, "WORKTREE", tmp_path)
    monkeypatch.setattr(live_stand, "load_stand_owner", load_owner)
    monkeypatch.setattr(live_stand, "docker_daemon_fingerprint", daemon_fingerprint)
    monkeypatch.setattr(
        live_stand, "_verify_stand_owner_compose_resources", verify_resources
    )
    monkeypatch.setattr(live_stand, "_docker_output", docker_output)
    return owner, evidence, context, state


def test_batched_docker_projection_retains_compose_oneoff_label() -> None:
    container_id = _batched_inspect_test_id(8100)
    row = _batched_inspect_test_row(container_id, service="caddy")

    parsed = live_stand._parse_docker_inspect_projection_batch(row, [container_id])

    assert parsed[0].oneoff_label == "False"


def test_live_full_caddy_pin_accepts_declared_mounts_and_stopped_other_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner, evidence, context, state = _aud174_full_probe_setup(monkeypatch, tmp_path)
    expected_identity = live_stand._core_container_record_from_inspect(
        state["caddy_id"], owner, evidence, state["raw_caddy"]
    ).identity
    assert dict(evidence.service_mounts)["caddy"] == (
        ("bind", str(tmp_path / "Caddyfile"), "/etc/caddy/Caddyfile"),
        ("volume", f"{owner.project_name}_app-data", "/data"),
    )
    deadline = state["deadline"]
    monkeypatch.setattr(live_stand.time, "monotonic", lambda: state["clock"][0])
    monkeypatch.setattr(
        live_stand,
        "_core_quiesce_container_inventory",
        lambda *_args, **_kwargs: pytest.fail(
            "Full admission must not use the Core quiesce inventory"
        ),
    )

    live_stand._assert_live_caddy_container_pin(
        owner,
        (state["caddy_id"], expected_identity),
        deadline=deadline,
        docker_context=context,
    )

    docker_events = [event[1] for event in state["events"] if event[0] == "docker"]
    assert docker_events[0][0] == "ps" and "--all" in docker_events[0]
    batch = next(
        event
        for event in docker_events
        if event[:4] == ("inspect", "--type", "container", "--format")
    )
    assert batch[5:] == tuple(state["ids"])
    assert ("inspect", "--type", "container", state["caddy_id"]) in docker_events
    assert any(row["ServiceLabel"] == "frontend" for row in state["rows"].values())
    assert all(
        event[2] == deadline and event[3] is context
        for event in state["events"]
        if event[0] == "docker"
    )
    assert [event[0] for event in state["events"]].index("resources") < [
        event[0] for event in state["events"]
    ].index("docker")
    assert state["resource_verifications"] >= 2
    assert state["owner_loads"] >= 2
    event_order = [event[0] for event in state["events"]]
    assert event_order == [
        "owner",
        "daemon",
        "resources",
        "docker",
        "docker",
        "docker",
        "docker",
        "owner",
        "daemon",
        "resources",
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        "foreign-bind-source",
        "wrong-bind-destination",
        "registered-but-wrong-volume",
        "missing-bind",
        "extra-bind",
        "duplicate-bind",
    ],
)
def test_live_full_caddy_inspect_mounts_match_verified_compose_contract(
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    owner, _evidence, context, state = _aud174_full_probe_setup(monkeypatch, tmp_path)
    mounts = state["raw_caddy"]["Mounts"]
    if mutation == "foreign-bind-source":
        mounts[0]["Source"] = str(tmp_path / "foreign-Caddyfile")
    elif mutation == "wrong-bind-destination":
        mounts[0]["Destination"] = "/etc/caddy/other.conf"
    elif mutation == "registered-but-wrong-volume":
        mounts[1]["Name"] = "shared-unused"
    elif mutation == "missing-bind":
        del mounts[0]
    elif mutation == "extra-bind":
        mounts.append(
            {
                "Type": "bind",
                "Name": "",
                "Source": str(tmp_path / "extra"),
                "Destination": "/extra",
                "RW": False,
            }
        )
    else:
        assert mutation == "duplicate-bind"
        mounts.append(dict(mounts[0]))
    monkeypatch.setattr(live_stand.time, "monotonic", lambda: state["clock"][0])

    with pytest.raises(
        live_stand.StandError, match="Caddy access-log redaction proof failed"
    ):
        live_stand._assert_live_caddy_container_pin(
            owner,
            (state["caddy_id"], "irrelevant-expected-identity"),
            deadline=state["deadline"],
            docker_context=context,
        )

    docker_events = [event[1] for event in state["events"] if event[0] == "docker"]
    assert ("inspect", "--type", "container", state["caddy_id"]) in docker_events
    assert sum(event[0] == "ps" for event in docker_events) == 1


@pytest.mark.parametrize(
    "case",
    [
        "foreign-project",
        "orphan-service",
        "oneoff-true",
        "oneoff-missing",
        "oneoff-malformed",
        "unregistered-volume",
        "bind-with-name",
        "missing-inspect-response",
        "duplicate-inspect-response",
    ],
)
def test_live_full_caddy_inventory_rejects_unowned_or_ambiguous_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case: str,
) -> None:
    owner, _evidence, context, state = _aud174_full_probe_setup(monkeypatch, tmp_path)
    caddy_id = state["caddy_id"]
    caddy_row = state["rows"][caddy_id]
    if case == "foreign-project":
        caddy_row["ProjectLabel"] = "ue-live-fedcba9876543210"
    elif case == "orphan-service":
        state["rows"][state["ids"][1]]["ServiceLabel"] = "removed-service"
    elif case == "oneoff-true":
        caddy_row["OneoffLabel"] = "True"
    elif case == "oneoff-missing":
        caddy_row["OneoffLabel"] = None
    elif case == "oneoff-malformed":
        caddy_row["OneoffLabel"] = "false"
    elif case == "unregistered-volume":
        caddy_row["Mounts"].append({"Type": "volume", "Name": "foreign-volume"})
    elif case == "bind-with-name":
        caddy_row["Mounts"][0]["Name"] = "not-a-volume"
    elif case == "missing-inspect-response":
        state["batch_output_override"] = (
            lambda ids: json.dumps(state["rows"][ids[0]], separators=(",", ":")) + "\n"
        )
    else:
        assert case == "duplicate-inspect-response"
        state["batch_output_override"] = (
            lambda ids: "\n".join(
                json.dumps(state["rows"][ids[0]], separators=(",", ":"))
                for _ in range(len(ids))
            )
            + "\n"
        )
    monkeypatch.setattr(live_stand.time, "monotonic", lambda: state["clock"][0])

    with pytest.raises(
        live_stand.StandError, match="Caddy access-log redaction proof failed"
    ):
        live_stand._assert_live_caddy_container_pin(
            owner,
            (caddy_id, "irrelevant-expected-identity"),
            deadline=state["deadline"],
            docker_context=context,
        )

    docker_events = [event[1] for event in state["events"] if event[0] == "docker"]
    assert any(
        event[:4] == ("inspect", "--type", "container", "--format")
        for event in docker_events
    )
    assert ("inspect", "--type", "container", caddy_id) not in docker_events


def test_live_full_caddy_inventory_rejects_too_many_captured_ids_before_inspect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner, _evidence, context, state = _aud174_full_probe_setup(monkeypatch, tmp_path)
    state["ids"] = [_batched_inspect_test_id(value) for value in range(8_100, 8_165)]
    monkeypatch.setattr(live_stand.time, "monotonic", lambda: state["clock"][0])

    with pytest.raises(
        live_stand.StandError, match="Caddy access-log redaction proof failed"
    ):
        live_stand._assert_live_caddy_container_pin(
            owner,
            (state["caddy_id"], "irrelevant-expected-identity"),
            deadline=state["deadline"],
            docker_context=context,
        )

    assert not any(
        event[0] == "docker" and event[1][0] == "inspect" for event in state["events"]
    )
    assert any(
        event[0] == "docker" and event[1][0] == "ps" for event in state["events"]
    )


@pytest.mark.parametrize("expire_after", ["ps", "batch", "caddy-inspect", "second-ps"])
def test_live_full_caddy_inventory_stops_on_expired_deadline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    expire_after: str,
) -> None:
    owner, _evidence, context, state = _aud174_full_probe_setup(monkeypatch, tmp_path)
    state["expire_after"] = expire_after
    monkeypatch.setattr(live_stand.time, "monotonic", lambda: state["clock"][0])

    with pytest.raises(
        live_stand.StandError, match="Caddy access-log redaction proof failed"
    ):
        live_stand._assert_live_caddy_container_pin(
            owner,
            (state["caddy_id"], "irrelevant-expected-identity"),
            deadline=state["deadline"],
            docker_context=context,
        )

    docker_events = [event[1] for event in state["events"] if event[0] == "docker"]
    if expire_after == "ps":
        assert docker_events[-1][0] == "ps"
    elif expire_after == "batch":
        assert docker_events[-1][:4] == (
            "inspect",
            "--type",
            "container",
            "--format",
        )
    elif expire_after == "caddy-inspect":
        assert docker_events[-1] == (
            "inspect",
            "--type",
            "container",
            state["caddy_id"],
        )
    else:
        assert expire_after == "second-ps"
        assert docker_events[-1][0] == "ps"
    if expire_after in {"ps", "batch"}:
        assert not any(
            event[0] == "docker"
            and event[1][0] == "inspect"
            and "--format" not in event[1]
            for event in state["events"]
        )
    else:
        assert (
            sum(
                event == ("inspect", "--type", "container", state["caddy_id"])
                for event in docker_events
            )
            == 1
        )


def test_live_full_caddy_inventory_rechecks_owner_daemon_and_resources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner, evidence, context, state = _aud174_full_probe_setup(monkeypatch, tmp_path)
    owner_drift = replace(owner, project_name="ue-live-fedcba9876543210")
    state["owner_after_first"] = owner_drift
    monkeypatch.setattr(live_stand.time, "monotonic", lambda: state["clock"][0])

    with pytest.raises(
        live_stand.StandError, match="Caddy access-log redaction proof failed"
    ):
        live_stand._assert_live_caddy_container_pin(
            owner,
            (state["caddy_id"], "irrelevant-expected-identity"),
            deadline=state["deadline"],
            docker_context=context,
        )

    assert state["owner_loads"] >= 2
    assert state["resource_verifications"] >= 1
    assert evidence.stack == live_stand.LIVE_STACK_FULL
    docker_events = [event[1] for event in state["events"] if event[0] == "docker"]
    assert len(docker_events) == 4
    assert docker_events[0][0] == "ps" and docker_events[-1][0] == "ps"


def test_live_full_caddy_inventory_rechecks_daemon_after_captured_inventory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner, _evidence, context, state = _aud174_full_probe_setup(monkeypatch, tmp_path)
    state["daemon_fingerprints"] = [
        owner.daemon_fingerprint,
        hashlib.sha256(b"drifted-daemon").hexdigest(),
    ]
    monkeypatch.setattr(live_stand.time, "monotonic", lambda: state["clock"][0])

    with pytest.raises(
        live_stand.StandError, match="Caddy access-log redaction proof failed"
    ):
        live_stand._assert_live_caddy_container_pin(
            owner,
            (state["caddy_id"], "irrelevant-expected-identity"),
            deadline=state["deadline"],
            docker_context=context,
        )

    assert state["daemon_calls"] == 2
    assert state["owner_loads"] == 2
    assert len([event for event in state["events"] if event[0] == "docker"]) == 4


def test_live_full_caddy_inventory_rechecks_mount_evidence_after_capture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner, evidence, context, state = _aud174_full_probe_setup(monkeypatch, tmp_path)
    state["evidence_after_first"] = replace(
        evidence,
        service_mounts=(
            (
                "caddy",
                (("bind", str(tmp_path / "unverified.conf"), "/etc/caddy/Caddyfile"),),
            ),
        ),
    )
    monkeypatch.setattr(live_stand.time, "monotonic", lambda: state["clock"][0])

    with pytest.raises(
        live_stand.StandError, match="Caddy access-log redaction proof failed"
    ):
        live_stand._assert_live_caddy_container_pin(
            owner,
            (state["caddy_id"], "irrelevant-expected-identity"),
            deadline=state["deadline"],
            docker_context=context,
        )

    docker_events = [event[1] for event in state["events"] if event[0] == "docker"]
    assert len(docker_events) == 4
    assert docker_events[-1][0] == "ps"
    assert state["resource_verifications"] == 2


def test_live_full_caddy_inventory_rejects_project_id_change_after_capture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner, _evidence, context, state = _aud174_full_probe_setup(monkeypatch, tmp_path)
    state["ps_outputs"] = [
        list(state["ids"]),
        [*state["ids"], _batched_inspect_test_id(8104)],
    ]
    monkeypatch.setattr(live_stand.time, "monotonic", lambda: state["clock"][0])

    with pytest.raises(
        live_stand.StandError, match="Caddy access-log redaction proof failed"
    ):
        live_stand._assert_live_caddy_container_pin(
            owner,
            (state["caddy_id"], "irrelevant-expected-identity"),
            deadline=state["deadline"],
            docker_context=context,
        )

    docker_events = [event[1] for event in state["events"] if event[0] == "docker"]
    assert len([event for event in docker_events if event[0] == "ps"]) == 2
    assert docker_events[-1][0] == "ps"


def test_live_full_caddy_inventory_rejects_daemon_mismatch_before_project_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner, _evidence, context, state = _aud174_full_probe_setup(monkeypatch, tmp_path)
    state["daemon_fingerprint"] = hashlib.sha256(b"other-daemon").hexdigest()
    monkeypatch.setattr(live_stand.time, "monotonic", lambda: state["clock"][0])

    with pytest.raises(
        live_stand.StandError, match="Caddy access-log redaction proof failed"
    ):
        live_stand._assert_live_caddy_container_pin(
            owner,
            (state["caddy_id"], "irrelevant-expected-identity"),
            deadline=state["deadline"],
            docker_context=context,
        )

    assert not any(event[0] in {"resources", "docker"} for event in state["events"])


def test_live_full_caddy_inventory_does_not_accept_owner_without_daemon_pin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner, _evidence, context, state = _aud174_full_probe_setup(monkeypatch, tmp_path)
    unsigned_legacy_owner = replace(
        owner,
        schema_version=live_stand.PREVIOUS_OWNER_SCHEMA_VERSION,
        daemon_fingerprint=None,
        compose_resource_fingerprint=None,
        selected_services=(),
    )
    state["owner"] = unsigned_legacy_owner
    monkeypatch.setattr(live_stand.time, "monotonic", lambda: state["clock"][0])

    with pytest.raises(live_stand.StandError):
        live_stand._assert_live_caddy_container_pin(
            unsigned_legacy_owner,
            (state["caddy_id"], "irrelevant-expected-identity"),
            deadline=state["deadline"],
            docker_context=context,
        )

    assert not any(event[0] in {"resources", "docker"} for event in state["events"])


def test_live_caddy_pin_dispatch_preserves_core_verifier(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner = live_stand.StandOwner(
        repository=str(tmp_path),
        worktree=str(tmp_path),
        project_name=_PROJECTION_PROJECT,
        published_ports=tuple(_port_map().items()),
        schema_version=live_stand.OWNER_SCHEMA_VERSION,
        daemon_fingerprint=hashlib.sha256(b"core-daemon").hexdigest(),
        compose_resource_fingerprint="1" * 64,
        stack=live_stand.LIVE_STACK_CORE,
        service_roots=live_stand.LIVE_CORE_SERVICE_ROOTS,
        selected_services=live_stand.LIVE_CORE_EXPECTED_SERVICES,
    )
    context = _aud174_docker_read_context(tmp_path)
    expected = (_batched_inspect_test_id(8200), "2" * 64)
    calls: list[tuple[live_stand.StandOwner, float | None, object | None]] = []

    def verify_core(
        observed_owner: live_stand.StandOwner,
        *,
        deadline: float | None = None,
        docker_context: object | None = None,
    ) -> tuple[str, str]:
        calls.append((observed_owner, deadline, docker_context))
        return expected

    monkeypatch.setattr(live_stand, "_verified_live_core_caddy_container", verify_core)

    live_stand._assert_live_caddy_container_pin(
        owner,
        expected,
        deadline=33.0,
        docker_context=context,
    )

    assert calls == [(owner, 33.0, context)]


_LIVE_CORE_CADDY_MOUNT_FIELDS = (
    "Type",
    "Name",
    "Source",
    "Destination",
    "Driver",
    "Mode",
    "RW",
    "Propagation",
)


def _aud174_core_caddy_raw_record(
    owner: live_stand.StandOwner, service: str, index: int
) -> dict[str, Any]:
    container_id = f"{index:064x}"
    labels = {
        "com.docker.compose.project": owner.project_name,
        "com.docker.compose.service": service,
        "com.docker.compose.oneoff": "False",
        "org.example.owner-proof": f"owned:{service}",
    }
    mounts: list[dict[str, Any]] = []
    if service == "caddy":
        mounts.append(
            {
                "Type": "bind",
                "Source": "/workspace/infrastructure/Caddyfile",
                "Destination": "/etc/caddy/Caddyfile",
                "Mode": "ro",
                "RW": False,
                "Propagation": "rprivate",
            }
        )
    elif service == "backend":
        mounts.append(
            {
                "Type": "volume",
                "Name": f"{owner.project_name}_app-data",
                "Source": "/var/lib/docker/volumes/app-data/_data",
                "Destination": "/data",
                "Driver": "local",
                "Mode": "z",
                "RW": True,
                "Propagation": "",
            }
        )
    is_caddy = service == "caddy"
    return {
        "Id": container_id,
        "Name": f"/{owner.project_name}-{service}-1",
        "Image": f"sha256:{index:064x}",
        "Config": {
            "Image": f"example/{service}:private-test",
            "Labels": labels,
        },
        "Mounts": mounts,
        "State": {
            "Running": is_caddy,
            "Status": "running" if is_caddy else "exited",
            "Health": {"Status": "healthy"} if is_caddy else None,
        },
    }


def _aud174_core_caddy_wire_record(record: dict[str, Any]) -> dict[str, Any]:
    state = record["State"]
    health = state["Health"]
    return {
        "Id": record["Id"],
        "Name": record["Name"],
        "Image": record["Image"],
        "ConfigImage": record["Config"]["Image"],
        "Labels": record["Config"]["Labels"],
        "State": {
            "Running": state["Running"],
            "Status": state["Status"],
            "Health": None if health is None else {"Status": health["Status"]},
        },
        "Mounts": record["Mounts"],
    }


def _aud174_core_caddy_normalized_record(
    record: dict[str, Any],
) -> dict[str, Any]:
    wire = _aud174_core_caddy_wire_record(record)
    state = wire["State"]
    return {
        "Id": wire["Id"],
        "Name": wire["Name"],
        "Image": wire["Image"],
        "Config": {"Image": wire["ConfigImage"], "Labels": wire["Labels"]},
        "State": state,
        "Mounts": [
            {key: mount.get(key) for key in _LIVE_CORE_CADDY_MOUNT_FIELDS}
            for mount in wire["Mounts"]
        ],
    }


def _aud174_core_caddy_setup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    response_kind: str = "valid",
    expire_after: str | None = None,
) -> tuple[
    live_stand.StandOwner,
    live_stand.ComposeResourceEvidence,
    live_stand._LiveDockerReadContext,
    dict[str, Any],
]:
    project_name = _PROJECTION_PROJECT
    services = live_stand.LIVE_CORE_EXPECTED_SERVICES
    owner = live_stand.StandOwner(
        repository=str(tmp_path),
        worktree=str(tmp_path),
        project_name=project_name,
        published_ports=tuple(_port_map().items()),
        schema_version=live_stand.OWNER_SCHEMA_VERSION,
        daemon_fingerprint=hashlib.sha256(b"private-core-daemon").hexdigest(),
        compose_resource_fingerprint=hashlib.sha256(
            b"private-core-compose"
        ).hexdigest(),
        stack=live_stand.LIVE_STACK_CORE,
        service_roots=live_stand.LIVE_CORE_SERVICE_ROOTS,
        selected_services=services,
    )
    evidence = _projection_expected(core=True)
    context = _aud174_docker_read_context(tmp_path)
    deadline = 100.5
    now = [100.0]
    raw_records = {
        f"{index:064x}": _aud174_core_caddy_raw_record(owner, service, index)
        for index, service in enumerate(services, start=1)
    }
    container_ids = tuple(raw_records)
    events: list[tuple[str, Any]] = []
    state: dict[str, Any] = {
        "owner": owner,
        "evidence": evidence,
        "context": context,
        "deadline": deadline,
        "now": now,
        "raw_records": raw_records,
        "ids": container_ids,
        "events": events,
        "response_kind": response_kind,
        "expire_after": expire_after,
    }

    def load_owner(worktree: Path) -> live_stand.StandOwner:
        assert worktree == tmp_path
        events.append(("owner", worktree))
        return owner

    def daemon_fingerprint(
        *,
        deadline: float | None = None,
        docker_context: live_stand._LiveDockerReadContext | None = None,
    ) -> str:
        assert deadline == state["deadline"]
        assert docker_context is context
        events.append(("daemon", docker_context))
        assert owner.daemon_fingerprint is not None
        return owner.daemon_fingerprint

    def verify_resources(
        worktree: Path,
        observed_owner: live_stand.StandOwner,
        *,
        deadline: float | None = None,
        docker_context: live_stand._LiveDockerReadContext | None = None,
    ) -> live_stand.ComposeResourceEvidence:
        assert worktree == tmp_path
        assert observed_owner == owner
        assert deadline == state["deadline"]
        assert docker_context is context
        events.append(("resources", observed_owner))
        return evidence

    def bounded_read(
        command: Sequence[str],
        *,
        context: live_stand._LiveDockerReadContext,
        deadline: float,
        maximum_bytes: int,
        command_timeout_seconds: float,
    ) -> subprocess.CompletedProcess[bytes]:
        normalized = tuple(command)
        assert normalized[0] == "docker"
        assert context is context_value
        assert deadline == state["deadline"]
        assert maximum_bytes == live_stand._LIVE_CADDY_PROBE_MAX_BYTES
        assert (
            command_timeout_seconds == live_stand._LIVE_CADDY_PROBE_LOG_TIMEOUT_SECONDS
        )
        arguments = normalized[1:]
        events.append(("docker", arguments))
        if arguments[:1] == ("ps",):
            assert arguments == (
                "ps",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                f"label=com.docker.compose.project={project_name}",
            )
            if expire_after == "ps":
                now[0] = deadline
            output = "".join(f"{container_id}\n" for container_id in container_ids)
            return subprocess.CompletedProcess(normalized, 0, output.encode(), b"")
        assert arguments[:4] == ("inspect", "--type", "container", "--format"), (
            "Core Caddy pin must inspect the captured IDs in one bounded batch"
        )
        assert arguments[4] == live_stand._LIVE_CADDY_CORE_INSPECT_FORMAT
        assert arguments[5:] == container_ids
        lines = [
            json.dumps(
                _aud174_core_caddy_wire_record(raw_records[container_id]),
                separators=(",", ":"),
            )
            for container_id in container_ids
        ]
        if response_kind == "foreign":
            foreign = _aud174_core_caddy_wire_record(raw_records[container_ids[0]])
            foreign["Id"] = "f" * 64
            lines[0] = json.dumps(foreign, separators=(",", ":"))
        elif response_kind == "missing":
            lines.pop()
        elif response_kind == "duplicate":
            lines[-1] = lines[0]
        elif response_kind == "malformed":
            lines[0] = "{" + lines[0]
        elif response_kind == "duplicate-key":
            lines[0] = lines[0].replace(
                '"Name":', f'"Id":"{container_ids[0]}","Name":', 1
            )
        elif response_kind == "missing-field":
            lines[0] = lines[0].replace('"ConfigImage":', '"RemovedConfigImage":', 1)
        elif response_kind != "valid":
            raise AssertionError("unknown private test response case")
        if expire_after == "inspect":
            now[0] = deadline
        output = "\n".join(lines) + "\n"
        return subprocess.CompletedProcess(normalized, 0, output.encode(), b"")

    monkeypatch.setattr(live_stand, "WORKTREE", tmp_path)
    monkeypatch.setattr(live_stand, "_require_worktree", lambda: None)
    monkeypatch.setattr(live_stand.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(live_stand, "load_stand_owner", load_owner)
    monkeypatch.setattr(live_stand, "docker_daemon_fingerprint", daemon_fingerprint)
    monkeypatch.setattr(
        live_stand, "_verify_stand_owner_compose_resources", verify_resources
    )
    context_value = context
    monkeypatch.setattr(live_stand, "_run_live_bounded_read", bounded_read)
    return owner, evidence, context, state


def test_live_core_caddy_projection_preserves_identity_inputs_and_missing_mount_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner, evidence, context, state = _aud174_core_caddy_setup(monkeypatch, tmp_path)
    expected_records = tuple(state["raw_records"].values())
    encoded = (
        "\n".join(
            json.dumps(_aud174_core_caddy_wire_record(record), separators=(",", ":"))
            for record in expected_records
        )
        + "\n"
    )

    projected = live_stand._parse_live_core_caddy_inspect_batch(encoded, state["ids"])

    for actual, expected in zip(projected, expected_records, strict=True):
        normalized_expected = _aud174_core_caddy_normalized_record(expected)
        assert actual == normalized_expected
        actual_record = live_stand._core_container_record_from_inspect(
            expected["Id"], owner, evidence, actual
        )
        expected_record = live_stand._core_container_record_from_inspect(
            expected["Id"], owner, evidence, expected
        )
        assert actual_record == expected_record
    assert context is state["context"]


@pytest.mark.parametrize(
    "response_kind",
    ["foreign", "missing", "duplicate", "malformed", "duplicate-key", "missing-field"],
)
def test_live_core_caddy_batched_pin_rejects_nonbijective_or_malformed_responses(
    response_kind: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    owner, _evidence, context, state = _aud174_core_caddy_setup(
        monkeypatch, tmp_path, response_kind=response_kind
    )

    with pytest.raises(
        live_stand.StandError, match="Caddy access-log redaction proof failed"
    ) as error:
        live_stand._verified_live_core_caddy_container(
            owner, deadline=state["deadline"], docker_context=context
        )

    assert str(error.value) == "Caddy access-log redaction proof failed"
    assert "f" * 64 not in str(error.value)
    commands = [value for name, value in state["events"] if name == "docker"]
    assert commands[0][0] == "ps"
    assert len(commands) == 2
    assert commands[1][0:4] == ("inspect", "--type", "container", "--format")


def test_live_core_caddy_batched_pin_returns_the_existing_container_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner, evidence, context, state = _aud174_core_caddy_setup(monkeypatch, tmp_path)
    caddy_id = next(
        container_id
        for container_id, raw in state["raw_records"].items()
        if raw["Config"]["Labels"]["com.docker.compose.service"] == "caddy"
    )
    expected = live_stand._core_container_record_from_inspect(
        caddy_id, owner, evidence, state["raw_records"][caddy_id]
    )

    actual = live_stand._verified_live_core_caddy_container(
        owner, deadline=state["deadline"], docker_context=context
    )

    assert actual == (caddy_id, expected.identity)
    commands = [value for name, value in state["events"] if name == "docker"]
    assert len(commands) == 2
    assert commands[0][0] == "ps"
    assert commands[1][0:4] == ("inspect", "--type", "container", "--format")
    assert commands[1][5:] == state["ids"]
    assert len(state["ids"]) == len(live_stand.LIVE_CORE_EXPECTED_SERVICES)
    event_names = [name for name, _ in state["events"]]
    assert event_names.count("owner") == 2
    assert event_names.count("daemon") == 2
    assert event_names.count("resources") == 1


@pytest.mark.parametrize("expired_command", ["ps", "inspect"])
def test_live_core_caddy_batched_pin_stops_after_a_command_expires_deadline(
    expired_command: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    owner, _evidence, context, state = _aud174_core_caddy_setup(
        monkeypatch, tmp_path, expire_after=expired_command
    )

    with pytest.raises(
        live_stand.StandError, match="Caddy access-log redaction proof failed"
    ):
        live_stand._verified_live_core_caddy_container(
            owner, deadline=state["deadline"], docker_context=context
        )

    commands = [value for name, value in state["events"] if name == "docker"]
    expected_commands = ["ps"] if expired_command == "ps" else ["ps", "inspect"]
    assert [command[0] for command in commands] == expected_commands


def test_live_core_caddy_inspect_command_rejects_more_than_sixty_four_ids() -> None:
    ids = tuple(f"{index:064x}" for index in range(1, 66))

    with pytest.raises(live_stand._DockerProjectionError):
        live_stand._build_live_core_caddy_inspect_command(ids)


def test_live_core_caddy_projection_ignores_future_mount_fields_outside_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner, evidence, _context, state = _aud174_core_caddy_setup(monkeypatch, tmp_path)
    caddy_id, caddy_raw = next(
        (container_id, raw)
        for container_id, raw in state["raw_records"].items()
        if raw["Config"]["Labels"]["com.docker.compose.service"] == "caddy"
    )
    original_identity = live_stand._core_container_record_from_inspect(
        caddy_id, owner, evidence, caddy_raw
    ).identity
    caddy_raw["Mounts"][0]["FutureMetadata"] = {
        "version": 2,
        "opaque": ["ignored"],
    }
    encoded = (
        "\n".join(
            json.dumps(
                _aud174_core_caddy_wire_record(raw),
                separators=(",", ":"),
            )
            for raw in state["raw_records"].values()
        )
        + "\n"
    )

    parsed = live_stand._parse_live_core_caddy_inspect_batch(encoded, state["ids"])

    assert parsed == tuple(
        _aud174_core_caddy_normalized_record(raw)
        for raw in state["raw_records"].values()
    )
    caddy_index = state["ids"].index(caddy_id)
    assert "FutureMetadata" not in parsed[caddy_index]["Mounts"][0]
    actual_identity = live_stand._core_container_record_from_inspect(
        caddy_id, owner, evidence, parsed[caddy_index]
    ).identity
    assert actual_identity == original_identity


def test_live_core_caddy_template_uses_safe_health_map_lookup() -> None:
    assert (
        '"Health":{{if eq (index .State "Health") nil}}null{{else}}'
        '{"Status":{{json (index (index .State "Health") "Status")}}}{{end}}},'
    ) in live_stand._LIVE_CADDY_CORE_INSPECT_FORMAT


@pytest.mark.parametrize("missing", ["deadline", "docker_context"])
def test_live_core_caddy_pin_requires_deadline_and_context_before_any_read(
    missing: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner, _evidence, context, state = _aud174_core_caddy_setup(monkeypatch, tmp_path)

    with pytest.raises(
        live_stand.StandError, match="Caddy access-log redaction proof failed"
    ):
        if missing == "deadline":
            live_stand._verified_live_core_caddy_container(
                owner, docker_context=context
            )
        else:
            live_stand._verified_live_core_caddy_container(
                owner, deadline=state["deadline"]
            )

    assert state["events"] == []


def test_live_caddy_probe_brackets_one_union_read_within_the_shared_deadline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner = object()
    container_pin = ("a" * 64, "b" * 64)
    password_nonce = "0" * 32
    correlations = {"desktop": "1" * 32, "mobile": "2" * 32}
    completed_at = {"desktop": 1_798_000_000_000, "mobile": 1_798_000_000_100}
    started_at_ms = 1_798_000_000_000 - 200
    finished_at_ms = 1_798_000_000_100 + 200
    for project, timestamp_ms in completed_at.items():
        (tmp_path / f"aud174-caddy-probe-{project}.json").write_text(
            json.dumps(
                {
                    "schema": "aud174-caddy-probe-v1",
                    "project": project,
                    "completed_at_ms": timestamp_ms,
                }
            ),
            encoding="utf-8",
        )

    rows = b"".join(
        _aud174_access_log_row(
            f"/login?probe={correlations[project]}&password=REDACTED",
            timestamp=live_stand._caddy_probe_timestamp_argument(timestamp_ms),
        )
        for project, timestamp_ms in completed_at.items()
    )
    context = _aud174_docker_read_context(tmp_path)
    now = [100.0]
    events: list[str] = []
    log_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    completed_reads: list[subprocess.CompletedProcess[bytes]] = []

    def check_pin(
        observed_owner: object,
        observed_pin: tuple[str, str],
        *,
        deadline: float | None = None,
        docker_context: live_stand._LiveDockerReadContext | None = None,
    ) -> None:
        assert observed_owner is owner
        assert observed_pin == container_pin
        assert deadline == pytest.approx(125.0)
        assert docker_context is context
        events.append("pin")
        now[0] += 4.3

    def read_logs(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        events.append("logs")
        log_calls.append((args, kwargs))
        now[0] += 0.2
        completed = subprocess.CompletedProcess(
            ["docker", "logs"], 0, stdout=rows, stderr=b""
        )
        completed_reads.append(completed)
        return completed

    monkeypatch.setattr(live_stand.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(live_stand, "_assert_live_caddy_container_pin", check_pin)
    monkeypatch.setattr(live_stand, "_run_live_bounded_read", read_logs)

    live_stand._verify_live_caddy_probe_log(
        owner,
        tmp_path,
        started_at_ms=started_at_ms,
        finished_at_ms=finished_at_ms,
        password_nonce=password_nonce,
        correlation_ids=correlations,
        container_pin=container_pin,
        docker_context=context,
    )

    assert events == ["pin", "logs", "pin"]
    assert len(log_calls) == 1
    command = log_calls[0][0][0]
    assert command == [
        "docker",
        "logs",
        "--timestamps",
        "--since",
        live_stand._caddy_probe_timestamp_argument(
            min(
                timestamp - live_stand._LIVE_CADDY_PROBE_WINDOW_MS
                for timestamp in completed_at.values()
            )
        ),
        "--until",
        live_stand._caddy_probe_timestamp_argument(
            max(
                timestamp + live_stand._LIVE_CADDY_PROBE_WINDOW_MS
                for timestamp in completed_at.values()
            )
        ),
        container_pin[0],
    ]
    assert "--tail" not in command
    options = log_calls[0][1]
    assert options["context"] is context
    assert options["deadline"] == pytest.approx(114.3)
    assert options["maximum_bytes"] == live_stand._LIVE_CADDY_PROBE_MAX_BYTES
    assert (
        options["command_timeout_seconds"]
        <= live_stand._LIVE_CADDY_PROBE_LOG_TIMEOUT_SECONDS
    )
    assert now[0] < 125.0
    assert len(completed_reads) == 1
    assert completed_reads[0].stdout == completed_reads[0].stderr == b""
    assert list(tmp_path.glob("aud174-caddy-probe-*.json")) == []


@pytest.mark.parametrize(
    ("failure", "expected_stage"),
    [
        ("stdout-overflow", "log_size"),
        ("stderr-overflow", "log_size"),
        ("combined-overflow", "log_size"),
        ("exit", "log_exit"),
        ("pipe", "log_pipe_io"),
        ("wait", "log_read"),
    ],
)
@pytest.mark.parametrize("post_pin_failure", [False, True])
def test_live_caddy_real_reader_failure_diagnostics_and_final_pin_precedence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    failure: str,
    expected_stage: str,
    post_pin_failure: bool,
) -> None:
    owner = object()
    context = _aud174_docker_read_context(tmp_path)
    output_directory = tmp_path / "output"
    output_directory.mkdir()
    container_pin = ("a" * 64, "b" * 64)
    password_nonce = uuid4().hex
    correlations = {"desktop": uuid4().hex, "mobile": uuid4().hex}
    completed_at = {
        "desktop": 1_798_000_000_000,
        "mobile": 1_798_000_000_100,
    }
    cap = live_stand._LIVE_CADDY_PROBE_MAX_BYTES
    canary = f"private-reader-{uuid4().hex}"
    scripts = {
        "stdout-overflow": f"import sys; sys.stdout.buffer.write(b'x' * {cap + 1})",
        "stderr-overflow": f"import sys; sys.stderr.buffer.write(b'x' * {cap + 1})",
        "combined-overflow": (
            "import sys; "
            f"sys.stdout.buffer.write(b'x' * {cap // 2}); "
            "sys.stdout.buffer.flush(); "
            f"sys.stderr.buffer.write(b'y' * {cap - cap // 2 + 1})"
        ),
        "exit": f"import sys; sys.stderr.write({canary!r}); sys.exit(7)",
        "pipe": "import sys; sys.stdout.buffer.write(b'x' * 4096)",
        "wait": "import sys; sys.exit(0)",
    }
    real_start = live_stand.fast_preflight._start_process
    started: list[subprocess.Popen[bytes]] = []
    wait_attempts: list[float | None] = []

    def start_fixture(
        check: live_stand.fast_preflight.CheckSpec,
        *,
        repo_root: Path,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.Popen[bytes]:
        assert check.command[0] == context.executable
        assert check.command[1] == "logs"
        process = real_start(
            live_stand.fast_preflight.CheckSpec(
                "bounded-reader-fixture",
                (context.executable, "-c", scripts[failure]),
            ),
            repo_root=repo_root,
            env=env,
        )
        if failure == "wait":
            real_wait = process.wait

            def fail_first_wait(timeout: float | None = None) -> int:
                wait_attempts.append(timeout)
                if len(wait_attempts) == 1:
                    raise OSError(canary)
                return real_wait(timeout=timeout)

            monkeypatch.setattr(process, "wait", fail_first_wait)
        started.append(process)
        return process

    pin_calls: list[tuple[str, str]] = []

    def check_pin(
        _owner: object,
        pin: tuple[str, str],
        **_kwargs: object,
    ) -> None:
        pin_calls.append(pin)
        if post_pin_failure and len(pin_calls) == 2:
            raise live_stand.StandError(canary)

    monkeypatch.setattr(live_stand.fast_preflight, "_start_process", start_fixture)
    monkeypatch.setattr(
        live_stand,
        "_read_live_caddy_probe_observations",
        lambda *_args, **_kwargs: completed_at,
    )
    monkeypatch.setattr(live_stand, "_assert_live_caddy_container_pin", check_pin)

    if failure == "pipe":
        drain_name = (
            "_live_drain_windows_pipes"
            if os.name == "nt"
            else "_live_drain_posix_pipes"
        )
        real_drain = getattr(live_stand, drain_name)

        def fail_pipe_read(_descriptor: int, _size: int) -> bytes:
            raise OSError(canary)

        def drain_with_io_failure(
            process: subprocess.Popen[bytes],
            *,
            stdout: bytearray,
            stderr: bytearray,
            work_deadline: float,
            maximum_bytes: int,
        ) -> bool:
            # Patch only after startup, not subprocess's exec-error pipe.
            with monkeypatch.context() as pipe_patch:
                pipe_patch.setattr(live_stand.os, "read", fail_pipe_read)
                return real_drain(
                    process,
                    stdout=stdout,
                    stderr=stderr,
                    work_deadline=work_deadline,
                    maximum_bytes=maximum_bytes,
                )

        monkeypatch.setattr(live_stand, drain_name, drain_with_io_failure)

    with pytest.raises(live_stand.StandError) as caught:
        live_stand._verify_live_caddy_probe_log(
            owner,
            output_directory,
            started_at_ms=1_797_999_999_000,
            finished_at_ms=1_798_000_001_000,
            password_nonce=password_nonce,
            correlation_ids=correlations,
            container_pin=container_pin,
            docker_context=context,
        )

    stage = "post_pin" if post_pin_failure else expected_stage
    captured = capsys.readouterr()
    assert str(caught.value) == live_stand._LIVE_CADDY_PROBE_FAILURE
    assert captured.out == ""
    assert captured.err == f"live_caddy_probe_failure_stage={stage}\n"
    if failure == "wait":
        assert wait_attempts
    assert pin_calls == [container_pin, container_pin]
    assert len(started) == 1
    assert started[0].returncode is not None
    assert started[0].stdout is not None and started[0].stdout.closed
    assert started[0].stderr is not None and started[0].stderr.closed
    for value in (canary, password_nonce, *correlations.values()):
        assert value not in captured.err
        assert value not in str(caught.value)


@pytest.mark.parametrize("exit_code", [0, 7])
def test_live_bounded_reader_accepts_exact_combined_cap_and_preserves_exit_status(
    tmp_path: Path,
    exit_code: int,
) -> None:
    context = _aud174_docker_read_context(tmp_path)
    cap = live_stand._LIVE_CADDY_PROBE_MAX_BYTES
    first = cap // 2
    second = cap - first
    script = (
        "import sys; "
        f"sys.stdout.buffer.write(b'x' * {first}); "
        "sys.stdout.buffer.flush(); "
        f"sys.stderr.buffer.write(b'y' * {second}); "
        "sys.stderr.buffer.flush(); "
        f"sys.exit({exit_code})"
    )

    result = live_stand._run_live_bounded_read(
        (context.executable, "-c", script),
        context=context,
        deadline=live_stand.time.monotonic() + 10,
        maximum_bytes=cap,
        command_timeout_seconds=5,
    )

    assert result.returncode == exit_code
    assert result.stdout == b"x" * first
    assert result.stderr == b"y" * second


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("output_limit", "output_limit"),
        ("pipe_io", "pipe_io"),
        ("unrecognized-reason", "internal"),
        (None, "internal"),
        (17, "internal"),
    ],
)
def test_live_bounded_read_failure_reason_is_finite(reason: Any, expected: str) -> None:
    error = live_stand._LiveBoundedReadFailure(reason)

    assert error.reason == expected
    assert str(error) == live_stand._LIVE_CADDY_PROBE_FAILURE
    assert error.args == (live_stand._LIVE_CADDY_PROBE_FAILURE,)


def test_live_reset_registration_parser_accepts_only_six_unique_pairs() -> None:
    parser = getattr(live_stand, "_live_playwright_reset_registration_steps", None)
    assert callable(parser)
    expected = [
        (project, step)
        for project in ("desktop", "mobile")
        for step in ("arm-response", "click", "await-response")
    ]
    output = "".join(
        f"UE_LIVE_RESET_REGISTRATION_V1 project={project} step={step}\r\n"
        for project, step in expected * 3
    )
    assert parser(output) == expected


@pytest.mark.parametrize(
    "output",
    [
        "",
        "UE_LIVE_RESET_REGISTRATION_V1 project=desktop step=click",
        "UE_LIVE_RESET_REGISTRATION_V1 project=private step=click\n",
        "UE_LIVE_RESET_REGISTRATION_V1 project=desktop step=private\n",
        "UE_LIVE_RESET_REGISTRATION_V1 project=desktop step=click extra=x\n",
        "private UE_LIVE_RESET_REGISTRATION_V1 project=desktop step=click\n",
        "private\rUE_LIVE_RESET_REGISTRATION_V1 project=desktop step=click\n",
        "private\vUE_LIVE_RESET_REGISTRATION_V1 project=desktop step=click\n",
        "private\u2028UE_LIVE_RESET_REGISTRATION_V1 project=desktop step=click\n",
        "UE_LIVE_RESET_REGISTRATION_V1 project=desktop step=click\r\r\n",
        "\x1b[31mUE_LIVE_RESET_REGISTRATION_V1 project=desktop step=click\n",
        "x" * 1_024 + "\n",
    ],
)
def test_live_reset_registration_parser_rejects_untrusted_framing(
    output: str,
) -> None:
    parser = getattr(live_stand, "_live_playwright_reset_registration_steps", None)
    assert callable(parser)
    assert parser(output) == []


@pytest.mark.parametrize("return_code", [0, 1])
def test_live_reset_registration_runner_uses_failure_stdout_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    return_code: int,
) -> None:
    command = live_stand._live_e2e_command(mode="smoke")
    valid = "UE_LIVE_RESET_REGISTRATION_V1 project=desktop step=click\n"
    stderr_only = "UE_LIVE_RESET_REGISTRATION_V1 project=mobile step=await-response\n"
    private = "private-body https://private.invalid/?token=hidden"
    completed = subprocess.CompletedProcess(
        command,
        return_code,
        stdout=(valid + valid + private + "\n").encode(),
        stderr=(stderr_only + private).encode(),
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    if return_code:
        with pytest.raises(live_stand.StandError, match="exit code 1"):
            live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    else:
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")

    captured = capsys.readouterr()
    expected = ["+ " + " ".join(command)]
    if return_code:
        expected.append("live E2E reset-registration project=desktop step=click")
    outcome = "failed" if return_code else "passed"
    expected.append(f"live E2E outcome={outcome} exit_code={return_code}")
    assert captured.out.splitlines() == expected
    assert captured.err == ""
    assert private not in captured.out
    assert completed.stdout == completed.stderr == b""


def _aud174_install_window_log_selector(
    monkeypatch: pytest.MonkeyPatch,
    *,
    owner: object,
    container_pin: tuple[str, str],
    context: live_stand._LiveDockerReadContext,
    records: list[tuple[int, bytes, bytes]],
    now: list[float] | None = None,
    read_durations: tuple[float, ...] = (),
) -> dict[str, Any]:
    state: dict[str, Any] = {"events": [], "calls": [], "completed": []}

    def check_pin(
        observed_owner: object,
        observed_pin: tuple[str, str],
        *,
        deadline: float,
        docker_context: live_stand._LiveDockerReadContext,
    ) -> None:
        assert observed_owner is owner
        assert observed_pin == container_pin
        assert docker_context is context
        state["events"].append("pin")
        if now is not None:
            assert deadline == 125.0
            now[0] += 2.0

    def read_logs(
        command: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[bytes]:
        assert command[:3] == ["docker", "logs", "--timestamps"]
        assert command[3] == "--since"
        assert command[5] == "--until"
        assert command[7:] == [container_pin[0]]
        assert kwargs["context"] is context
        since_ns = live_stand._parse_live_docker_log_timestamp(
            command[4].encode("ascii")
        )
        until_ns = live_stand._parse_live_docker_log_timestamp(
            command[6].encode("ascii")
        )
        selected = [
            (stdout, stderr)
            for timestamp_ms, stdout, stderr in records
            if since_ns <= timestamp_ms * 1_000_000 <= until_ns
        ]
        stdout = b"".join(item[0] for item in selected)
        stderr = b"".join(item[1] for item in selected)
        state["events"].append("logs")
        state["calls"].append((list(command), dict(kwargs)))
        if now is not None:
            now[0] += read_durations[len(state["calls"]) - 1]
        if len(stdout) + len(stderr) > kwargs["maximum_bytes"]:
            raise live_stand._LiveBoundedReadFailure("output_limit")
        completed = subprocess.CompletedProcess(
            command, 0, stdout=stdout, stderr=stderr
        )
        state["completed"].append(completed)
        return completed

    monkeypatch.setattr(live_stand, "_assert_live_caddy_container_pin", check_pin)
    monkeypatch.setattr(live_stand, "_run_live_bounded_read", read_logs)
    if now is not None:
        monkeypatch.setattr(live_stand.time, "monotonic", lambda: now[0])
    return state


def test_live_caddy_probe_excludes_oversized_gap_between_project_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner = object()
    pin = ("a" * 64, "b" * 64)
    context = _aud174_docker_read_context(tmp_path)
    base = 1_798_000_000_000
    observed = {"desktop": base, "mobile": base + 120_000}
    correlations = {"desktop": "1" * 32, "mobile": "2" * 32}
    records = [
        (
            timestamp,
            _aud174_access_log_row(
                f"/login?probe={correlations[project]}&password=REDACTED",
                timestamp=live_stand._caddy_probe_timestamp_argument(timestamp),
            ),
            b"",
        )
        for project, timestamp in observed.items()
    ]
    gap_timestamp = base + 60_000
    gap_row = _aud174_access_log_row(
        "/health",
        timestamp=live_stand._caddy_probe_timestamp_argument(gap_timestamp),
    )
    cap = live_stand._LIVE_CADDY_PROBE_MAX_BYTES
    gap_rows = gap_row * (cap // len(gap_row) + 1)
    assert len(gap_rows) > cap
    records.append((gap_timestamp, gap_rows, b""))
    state = _aud174_install_window_log_selector(
        monkeypatch,
        owner=owner,
        container_pin=pin,
        context=context,
        records=records,
    )

    _aud174_read_project_logs(
        owner,
        container_pin=pin,
        completed_at_ms=observed,
        password_nonce="0" * 32,
        correlation_ids=correlations,
        deadline=live_stand.time.monotonic() + 25,
        docker_context=context,
    )

    assert state["events"] == ["pin", "logs", "logs", "pin"]
    assert len(state["completed"]) == 2
    assert all(result.stdout == result.stderr == b"" for result in state["completed"])


@pytest.mark.parametrize(
    ("mobile_offset", "expected_windows"),
    [
        (0, [(-5_000, 5_000)]),
        (2_000, [(-5_000, 7_000)]),
        (10_000, [(-5_000, 15_000)]),
        (10_001, [(-5_000, 5_000), (5_001, 15_001)]),
        (-10_001, [(-15_001, -5_001), (-5_000, 5_000)]),
        (-2_000, [(-7_000, 5_000)]),
    ],
)
def test_live_caddy_probe_coalesces_only_overlapping_or_touching_windows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mobile_offset: int,
    expected_windows: list[tuple[int, int]],
) -> None:
    owner = object()
    pin = ("a" * 64, "b" * 64)
    context = _aud174_docker_read_context(tmp_path)
    base = 1_798_000_000_000
    observed = {"desktop": base, "mobile": base + mobile_offset}
    correlations = {"desktop": "1" * 32, "mobile": "2" * 32}
    records = [
        (
            timestamp,
            _aud174_access_log_row(
                f"/login?probe={correlations[project]}&password=REDACTED",
                timestamp=live_stand._caddy_probe_timestamp_argument(timestamp),
            ),
            b"",
        )
        for project, timestamp in observed.items()
    ]
    state = _aud174_install_window_log_selector(
        monkeypatch,
        owner=owner,
        container_pin=pin,
        context=context,
        records=records,
    )

    _aud174_read_project_logs(
        owner,
        container_pin=pin,
        completed_at_ms=observed,
        password_nonce="0" * 32,
        correlation_ids=correlations,
        deadline=live_stand.time.monotonic() + 25,
        docker_context=context,
    )

    assert [(command[4], command[6]) for command, _kwargs in state["calls"]] == [
        (
            live_stand._caddy_probe_timestamp_argument(base + since),
            live_stand._caddy_probe_timestamp_argument(base + until),
        )
        for since, until in expected_windows
    ]
    assert state["events"] == ["pin", *(["logs"] * len(expected_windows)), "pin"]
    assert all(result.stdout == result.stderr == b"" for result in state["completed"])


def test_live_caddy_probe_disjoint_reads_share_bytes_and_capture_time(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner = object()
    pin = ("a" * 64, "b" * 64)
    context = _aud174_docker_read_context(tmp_path)
    base = 1_798_000_000_000
    observed = {"desktop": base, "mobile": base + 120_000}
    correlations = {"desktop": "1" * 32, "mobile": "2" * 32}
    rows = {
        project: _aud174_access_log_row(
            f"/login?probe={correlations[project]}&password=REDACTED",
            timestamp=live_stand._caddy_probe_timestamp_argument(timestamp),
        )
        for project, timestamp in observed.items()
    }
    benign_stderr = _aud174_access_log_row(
        "/health", timestamp=live_stand._caddy_probe_timestamp_argument(base)
    )
    now = [100.0]
    state = _aud174_install_window_log_selector(
        monkeypatch,
        owner=owner,
        container_pin=pin,
        context=context,
        records=[
            (base, rows["desktop"], benign_stderr),
            (observed["mobile"], b"", rows["mobile"]),
        ],
        now=now,
        read_durations=(3.0, 1.0),
    )

    _aud174_read_project_logs(
        owner,
        container_pin=pin,
        completed_at_ms=observed,
        password_nonce="0" * 32,
        correlation_ids=correlations,
        deadline=125.0,
        docker_context=context,
    )

    assert state["events"] == ["pin", "logs", "logs", "pin"]
    first = state["calls"][0][1]
    second = state["calls"][1][1]
    cap = live_stand._LIVE_CADDY_PROBE_MAX_BYTES
    assert first["maximum_bytes"] == cap
    assert second["maximum_bytes"] == cap - len(rows["desktop"]) - len(benign_stderr)
    assert first["deadline"] == second["deadline"] == 112.0
    assert first["command_timeout_seconds"] == pytest.approx(10.0)
    assert second["command_timeout_seconds"] == pytest.approx(7.0)
    assert now[0] == pytest.approx(108.0)
    assert all(result.stdout == result.stderr == b"" for result in state["completed"])


@pytest.mark.parametrize(
    ("failure", "expected_stage"),
    [
        ("duplicate", "correlation_row"),
        ("nonce", "nonce_exposure"),
        ("stderr-error", "stderr_validation"),
    ],
)
def test_live_caddy_probe_disjoint_captures_keep_cross_window_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: str,
    expected_stage: str,
) -> None:
    owner = object()
    pin = ("a" * 64, "b" * 64)
    context = _aud174_docker_read_context(tmp_path)
    base = 1_798_000_000_000
    observed = {"desktop": base, "mobile": base + 120_000}
    correlations = {"desktop": "1" * 32, "mobile": "2" * 32}
    nonce = "0" * 32
    rows = {
        project: _aud174_access_log_row(
            f"/login?probe={correlations[project]}&password=REDACTED",
            timestamp=live_stand._caddy_probe_timestamp_argument(timestamp),
        )
        for project, timestamp in observed.items()
    }
    second_stdout = rows["mobile"]
    second_stderr = b""
    second_timestamp = live_stand._caddy_probe_timestamp_argument(observed["mobile"])
    if failure == "duplicate":
        second_stdout += _aud174_access_log_row(
            f"/login?probe={correlations['desktop']}&password=REDACTED",
            timestamp=second_timestamp,
        )
    elif failure == "nonce":
        second_stderr = _aud174_access_log_row(
            "/health", timestamp=second_timestamp, message=nonce
        )
    else:
        second_stderr = _aud174_access_log_row(
            "/health", timestamp=second_timestamp, level="error"
        )
    state = _aud174_install_window_log_selector(
        monkeypatch,
        owner=owner,
        container_pin=pin,
        context=context,
        records=[
            (base, rows["desktop"], b""),
            (observed["mobile"], second_stdout, second_stderr),
        ],
    )

    with pytest.raises(live_stand._LiveCaddyProbeStageFailure) as caught:
        _aud174_read_project_logs(
            owner,
            container_pin=pin,
            completed_at_ms=observed,
            password_nonce=nonce,
            correlation_ids=correlations,
            deadline=live_stand.time.monotonic() + 25,
            docker_context=context,
        )

    assert caught.value.stage == expected_stage
    assert state["events"] == ["pin", "logs", "logs", "pin"]
    assert all(result.stdout == result.stderr == b"" for result in state["completed"])


def _aud174_install_real_window_children(
    monkeypatch: pytest.MonkeyPatch,
    *,
    owner: object,
    pin: tuple[str, str],
    context: live_stand._LiveDockerReadContext,
    scripts: list[str],
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "events": [],
        "started": [],
        "calls": [],
        "completed": [],
        "sizes": [],
    }
    real_start = live_stand.fast_preflight._start_process
    real_read = live_stand._run_live_bounded_read

    def start_fixture(
        check: live_stand.fast_preflight.CheckSpec,
        *,
        repo_root: Path,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.Popen[bytes]:
        assert check.command[0] == context.executable
        assert check.command[1] == "logs"
        index = len(state["started"])
        assert index < len(scripts)
        process = real_start(
            live_stand.fast_preflight.CheckSpec(
                "bounded-window-fixture",
                (context.executable, "-c", scripts[index]),
            ),
            repo_root=repo_root,
            env=env,
        )
        state["started"].append(process)
        return process

    def record_read(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        assert kwargs["context"] is context
        state["events"].append("logs")
        state["calls"].append((args, dict(kwargs)))
        result = real_read(*args, **kwargs)
        state["sizes"].append((len(result.stdout), len(result.stderr)))
        state["completed"].append(result)
        return result

    def check_pin(
        observed_owner: object,
        observed_pin: tuple[str, str],
        *,
        deadline: float,
        docker_context: live_stand._LiveDockerReadContext,
    ) -> None:
        assert observed_owner is owner
        assert observed_pin == pin
        assert docker_context is context
        assert deadline > 0
        state["events"].append("pin")

    monkeypatch.setattr(live_stand.fast_preflight, "_start_process", start_fixture)
    monkeypatch.setattr(live_stand, "_run_live_bounded_read", record_read)
    monkeypatch.setattr(live_stand, "_assert_live_caddy_container_pin", check_pin)
    return state


@pytest.mark.parametrize("extra_stream", [None, "stdout", "stderr"])
def test_live_caddy_disjoint_real_reads_enforce_aggregate_cap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    extra_stream: str | None,
) -> None:
    owner = object()
    pin = ("a" * 64, "b" * 64)
    context = _aud174_docker_read_context(tmp_path)
    base = 1_798_000_000_000
    observed = {"desktop": base, "mobile": base + 120_000}
    correlations = {"desktop": "1" * 32, "mobile": "2" * 32}
    rows = {
        project: _aud174_access_log_row(
            f"/login?probe={correlations[project]}&password=REDACTED",
            timestamp=live_stand._caddy_probe_timestamp_argument(timestamp),
        )
        for project, timestamp in observed.items()
    }
    cap = live_stand._LIVE_CADDY_PROBE_MAX_BYTES
    first_stderr = _aud174_access_log_row(
        "/health", timestamp=live_stand._caddy_probe_timestamp_argument(base)
    )
    padding_row = _aud174_access_log_row(
        "/health",
        timestamp=live_stand._caddy_probe_timestamp_argument(observed["mobile"]),
        message="",
    )
    padding = cap - sum(
        map(len, (rows["desktop"], first_stderr, rows["mobile"], padding_row))
    )
    assert padding > 0
    assert padding_row.count(b'"msg": ""') == 1
    first_script = (
        "import sys; "
        f"sys.stdout.buffer.write({rows['desktop']!r}); "
        "sys.stdout.buffer.flush(); "
        f"sys.stderr.buffer.write({first_stderr!r}); "
        "sys.stderr.buffer.flush(); "
    )
    second_script = (
        "import sys; "
        f"sys.stdout.buffer.write({rows['mobile']!r}); "
        "sys.stdout.buffer.flush(); "
        f"row = {padding_row!r}; "
        f'row = row.replace(b\'"msg": ""\', '
        f"b'\"msg\": \"' + b'x' * {padding} + b'\"', 1); "
        "sys.stderr.buffer.write(row); "
        "sys.stderr.buffer.flush(); "
    )
    if extra_stream is not None:
        second_script += f"sys.{extra_stream}.buffer.write(b'\\n'); "
    state = _aud174_install_real_window_children(
        monkeypatch,
        owner=owner,
        pin=pin,
        context=context,
        scripts=[first_script, second_script],
    )

    def read_project_logs() -> None:
        _aud174_read_project_logs(
            owner,
            container_pin=pin,
            completed_at_ms=observed,
            password_nonce="0" * 32,
            correlation_ids=correlations,
            deadline=live_stand.time.monotonic() + 25,
            docker_context=context,
        )

    if extra_stream is None:
        read_project_logs()
        assert sum(sum(size) for size in state["sizes"]) == cap
        assert len(state["completed"]) == 2
    else:
        with pytest.raises(live_stand._LiveCaddyProbeStageFailure) as caught:
            read_project_logs()
        assert caught.value.stage == "log_size"
        assert len(state["completed"]) == 1

    assert state["events"] == ["pin", "logs", "logs", "pin"]
    assert state["calls"][0][1]["maximum_bytes"] == cap
    assert state["calls"][1][1]["maximum_bytes"] == (
        cap - len(rows["desktop"]) - len(first_stderr)
    )
    assert state["calls"][0][1]["deadline"] == state["calls"][1][1]["deadline"]
    assert len(state["started"]) == 2
    for process in state["started"]:
        assert process.returncode is not None
        assert process.stdout is not None and process.stdout.closed
        assert process.stderr is not None and process.stderr.closed
    assert all(result.stdout == result.stderr == b"" for result in state["completed"])


@pytest.mark.parametrize("stream", ["stdout", "stderr", "crlf"])
def test_live_caddy_disjoint_reads_preserve_record_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stream: str,
) -> None:
    owner = object()
    pin = ("a" * 64, "b" * 64)
    context = _aud174_docker_read_context(tmp_path)
    base = 1_798_000_000_000
    observed = {"desktop": base, "mobile": base + 120_000}
    correlations = {"desktop": "1" * 32, "mobile": "2" * 32}
    rows = {
        project: _aud174_access_log_row(
            f"/login?probe={correlations[project]}&password=REDACTED",
            timestamp=live_stand._caddy_probe_timestamp_argument(timestamp),
        )
        for project, timestamp in observed.items()
    }
    desktop, mobile = rows["desktop"], rows["mobile"]
    split_at = desktop.index(b'"request"') + 4
    first, second = desktop[:split_at], desktop[split_at:] + mobile
    assert first and not first.endswith(b"\n")
    assert first + second == desktop + mobile
    if stream == "stdout":
        records = [(base, first, b""), (observed["mobile"], second, b"")]
    elif stream == "stderr":
        records = [(base, b"", first), (observed["mobile"], b"", second)]
    else:
        records = [
            (base, desktop[:-1] + b"\r\n", b""),
            (observed["mobile"], b"", mobile[:-1] + b"\r\n"),
        ]
    state = _aud174_install_window_log_selector(
        monkeypatch,
        owner=owner,
        container_pin=pin,
        context=context,
        records=records,
    )

    def read_project_logs() -> None:
        _aud174_read_project_logs(
            owner,
            container_pin=pin,
            completed_at_ms=observed,
            password_nonce="0" * 32,
            correlation_ids=correlations,
            deadline=live_stand.time.monotonic() + 25,
            docker_context=context,
        )

    if stream == "crlf":
        read_project_logs()
        assert state["events"] == ["pin", "logs", "logs", "pin"]
        assert len(state["completed"]) == 2
    else:
        with pytest.raises(live_stand._LiveCaddyProbeStageFailure) as caught:
            read_project_logs()
        expected = "project_row" if stream == "stdout" else "stderr_validation"
        assert caught.value.stage == expected
        assert state["events"] in (
            ["pin", "logs", "pin"],
            ["pin", "logs", "logs", "pin"],
        )
        assert state["completed"]
    assert state["events"].count("pin") == 2
    assert all(result.stdout == result.stderr == b"" for result in state["completed"])


@pytest.mark.parametrize("first_duration", [10.0, 10.25])
def test_live_caddy_disjoint_capture_deadline_prevents_second_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    first_duration: float,
) -> None:
    owner = object()
    pin = ("a" * 64, "b" * 64)
    context = _aud174_docker_read_context(tmp_path)
    base = 1_798_000_000_000
    observed = {"desktop": base, "mobile": base + 120_000}
    correlations = {"desktop": "1" * 32, "mobile": "2" * 32}
    rows = {
        project: _aud174_access_log_row(
            f"/login?probe={correlations[project]}&password=REDACTED",
            timestamp=live_stand._caddy_probe_timestamp_argument(timestamp),
        )
        for project, timestamp in observed.items()
    }
    records = [
        (timestamp, rows[project], b"") for project, timestamp in observed.items()
    ]
    now = [100.0]
    state = _aud174_install_window_log_selector(
        monkeypatch,
        owner=owner,
        container_pin=pin,
        context=context,
        records=records,
        now=now,
        read_durations=(first_duration,),
    )

    with pytest.raises(live_stand._LiveCaddyProbeStageFailure) as caught:
        _aud174_read_project_logs(
            owner,
            container_pin=pin,
            completed_at_ms=observed,
            password_nonce="0" * 32,
            correlation_ids=correlations,
            deadline=125.0,
            docker_context=context,
        )
    assert caught.value.stage == "deadline"
    assert state["events"] == ["pin", "logs", "pin"]
    assert len(state["calls"]) == 1
    assert state["calls"][0][1]["deadline"] == 112.0
    assert state["calls"][0][1]["command_timeout_seconds"] == pytest.approx(10.0)
    assert now[0] == pytest.approx(104.0 + first_duration)
    assert now[0] < 125.0
    assert len(state["completed"]) == 1
    assert state["completed"][0].stdout == b""
    assert state["completed"][0].stderr == b""


@pytest.mark.parametrize(
    ("failure", "expected_stage"),
    [("exit", "log_exit"), ("pipe", "log_pipe_io"), ("wait", "log_read")],
)
@pytest.mark.parametrize("post_pin_failure", [False, True])
def test_live_caddy_disjoint_second_read_failure_preserves_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    failure: str,
    expected_stage: str,
    post_pin_failure: bool,
) -> None:
    owner = object()
    pin = ("a" * 64, "b" * 64)
    context = _aud174_docker_read_context(tmp_path)
    base = 1_798_000_000_000
    observed = {"desktop": base, "mobile": base + 120_000}
    correlations = {"desktop": uuid4().hex, "mobile": uuid4().hex}
    rows = {
        project: _aud174_access_log_row(
            f"/login?probe={correlations[project]}&password=REDACTED",
            timestamp=live_stand._caddy_probe_timestamp_argument(timestamp),
        )
        for project, timestamp in observed.items()
    }
    nonce = uuid4().hex
    canary = f"private-second-read-{uuid4().hex}"
    scripts = [
        (
            "import sys; "
            f"sys.stdout.buffer.write({rows['desktop']!r}); "
            "sys.stdout.buffer.flush(); "
        ),
        (
            "import sys; "
            f"sys.stdout.buffer.write({rows['mobile']!r}); "
            "sys.stdout.buffer.flush(); "
        ),
    ]
    if failure == "exit":
        scripts[1] += f"sys.stderr.write({canary!r}); sys.exit(7); "
    state = _aud174_install_real_window_children(
        monkeypatch, owner=owner, pin=pin, context=context, scripts=scripts
    )
    wait_attempts: list[float | None] = []
    pipe_attempts: list[int] = []

    if failure == "wait":
        fixture_start = live_stand.fast_preflight._start_process

        def start_with_second_wait_failure(
            check: live_stand.fast_preflight.CheckSpec,
            *,
            repo_root: Path,
            env: Mapping[str, str] | None = None,
        ) -> subprocess.Popen[bytes]:
            process = fixture_start(check, repo_root=repo_root, env=env)
            if len(state["started"]) == 2:
                assert process is state["started"][1]
                real_wait = process.wait

                def fail_first_wait(timeout: float | None = None) -> int:
                    wait_attempts.append(timeout)
                    if len(wait_attempts) == 1:
                        raise OSError(canary)
                    return real_wait(timeout=timeout)

                monkeypatch.setattr(process, "wait", fail_first_wait)
            return process

        monkeypatch.setattr(
            live_stand.fast_preflight, "_start_process", start_with_second_wait_failure
        )

    if failure == "pipe":
        drain_name = (
            "_live_drain_windows_pipes"
            if os.name == "nt"
            else "_live_drain_posix_pipes"
        )
        real_drain = getattr(live_stand, drain_name)

        def fail_pipe_read(descriptor: int, _size: int) -> bytes:
            pipe_attempts.append(descriptor)
            raise OSError(canary)

        def drain_with_second_pipe_failure(
            process: subprocess.Popen[bytes],
            *,
            stdout: bytearray,
            stderr: bytearray,
            work_deadline: float,
            maximum_bytes: int,
        ) -> bool:
            is_second = len(state["started"]) == 2 and process is state["started"][1]
            if not is_second:
                return real_drain(
                    process,
                    stdout=stdout,
                    stderr=stderr,
                    work_deadline=work_deadline,
                    maximum_bytes=maximum_bytes,
                )
            with monkeypatch.context() as pipe_patch:
                pipe_patch.setattr(live_stand.os, "read", fail_pipe_read)
                return real_drain(
                    process,
                    stdout=stdout,
                    stderr=stderr,
                    work_deadline=work_deadline,
                    maximum_bytes=maximum_bytes,
                )

        monkeypatch.setattr(live_stand, drain_name, drain_with_second_pipe_failure)

    fixture_pin = live_stand._assert_live_caddy_container_pin

    def check_final_pin(
        observed_owner: object,
        observed_pin: tuple[str, str],
        *,
        deadline: float,
        docker_context: live_stand._LiveDockerReadContext,
    ) -> None:
        fixture_pin(
            observed_owner,
            observed_pin,
            deadline=deadline,
            docker_context=docker_context,
        )
        if post_pin_failure and state["events"].count("pin") == 2:
            raise live_stand.StandError(canary)

    monkeypatch.setattr(live_stand, "_assert_live_caddy_container_pin", check_final_pin)
    with pytest.raises(live_stand._LiveCaddyProbeStageFailure) as caught:
        _aud174_read_project_logs(
            owner,
            container_pin=pin,
            completed_at_ms=observed,
            password_nonce=nonce,
            correlation_ids=correlations,
            deadline=live_stand.time.monotonic() + 25,
            docker_context=context,
        )

    assert caught.value.stage == ("post_pin" if post_pin_failure else expected_stage)
    assert state["events"] == ["pin", "logs", "logs", "pin"]
    assert len(state["started"]) == 2
    assert len(state["completed"]) == (2 if failure == "exit" else 1)
    assert state["sizes"][0] == (len(rows["desktop"]), 0)
    assert all(result.stdout == result.stderr == b"" for result in state["completed"])
    for process in state["started"]:
        assert process.returncode is not None
        assert process.stdout is not None and process.stdout.closed
        assert process.stderr is not None and process.stderr.closed
    if failure == "wait":
        assert wait_attempts
    if failure == "pipe":
        assert pipe_attempts
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    for private_value in (canary, nonce, *correlations.values()):
        assert private_value not in str(caught.value)


def test_live_caddy_capture_deadline_cannot_be_rebased_during_reader_admission(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner = object()
    pin = ("a" * 64, "b" * 64)
    context = _aud174_docker_read_context(tmp_path)
    real_read = live_stand._run_live_bounded_read
    now = [100.0]
    state = _aud174_install_window_log_selector(
        monkeypatch,
        owner=owner,
        container_pin=pin,
        context=context,
        records=[],
        now=now,
    )
    started: list[object] = []

    def forbid_start(*args: Any, **_kwargs: Any) -> None:
        started.append(args)
        raise AssertionError("expired capture phase must not start a child")

    def delayed_admission(
        command: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[bytes]:
        state["events"].append("logs")
        state["calls"].append((list(command), dict(kwargs)))
        # Model scheduling delay after relative allowance sampling, not a sleep.
        now[0] = 113.0
        return real_read(command, **kwargs)

    monkeypatch.setattr(live_stand.fast_preflight, "_start_process", forbid_start)
    monkeypatch.setattr(live_stand, "_run_live_bounded_read", delayed_admission)
    with pytest.raises(live_stand._LiveCaddyProbeStageFailure) as caught:
        _aud174_read_project_logs(
            owner,
            container_pin=pin,
            completed_at_ms={
                "desktop": 1_798_000_000_000,
                "mobile": 1_798_000_120_000,
            },
            password_nonce="0" * 32,
            correlation_ids={"desktop": "1" * 32, "mobile": "2" * 32},
            deadline=125.0,
            docker_context=context,
        )

    assert caught.value.stage == "log_read"
    assert state["events"] == ["pin", "logs", "pin"]
    assert state["calls"][0][1]["deadline"] == 112.0
    assert state["calls"][0][1]["command_timeout_seconds"] == pytest.approx(10.0)
    assert now[0] == 115.0
    assert started == []


def _reset_registration_v2_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "project": "mobile",
        "step": "await-response",
        "errorCategory": "timeout",
        "snapshot": "available",
        "hydrated": True,
        "formPresent": True,
        "formInvalid": False,
        "formError": False,
        "submitPresent": True,
        "submitDisabled": False,
        "submitBusy": False,
        "csrfRequested": True,
        "csrfResponse": "success",
        "csrfFailed": False,
    }
    record.update(overrides)
    return record


def _reset_registration_v2_row(record: dict[str, object]) -> str:
    encoded = json.dumps(record, separators=(",", ":"))
    return "UE_LIVE_RESET_REGISTRATION_V2 " + encoded + "\n"


def test_live_reset_registration_v2_accepts_only_finite_failure_observations() -> None:
    parser = getattr(live_stand, "_live_playwright_reset_registration_v2", None)
    assert callable(parser), "bounded registration V2 parser is missing"
    available = _reset_registration_v2_record()
    unavailable = _reset_registration_v2_record(
        project="desktop",
        step="click",
        errorCategory="other",
        snapshot="unavailable",
        hydrated=False,
        formPresent=False,
        submitPresent=False,
        csrfRequested=False,
        csrfResponse="not-observed",
    )
    output = (
        _reset_registration_v2_row(available).replace("\n", "\r\n")
        + _reset_registration_v2_row(unavailable)
    )
    assert parser(output) == [available, unavailable]
    for key, values in {
        "project": ("desktop", "mobile"),
        "step": ("arm-response", "click", "await-response"),
        "errorCategory": (
            "timeout",
            "abort",
            "type-error",
            "target-closed",
            "error",
            "other",
        ),
        "csrfResponse": (
            "not-observed",
            "success",
            "http-error",
            "mixed",
            "unavailable",
        ),
    }.items():
        for value in values:
            record = _reset_registration_v2_record(**{key: value})
            assert parser(_reset_registration_v2_row(record)) == [record]


def test_live_reset_registration_v2_rejects_private_fields_and_wrong_types() -> None:
    parser = getattr(live_stand, "_live_playwright_reset_registration_v2", None)
    assert callable(parser), "bounded registration V2 parser is missing"
    valid = _reset_registration_v2_record()
    invalid = [
        {**valid, "url": "https://private.invalid/"},
        {**valid, "message": "private-message"},
        {**valid, "body": "private-body"},
        {**valid, "cookie": "private-cookie"},
        {**valid, "password": "private-input"},
        {**valid, "schema": 2},
    ]
    enums = {
        "project": ("desktop", "mobile"),
        "step": ("arm-response", "click", "await-response"),
        "errorCategory": (
            "timeout",
            "abort",
            "type-error",
            "target-closed",
            "error",
            "other",
        ),
        "snapshot": ("available", "unavailable"),
        "csrfResponse": (
            "not-observed",
            "success",
            "http-error",
            "mixed",
            "unavailable",
        ),
    }
    for key in enums:
        for value in ("private", "timeout\nprivate", "", True, 0, None, [], {}):
            invalid.append({**valid, key: value})
    boolean_keys = set(valid) - set(enums)
    for key in boolean_keys:
        for value in (0, 1, "true", "false", None, [], {}):
            invalid.append({**valid, key: value})
    for key in valid:
        invalid.append({name: value for name, value in valid.items() if name != key})
    output = "".join(_reset_registration_v2_row(record) for record in invalid)
    assert parser(output) == []


def test_live_reset_registration_v2_rejects_inconsistent_observations() -> None:
    parser = getattr(live_stand, "_live_playwright_reset_registration_v2", None)
    assert callable(parser), "bounded registration V2 parser is missing"
    invalid = [
        _reset_registration_v2_record(snapshot="unavailable"),
        _reset_registration_v2_record(formPresent=False),
        _reset_registration_v2_record(submitPresent=False, submitDisabled=True),
        _reset_registration_v2_record(submitPresent=False, submitBusy=True),
        _reset_registration_v2_record(csrfRequested=False),
        _reset_registration_v2_record(
            csrfRequested=False, csrfResponse="not-observed", csrfFailed=True
        ),
    ]
    rows = "".join(_reset_registration_v2_row(record) for record in invalid)
    assert parser(rows) == []


def test_live_reset_registration_v2_rejects_duplicate_keys_and_untrusted_framing() -> (
    None
):
    parser = getattr(live_stand, "_live_playwright_reset_registration_v2", None)
    assert callable(parser), "bounded registration V2 parser is missing"
    valid = _reset_registration_v2_row(_reset_registration_v2_record())
    rows = [
        valid[:-1],
        "private " + valid,
        "private\r" + valid,
        "private\v" + valid,
        "private\u2028" + valid,
        "\x1b[31m" + valid,
        valid.replace("\n", "\r\r\n"),
        valid.replace('"project":"mobile"', '"project":"mobile","project":"mobile"'),
        valid.replace('"formInvalid":false', '"formInvalid":NaN'),
        valid.replace('"formInvalid":false', '"formInvalid":Infinity'),
        valid.replace(
            '"snapshot":"available"', '"snapshot":"available","body":"private"'
        ),
        valid.rstrip("\n") + " private\n",
        "UE_LIVE_RESET_REGISTRATION_V2 " + "x" * 1024 + "\n",
    ]
    for row in rows:
        assert parser(row) == []


def test_live_reset_registration_v2_deduplicates_and_caps_output() -> None:
    parser = getattr(live_stand, "_live_playwright_reset_registration_v2", None)
    assert callable(parser), "bounded registration V2 parser is missing"
    records = [
        _reset_registration_v2_record(errorCategory=category)
        for category in (
            "timeout",
            "abort",
            "type-error",
            "target-closed",
            "error",
            "other",
        )
    ]
    rows = "".join(_reset_registration_v2_row(record) * 3 for record in records)
    overflow = _reset_registration_v2_row(
        _reset_registration_v2_record(project="desktop")
    )
    assert parser(rows + overflow) == records


@pytest.mark.parametrize("return_code", [0, 1])
def test_live_reset_registration_v2_runner_uses_failure_stdout_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    return_code: int,
) -> None:
    command = live_stand._live_e2e_command(mode="smoke")
    record = _reset_registration_v2_record()
    valid = _reset_registration_v2_row(record)
    stderr_only = _reset_registration_v2_row(
        _reset_registration_v2_record(project="desktop")
    )
    private = "private-body https://private.invalid/?token=hidden"
    completed = subprocess.CompletedProcess(
        command,
        return_code,
        stdout=(valid + valid + private + "\n").encode(),
        stderr=(stderr_only + private).encode(),
    )
    monkeypatch.setattr(
        live_stand.subprocess, "run", lambda *_args, **_kwargs: completed
    )
    if return_code:
        with pytest.raises(live_stand.StandError, match="exit code 1"):
            live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    else:
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    captured = capsys.readouterr()
    expected = ["+ " + " ".join(command)]
    if return_code:
        expected.append(
            "live E2E reset-registration-v2 "
            + json.dumps(record, separators=(",", ":"), sort_keys=True)
        )
    outcome = "failed" if return_code else "passed"
    expected.append(f"live E2E outcome={outcome} exit_code={return_code}")
    assert captured.out.splitlines() == expected
    assert captured.err == ""
    assert private not in captured.out
    assert completed.stdout == completed.stderr == b""
