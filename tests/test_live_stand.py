"""Contracts for the owned live acceptance stand launcher."""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path
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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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
    owner = live_stand.create_stand_owner(worktree)
    keys = {"public": "pub", "private": "priv"}
    key_path = worktree / live_stand.VAPID_FILE
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(json.dumps(keys), encoding="utf-8")
    return worktree, owner, keys


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
