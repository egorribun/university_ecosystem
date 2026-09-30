"""Contracts for the owned live acceptance stand launcher."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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


def _unb64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _port_map(start: int = 24000) -> dict[str, int]:
    return {
        name: start + index
        for index, (name, _service, _container_port) in enumerate(
            live_stand.LIVE_PORT_SPECS
        )
    }


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


def test_seed_cli_passes_a_fresh_password_only_to_the_admin_seed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from contextlib import nullcontext

    owner = live_stand.StandOwner(
        repository=str(ROOT),
        worktree=str(live_stand.WORKTREE),
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
    monkeypatch.setattr(live_stand, "stand_lifecycle_lock", nullcontext)
    monkeypatch.setattr(live_stand, "_require_worktree", lambda: None)
    monkeypatch.setattr(live_stand, "load_stand_owner", lambda _path: owner)
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

    assert live_stand.main(["seed"]) == 0
    assert live_stand.main(["seed"]) == 0

    if len(runs) != 4 or token_sizes != [32, 32]:
        pytest.fail("each seed invocation must create one per-run admin password")

    admin_commands = [runs[1][0], runs[3][0]]
    admin_environments = [runs[1][1], runs[3][1]]
    demo_environments = [runs[0][1], runs[2][1]]
    if any("TEST_PASSWORD" in environment for environment in demo_environments):
        pytest.fail("demo-data seeding must not receive the admin password")

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
    if generated_passwords[0] == generated_passwords[1]:
        pytest.fail("separate seed invocations must use different passwords")
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


def test_e2e_cli_hands_one_password_to_seed_and_playwright_without_persisting_it(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    from contextlib import nullcontext

    worktree = tmp_path / "ue-live"
    port_map = _port_map()
    owner = live_stand.StandOwner(
        repository=str(ROOT),
        worktree=str(worktree),
        project_name="ue-live-0123456789abcdef",
        published_ports=tuple(port_map.items()),
        schema_version=live_stand.OWNER_SCHEMA_VERSION,
    )
    runs: list[tuple[list[str], Path, dict[str, str]]] = []
    playwright_runs: list[tuple[Path, dict[str, str], str, bool, bool]] = []
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

    def capture_playwright(*, cwd: Path, environment: dict[str, str]) -> None:
        print("+", " ".join(live_stand.LIVE_E2E_COMMAND))
        event_order.append("playwright")
        output_directory = environment.get("LIVE_E2E_OUTPUT_DIR", "")
        output_path = Path(output_directory)
        if environment.get("PLAYWRIGHT_TEST_OUTPUT_DIR") != output_directory:
            pytest.fail("Playwright output aliases must share one owned directory")
        owner_marker = output_path.parent / live_stand.LIVE_E2E_OUTPUT_OWNER_MARKER
        if (
            not owner_marker.is_file()
            or owner_marker.read_text(encoding="utf-8")
            != live_stand.LIVE_E2E_OUTPUT_OWNER_MARKER_CONTENT
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

    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setenv("TEST_PASSWORD", ambient_password)
    monkeypatch.setenv("LIVE_PRIMARY_REPOSITORY_ROOT", caller_repository_root)
    for name, value in forwarded_secret_values.items():
        monkeypatch.setenv(name, value)
    for name, value in inherited_npm_config_values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(live_stand.secrets, "token_urlsafe", generate_token)
    monkeypatch.setattr(live_stand, "stand_lifecycle_lock", nullcontext)
    monkeypatch.setattr(live_stand, "_require_worktree", lambda: None)
    monkeypatch.setattr(live_stand, "load_stand_owner", lambda _path: owner)
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

    try:
        if live_stand.main(["e2e"]) != 0:
            pytest.fail("the E2E orchestration command should complete successfully")

        if (
            len(runs) != 2
            or len(dependency_runs) != 1
            or len(playwright_runs) != 1
            or token_sizes != [32]
        ):
            pytest.fail("the E2E command must generate one password and run both seeds")
        if event_order != ["seed", "seed", "bootstrap", "playwright"]:
            pytest.fail("locked dependencies must be ready before Playwright starts")
        if any(marker.exists() for marker in owner_marker_paths):
            pytest.fail(
                "the output ownership marker must be removed with its temp root"
            )

        demo_command, _demo_cwd, demo_env = runs[0]
        admin_command, _admin_cwd, admin_env = runs[1]
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
        if "TEST_PASSWORD" in demo_env:
            pytest.fail("the demo seed must not receive the admin password")
        if e2e_env.get("TEST_PASSWORD") != generated_password:
            pytest.fail("the Playwright child must receive the same per-run password")
        if playwright_password != generated_password:
            pytest.fail("the orchestrator must retain only the password for this run")
        if generated_password == ambient_password:
            pytest.fail("the E2E command must ignore an inherited password")
        if (
            "scripts/seed_demo_data.py" not in demo_command
            or "scripts/seed_admin_data.py" not in admin_command
        ):
            pytest.fail("the E2E command must run demo and admin seed scripts")
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
        if e2e_cwd != worktree / "frontend":
            pytest.fail("Playwright must run from the owned worktree frontend")
        if dependency_frontend != worktree / "frontend":
            pytest.fail("dependency bootstrap must use the owned worktree frontend")
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
        return subprocess.CompletedProcess(command, 1, stdout=stdout, stderr=stderr)

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
    if call.get("capture_output") is not True or call.get("text") is not True:
        pytest.fail("Playwright output must be captured before diagnostics are emitted")


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
    owner = live_stand.create_stand_owner(worktree)
    keys = {"public": "pub", "private": "priv"}
    key_path = worktree / live_stand.VAPID_FILE
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(json.dumps(keys), encoding="utf-8")
    return worktree, owner, keys


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


def test_new_owner_marker_stores_only_the_daemon_fingerprint(
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
    assert marker["version"] == live_stand.OWNER_SCHEMA_VERSION
    assert marker["daemon_fingerprint"] == fingerprint
    assert engine_id not in marker_text


@pytest.mark.parametrize("version", [2, 3])
def test_status_reads_legacy_owner_markers_without_migrating_them(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    version: int,
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    marker_path = _write_legacy_owner_marker(worktree, owner, version)
    marker_before = marker_path.read_bytes()
    commands: list[list[str]] = []
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_: commands.append(list(command))
    )

    live_stand.status()

    assert commands == [
        live_stand.compose_command("ps", project_name=owner.project_name)
    ]
    assert marker_path.read_bytes() == marker_before


@pytest.mark.parametrize("version", [2, 3])
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

    with pytest.raises(
        live_stand.StandError, match="cannot verify Docker daemon ownership"
    ):
        getattr(live_stand, operation)()

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
    commands: list[list[str]] = []
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_: commands.append(list(command))
    )

    with pytest.raises(live_stand.StandError, match="ownership metadata"):
        live_stand.status()

    assert not (worktree / live_stand.STAND_FILE).exists()
    assert not (worktree / live_stand.VAPID_FILE).exists()
    assert commands == []


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
    monkeypatch.setattr(live_stand, "_run", capture_compose_environment)

    getattr(live_stand, operation)()

    compose_args = {
        "status": ("ps",),
        "stop": ("stop",),
        "teardown": ("down", "--volumes", "--remove-orphans"),
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
    marker = worktree / live_stand.STAND_FILE
    vapid = worktree / live_stand.VAPID_FILE
    marker_before = marker.read_bytes()
    vapid_before = vapid.read_bytes()
    monkeypatch.setattr(
        live_stand,
        "docker_daemon_fingerprint",
        lambda: pytest.fail("status must not query Docker daemon identity"),
        raising=False,
    )
    commands: list[list[str]] = []
    environments: list[dict[str, str]] = []

    def capture(command: list[str], *, cwd: Path, env: dict[str, str] | None) -> None:
        commands.append(list(command))
        environments.append(dict(env or {}))

    monkeypatch.setattr(live_stand, "_run", capture)

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


def test_stop_preserves_owned_volumes_and_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
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
    monkeypatch.setattr(live_stand, "_require_worktree", lambda: None)
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
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    env_file = worktree / ".env"
    env_file.write_text("KEEP_ME=1\n", encoding="utf-8")
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
        live_stand.compose_command(
            "down", "--volumes", "--remove-orphans", project_name=owner.project_name
        )
    ]
    assert git_calls == []
    assert worktree.exists()
    assert env_file.read_text(encoding="utf-8") == "KEEP_ME=1\n"
    _assert_compose_port_environment(environments[0], owner.published_ports)


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
        events.append("compose-stop" if command[-1] == "stop" else "build")

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
        "build",
    ]
    assert checked_port_maps == [new_ports, new_ports]
    assert compose_calls[0] == live_stand.compose_command(
        "stop", project_name=owner.project_name
    )
    assert dict(live_stand.load_stand_owner(worktree).published_ports) == new_ports


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
