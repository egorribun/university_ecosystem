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
        text=True,
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
    base_environment["TEST_PASSWORD"] = inherited_password  # pragma: allowlist secret

    def generate_token(size: int) -> str:
        token_sizes.append(size)
        return original_token_urlsafe(size)

    monkeypatch.setattr(live_stand.secrets, "token_urlsafe", generate_token)
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "stand_lifecycle_lock", nullcontext)
    monkeypatch.setattr(live_stand, "_require_worktree", lambda **_kwargs: None)
    monkeypatch.setattr(live_stand, "load_stand_owner", lambda _path: owner)
    daemon_checks: list[live_stand.StandOwner] = []
    monkeypatch.setattr(
        live_stand,
        "_require_owned_docker_daemon",
        lambda checked_owner: daemon_checks.append(checked_owner),
    )
    resource_checks: list[live_stand.StandOwner] = []
    monkeypatch.setattr(
        live_stand,
        "_verify_stand_owner_compose_resources",
        lambda _path, checked_owner, **_kwargs: resource_checks.append(checked_owner),
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
    if daemon_checks != [owner] * 8:
        pytest.fail("each seed subprocess must reverify the owned Docker daemon")
    if resource_checks != [owner] * 6:
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
    monkeypatch.setattr(
        live_stand,
        "_require_owned_docker_daemon",
        lambda _owner: pytest.fail("daemon check ran with stale ownership data"),
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
    dependency_runs: list[tuple[Path, dict[str, str]]] = []
    owner_marker_paths: list[Path] = []
    event_order: list[str] = []
    token_sizes: list[int] = []
    original_token_urlsafe = live_stand.secrets.token_urlsafe
    ambient_password = original_token_urlsafe(32)
    base_environment = {
        "COMPOSE_PROJECT_NAME": owner.project_name,
        "LIVE_VAPID_PUBLIC_KEY": "public-marker",
        "LIVE_VAPID_PRIVATE_KEY": "private-marker",  # pragma: allowlist secret
        "LIVE_HOST_PORT_CADDY_HTTP": str(port_map["CADDY_HTTP"]),
        "LIVE_MAILPIT_PORT": str(port_map["MAILPIT"]),
        "TEST_PASSWORD": ambient_password,  # pragma: allowlist secret
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
    monkeypatch.setattr(live_stand, "_require_owned_docker_daemon", lambda _owner: None)
    monkeypatch.setattr(
        live_stand,
        "_verify_stand_owner_compose_resources",
        lambda *_args, **_kwargs: None,
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
                *live_stand.LIVE_E2E_WINDOWS_ENVIRONMENT,
                *live_stand.LIVE_E2E_CI_ENVIRONMENT,
            ),
        ),
        (
            "posix",
            (
                "PATH",
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
    config_root = tmp_path / "npm-config"
    config_root.mkdir()
    user_config = config_root / "npm-userconfig"
    global_config = config_root / "npm-globalconfig"
    user_config.write_bytes(b"")
    global_config.write_bytes(b"")
    runtime_source = {
        "PATH": "runtime-path-marker",
        "HOME": str(tmp_path / "profile"),
        "LOCALAPPDATA": str(tmp_path / "profile"),
        "SYSTEMROOT": "runtime-systemroot-marker",
        "TEMP": str(tmp_path),
        "TMP": str(tmp_path),
        "USERPROFILE": str(tmp_path / "profile"),
        "TMPDIR": str(tmp_path),
        "CI": "true",
        "GITHUB_ACTIONS": "true",
        "TEST_PASSWORD": "admin-password-sentinel",  # pragma: allowlist secret
        "LIVE_BASE_URL": "http://sensitive-endpoint.invalid",
        "LIVE_MAILPIT_URL": "http://sensitive-mail.invalid",
        "LIVE_E2E_OUTPUT_DIR": str(output_path),
        "PLAYWRIGHT_TEST_OUTPUT_DIR": str(output_path),
        "LIVE_PRIMARY_REPOSITORY_ROOT": "caller-controlled-root-sentinel",
        "CHROMATIC_PROJECT_TOKEN": "chromatic-secret-sentinel",  # pragma: allowlist secret
        "GH_TOKEN": "github-secret-sentinel",  # pragma: allowlist secret
        "ACTIONS_RUNTIME_TOKEN": "actions-secret-sentinel",  # pragma: allowlist secret
        "UNRELATED_API_KEY": "api-key-sentinel",  # pragma: allowlist secret
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
        "PLAYWRIGHT_BROWSERS_PATH": str(browser_cache),
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
    registration_password = "Live-Registration-Pw9!"  # pragma: allowlist secret
    student_password = "student-fixture-sentinel"  # pragma: allowlist secret
    teacher_password = "teacher-fixture-sentinel"  # pragma: allowlist secret
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
@pytest.mark.parametrize(
    "check",
    [
        "admin-users",
        "admin-feature-flags",
        "admin-feature-flags-ui",
        "password-reset-replay",
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
    "line",
    [
        "UE_LIVE_HTTP_STATUS_V1 project=private-project check=admin-users status=200\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=private-check status=200\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=99\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=600\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=-200\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=0200\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=200.0\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=２００\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=200 private-token\n",
        "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=200 \n",
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


def test_live_playwright_http_status_deduplicates_and_bounds_records() -> None:
    output = "".join(
        f"UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status={status}\n"
        * 10
        for status in range(100, 600)
    )
    assert live_stand._live_playwright_http_statuses(output) == [
        ("desktop", "admin-users", status) for status in range(100, 116)
    ]


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
def test_live_playwright_emits_only_bounded_http_statuses(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    return_code: int,
) -> None:
    sentinel = "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=503\n"
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"),
        return_code,
        stdout=(
            "private-title https://private.invalid/?token=private-token\n"
            + sentinel * 20
            + "UE_LIVE_HTTP_STATUS_V1 project=mobile check=admin-feature-flags status=403\n"
            + "UE_LIVE_HTTP_STATUS_V1 project=mobile check=admin-users status="
        ).encode(),
        stderr=(
            b"401\n"
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
        "live E2E HTTP project=mobile check=admin-feature-flags status=403",
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
    ("check", "page", "kind"),
    [
        ("password-reset", "admin-notifications", "error"),
        ("password-reset", "login", "react-418"),
        ("admin-notifications", "register", "error"),
        ("admin-notifications", "forgot-password", "error"),
        ("admin-notifications", "reset-password", "error"),
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
        for count in range(1, 249)
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
        "live E2E page error project=mobile check=password-reset page=reset-password type=other count=999",
        f"live E2E outcome={outcome} exit_code={return_code}",
    ]
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
    live_stand._run_live_playwright(cwd=tmp_path, environment=dict(os.environ))
    printed = capsys.readouterr()
    assert printed.out.splitlines() == [
        "+ " + " ".join(live_stand._live_e2e_command()),
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
            f"        at privateHelper ({frame_sources[2]}:2:17)\n"
            f"        at {frame_sources[2]}:3:1\n"
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
    monkeypatch.setattr(
        live_stand,
        "docker_daemon_fingerprint",
        lambda: daemon_fingerprint,
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
        payload["published_ports"] = dict(owner.published_ports)
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
            {"check": True, "capture_output": True, "text": True},
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
    changed_ports["CADDY_HTTP"] += 1000

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
    changed_ports["CADDY_HTTP"] += 1000
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
    monkeypatch.setattr(
        live_stand, "docker_daemon_fingerprint", lambda: "b" * 64, raising=False
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

    def unavailable() -> str:
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
    mounts: list[dict[str, object]] | None = None,
) -> str:
    return json.dumps(
        {
            "Id": container_id,
            "ProjectLabel": project,
            "ServiceLabel": service,
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
        + '","ServiceLabel":"backend","Mounts":[]}\n'
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
    monkeypatch.setattr(live_stand, "docker_daemon_fingerprint", lambda: "b" * 64)

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
    }
    assert source.count("ports: !override") == len(expected)
    assert all(
        port.startswith("127.0.0.1:${")
        for service_ports in expected.values()
        for port in service_ports
    )
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

    # Base storage is project-scoped, so the live overlay needs no global-name
    # reset and cannot mount the developer's storage volume.
    assert "minio" not in overlay["services"]
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
    monkeypatch.setattr(live_stand, "require_free_ports", check_ports)
    monkeypatch.setattr(live_stand, "choose_published_ports", lambda: new_ports)
    monkeypatch.setattr(
        live_stand,
        "ensure_worktree",
        lambda ref: events.append(f"ensure:{ref}") or "sha",
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
