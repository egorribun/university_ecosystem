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
    env = live_stand.stand_environment(
        {"public": "pub", "private": "priv"}, project_name
    )

    assert env["COMPOSE_PROJECT_NAME"] == project_name
    assert env["LIVE_VAPID_PUBLIC_KEY"] == "pub"
    assert env["LIVE_VAPID_PRIVATE_KEY"] == "priv"  # pragma: allowlist secret
    assert env["LIVE_MAILPIT_PORT"] == "18025"


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


def test_port_preflight_includes_mailpit() -> None:
    assert live_stand.MAILPIT_PORT in live_stand.PUBLISHED_PORTS


def test_port_preflight_uses_wildcard_binds_for_caddy_and_loopback_for_mailpit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probes: list[tuple[int, str]] = []

    def fake_port_is_free(port: int, host: str = "127.0.0.1") -> bool:
        probes.append((port, host))
        return True

    monkeypatch.setattr(live_stand, "port_is_free", fake_port_is_free)

    live_stand.require_free_ports()

    assert probes == [
        (80, ""),
        (443, ""),
        (live_stand.MAILPIT_PORT, "127.0.0.1"),
    ]


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


def test_status_does_not_generate_missing_vapid_keys_for_owned_stand(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, _, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    (worktree / live_stand.VAPID_FILE).unlink()
    commands: list[list[str]] = []
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_: commands.append(list(command))
    )

    with pytest.raises(live_stand.StandError, match="missing or unsafe VAPID key file"):
        live_stand.status()

    assert not (worktree / live_stand.VAPID_FILE).exists()
    assert commands == []


def test_status_is_read_only_and_uses_the_owned_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    marker = worktree / live_stand.STAND_FILE
    vapid = worktree / live_stand.VAPID_FILE
    marker_before = marker.read_bytes()
    vapid_before = vapid.read_bytes()
    commands: list[list[str]] = []
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_: commands.append(list(command))
    )

    live_stand.status()

    assert commands == [
        live_stand.compose_command("ps", project_name=owner.project_name)
    ]
    assert marker.read_bytes() == marker_before
    assert vapid.read_bytes() == vapid_before


def test_stop_preserves_owned_volumes_and_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    commands: list[list[str]] = []
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_: commands.append(list(command))
    )

    live_stand.stop()

    assert commands == [
        live_stand.compose_command("stop", project_name=owner.project_name)
    ]
    assert worktree.exists()
    assert not any("--volumes" in command for command in commands)


def test_teardown_removes_only_the_owned_compose_project_and_preserves_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    env_file = worktree / ".env"
    env_file.write_text("KEEP_ME=1\n", encoding="utf-8")
    commands: list[list[str]] = []
    git_calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_: commands.append(list(command))
    )
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


def test_live_overlay_adds_mailpit_and_keeps_the_base_host_ports() -> None:
    source = (ROOT / "docker-compose.live.yml").read_text(encoding="utf-8")
    overlay: dict[str, Any] = yaml.safe_load(source.replace("!reset", ""))
    services = overlay["services"]

    # The launcher's readiness probes use the base 127.0.0.1 ports, so the
    # overlay publishes only Mailpit and never resets a base binding.
    assert {name for name, service in services.items() if "ports" in service} == {
        "mailpit"
    }
    assert services["mailpit"]["ports"] == [
        "127.0.0.1:${LIVE_MAILPIT_PORT:-18025}:8025"
    ]
    for sender in ("backend", "outbox-worker", "notifications-worker"):
        environment = services[sender]["environment"]
        assert environment["SMTP_HOST"] == "mailpit"
        assert environment["VAPID_PRIVATE_KEY"].startswith("${LIVE_VAPID_PRIVATE_KEY:?")
    assert "caddy" not in services


def test_live_overlay_keeps_base_storage_on_a_project_scoped_volume() -> None:
    source = (ROOT / "docker-compose.live.yml").read_text(encoding="utf-8")
    overlay: dict[str, Any] = yaml.safe_load(source.replace("!reset", ""))

    # Base storage is project-scoped, so the live overlay needs no global-name
    # reset and cannot mount the developer's storage volume.
    assert "minio" not in overlay["services"]
    assert "minio-init" not in overlay["services"]
    assert "volumes" not in overlay
    assert "!reset null" not in source
    assert "university_ecosystem_seaweedfs_data" not in source
    assert "quay.io/minio" not in source


def test_up_stops_the_owned_project_before_checking_ports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree, owner, _ = _prepare_owned_stand(monkeypatch, tmp_path)
    events: list[str] = []
    compose_calls: list[list[str]] = []

    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(
        live_stand,
        "_git",
        lambda *args: "" if "status" in args else "resolved-sha",
    )
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_: (
            compose_calls.append(list(command)),
            events.append("compose-stop" if command[-1] == "stop" else "build"),
        ),
    )
    monkeypatch.setattr(
        live_stand, "require_free_ports", lambda: events.append("ports")
    )
    monkeypatch.setattr(
        live_stand, "ensure_worktree", lambda ref: events.append(ref) or "sha"
    )
    monkeypatch.setattr(live_stand.shutil, "which", lambda name: "pwsh")

    live_stand.up("HEAD")

    assert events == [
        "compose-stop",
        "ports",
        "resolved-sha",
        "build",
    ]
    assert compose_calls[0] == live_stand.compose_command(
        "stop", project_name=owner.project_name
    )
