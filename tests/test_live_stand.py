"""Contracts for the owned live acceptance stand launcher."""

from __future__ import annotations

import base64
import importlib.util
import json
import socket
import sys
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


def test_corrupt_vapid_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / ".secrets" / "live-vapid.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"public": "x"}))

    with pytest.raises(live_stand.StandError, match="does not hold a VAPID key pair"):
        live_stand.load_or_create_vapid(tmp_path)


def test_stand_environment_pins_the_project_and_keys() -> None:
    env = live_stand.stand_environment({"public": "pub", "private": "priv"})

    assert env["COMPOSE_PROJECT_NAME"] == "ue-live"
    assert env["LIVE_VAPID_PUBLIC_KEY"] == "pub"
    assert env["LIVE_VAPID_PRIVATE_KEY"] == "priv"  # pragma: allowlist secret
    assert env["LIVE_MAILPIT_PORT"] == "18025"


def test_compose_command_targets_only_the_stand_project() -> None:
    assert live_stand.compose_command("ps") == [
        "docker",
        "compose",
        "-p",
        "ue-live",
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


def test_down_refuses_an_unexpected_worktree_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(live_stand, "WORKTREE", tmp_path / "somewhere-else")
    with pytest.raises(live_stand.StandError, match="unexpected path"):
        live_stand.down()


def test_down_removes_only_the_stand_project_and_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree = tmp_path / "ue-live"
    (worktree / ".secrets").mkdir(parents=True)
    (worktree / "docker-compose.live.yml").write_text("services: {}\n")
    commands: list[list[str]] = []
    git_calls: list[tuple[str, ...]] = []

    monkeypatch.setattr(live_stand, "REPO_ROOT", tmp_path / "repo")
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(
        live_stand, "_run", lambda command, **_: commands.append(list(command))
    )
    monkeypatch.setattr(live_stand, "_git", lambda *args: git_calls.append(args) or "")

    live_stand.down()

    assert commands == [
        live_stand.compose_command("down", "--volumes", "--remove-orphans")
    ]
    assert git_calls == [("worktree", "remove", "--force", str(worktree))]


def test_main_reports_stand_errors_with_exit_code_two(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse() -> None:
        raise live_stand.StandError("no stand")

    monkeypatch.setattr(live_stand, "status", refuse)

    assert live_stand.main(["status"]) == 2
    assert "live_stand: no stand" in capsys.readouterr().err


def test_live_overlay_publishes_only_caddy_and_mailpit() -> None:
    source = (ROOT / "docker-compose.live.yml").read_text(encoding="utf-8")
    overlay: dict[str, Any] = yaml.safe_load(
        source.replace("!reset []", "[]").replace("!override", "")
    )
    services = overlay["services"]

    published = {name for name, service in services.items() if service.get("ports")}
    assert published == {"mailpit"}
    assert services["mailpit"]["ports"] == [
        "127.0.0.1:${LIVE_MAILPIT_PORT:-18025}:8025"
    ]
    for sender in ("backend", "outbox-worker", "notifications-worker"):
        environment = services[sender]["environment"]
        assert environment["SMTP_HOST"] == "mailpit"
        assert environment["VAPID_PRIVATE_KEY"].startswith("${LIVE_VAPID_PRIVATE_KEY:?")
    assert "caddy" not in services


def test_live_overlay_replaces_minio_with_a_project_scoped_seaweedfs() -> None:
    source = (ROOT / "docker-compose.live.yml").read_text(encoding="utf-8")
    overlay: dict[str, Any] = yaml.safe_load(
        source.replace("!reset []", "[]").replace("!override", "")
    )
    storage = overlay["services"]["minio"]
    init = overlay["services"]["minio-init"]

    assert storage["image"].startswith("ghcr.io/chrislusf/seaweedfs:")
    assert init["image"] == storage["image"]
    assert storage["volumes"] == ["live-seaweedfs-data:/data"]
    assert overlay["volumes"] == {"live-seaweedfs-data": {}}
    assert "S3_CUTOVER_ACK" not in storage["environment"]
    assert "quay.io/minio" not in source


def test_up_stops_the_stands_own_containers_before_checking_ports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree = tmp_path / "ue-live"
    worktree.mkdir()
    (worktree / "docker-compose.live.yml").write_text("services: {}\n")
    events: list[str] = []

    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, **_: events.append(" ".join(command[-3:])),
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
        "docker-compose.live.yml down --remove-orphans",
        "ports",
        "HEAD",
        "-Build -ExtraCompose docker-compose.live.yml",
    ]
